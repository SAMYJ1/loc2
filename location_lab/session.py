"""Thread-safe session boundary shared by local and authorized phone controls."""
import copy
import datetime as dt
import math
import threading
import time
import uuid


def _sentence(body):
    checksum = 0
    for byte in body.encode('ascii'):
        checksum ^= byte
    return '$' + body + '*%02X\r\n' % checksum


def _coordinate(value, latitude):
    units = int(math.floor(abs(value) * 600000 + .5))
    degrees, rest = divmod(units, 600000)
    minutes, fraction = divmod(rest, 10000)
    hemisphere = ('S' if value < 0 else 'N') if latitude else ('W' if value < 0 else 'E')
    return f'{degrees:0{2 if latitude else 3}d}{minutes:02d}.{fraction:04d},{hemisphere}'


def _nmea(point, now):
    pair = _coordinate(point['latitude'], True) + ',' + _coordinate(point['longitude'], False)
    clock, day = now.strftime('%H%M%S.00'), now.strftime('%d%m%y')
    # Existing tested synthetic fixed-point profile; these are not GNSS measurements.
    return (_sentence(f'GPGGA,{clock},{pair},1,08,1.0,10.0,M,0.0,M,,') +
            _sentence(f'GPRMC,{clock},A,{pair},0.00,0.00,{day},,'))


def validate_point(point):
    if not isinstance(point, dict):
        raise ValueError('位置必须为坐标对象')
    for key, limit in [('latitude',90),('longitude',180)]:
        value = point.get(key)
        if isinstance(value, bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or abs(value)>limit:
            raise ValueError('请输入有效 WGS84 经纬度')
    if point.get('inputCRS','WGS84') != 'WGS84':
        raise ValueError('此坐标参考系尚未完成 WGS84 校准')
    result = copy.deepcopy(point)
    result.setdefault('inputCRS','WGS84')
    result.setdefault('provider','manual')
    result.setdefault('inputCoordinate',dict(latitude=point['latitude'],longitude=point['longitude']))
    result.setdefault('normalizedWGS84',dict(latitude=point['latitude'],longitude=point['longitude']))
    normalized = result['normalizedWGS84']
    if not isinstance(normalized,dict) or any(normalized.get(k)!=point[k] for k in ('latitude','longitude')):
        raise ValueError('归一化坐标与供数目标不一致')
    return result


class SessionService:
    def __init__(self, backend, monotonic=time.monotonic, utcnow=None):
        self.backend, self.clock = backend, monotonic
        self.utcnow = utcnow or (lambda:dt.datetime.now(dt.timezone.utc))
        self.lock = threading.RLock()
        self.snapshot = dict(sessionId=None, deviceId=None, availableDevices=[], connected=False,
            subscribed=False, target=None, state='disconnected', helperAcceptedBatches=0,
            queuedMessages=0, adoption='unverified', recovery='not-required', error=None)
        self.next_send = 0
        self.last_tick = None

    def status(self):
        with self.lock:
            return copy.deepcopy(self.snapshot)

    def refresh_devices(self):
        with self.lock:
            try:
                devices = self.backend.device_ids()
            except Exception:
                self.snapshot['availableDevices'] = []
                self._fail('无法查询 USB 设备；当前会话已停止')
                return self.status()
            self.snapshot['availableDevices'] = devices
            if self.snapshot['sessionId'] and self.snapshot['deviceId'] not in devices:
                self.stop('usb-disconnected')
            if not self.snapshot['sessionId'] and self.snapshot['state'] not in ('stopped','error'):
                self.snapshot['state'] = 'ready' if len(devices)==1 else 'disconnected'
            return self.status()

    def apply(self, device_id, point, expected_session_id=None):
        point = validate_point(point)
        with self.lock:
            if expected_session_id is not None and expected_session_id != self.snapshot['sessionId']:
                raise ValueError('会话已变化，请刷新后重新应用')
            self.refresh_devices()
            if device_id not in self.snapshot['availableDevices'] or len(self.snapshot['availableDevices']) != 1:
                raise ValueError('请连接且仅连接指定的一台 USB iPhone')
            if not self.snapshot['sessionId']:
                self.snapshot.update(sessionId=str(uuid.uuid4()), deviceId=device_id,
                    state='connecting', connected=False, subscribed=False, error=None,
                    helperAcceptedBatches=0, queuedMessages=0, adoption='unverified')
                self.snapshot['target'] = point
                try:
                    self.backend.start(self.snapshot['sessionId'], device_id, self._event)
                except Exception:
                    self._fail('USB 后端启动失败，请检查本机运行时和认证配置')
                    raise ValueError(self.snapshot['error']) from None
            if not self.snapshot['sessionId']:
                raise ValueError('USB 会话启动时已结束，请检查连接')
            self.snapshot['target'] = point
            self.snapshot['adoption'] = 'unverified'
            return self.status()

    def stop(self, reason='requested-stop', expected_session_id=None):
        with self.lock:
            if expected_session_id is not None and expected_session_id != self.snapshot['sessionId']:
                raise ValueError('会话已变化，请刷新后重试')
            self.snapshot.update(sessionId=None, target=None, connected=False, subscribed=False,
                                 state='stopped', adoption='unverified', stopReason=reason)
            self.next_send = 0
            self.last_tick = None
            self.backend.stop()
            return self.status()

    def _fail(self, message):
        self.stop('backend-failure')
        self.snapshot.update(state='error', error=message)

    def suspend(self): return self.stop('sleep')
    def shutdown(self): return self.stop('quit')

    def _event(self, session, kind, **data):
        with self.lock:
            if session != self.snapshot['sessionId']:
                return
            if kind == 'connected': self.snapshot['connected'] = True
            if kind == 'subscribed': self.snapshot['subscribed'] = bool(data['active'])
            if kind == 'queued': self.snapshot['queuedMessages'] += data.get('count',1)
            if kind in ('failure','disconnected'):
                self._fail('USB 会话已结束，请检查连接后重新应用')
            elif self.snapshot['connected']:
                self.snapshot['state'] = 'reporting' if self.snapshot['subscribed'] and self.snapshot['helperAcceptedBatches'] else 'waiting-for-subscription'

    def confirm_adoption(self, session_id):
        with self.lock:
            if not session_id or session_id != self.snapshot['sessionId'] or not self.snapshot['helperAcceptedBatches']:
                raise ValueError('只能确认当前已报点会话的位置采用')
            self.snapshot['adoption'] = 'user-confirmed'
            return self.status()

    def confirm_recovery(self):
        with self.lock:
            if self.snapshot['sessionId']:
                raise ValueError('请先停止报点，再确认真实位置恢复')
            self.snapshot['recovery'] = 'user-confirmed'
            return self.status()

    def tick(self):
        with self.lock:
            now = self.clock()
            if self.snapshot['sessionId'] and self.last_tick is not None and not 0 <= now-self.last_tick <= 5:
                self.stop('clock-gap')
                return self.status()
            self.last_tick = now
            s = self.snapshot
            if s['target'] and s['connected'] and s['subscribed'] and self.clock() >= self.next_send:
                s['recovery'] = 'pending'
                try:
                    self.backend.send(_nmea(s['target'], self.utcnow()))
                except Exception:
                    self._fail('报点失败，会话已停止；请单独确认真实位置恢复')
                    return self.status()
                s['helperAcceptedBatches'] += 1
                s['state'] = 'reporting'
                s['recovery'] = 'pending'
                self.next_send = self.clock() + 1
