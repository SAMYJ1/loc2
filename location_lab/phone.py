"""Same-origin phone control. Mac approval exists only on the private local IPC."""
import hashlib
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import math
from pathlib import Path
import re
import secrets
import time
from .favorites import FavoritesStore

COOKIE = 'location_lab_control'
WEB = Path(__file__).with_name('web')


class RequestError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def secret_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


class PhoneControl:
    def __init__(self, service, clock=time.time, state_dir=None):
        self.service, self.clock = service, clock
        self.lock = service.lock
        self.challenge = None
        self.pending = {}
        self.grants = {}
        self.origin = None
        self.favorites=FavoritesStore(Path(state_dir)/"favorites.json" if state_dir is not None else None)

    def create_pairing(self):
        with self.lock:
            snapshot=self.service.refresh_devices()
            if len(snapshot['availableDevices']) != 1:
                raise ValueError('请连接且仅连接需要授权的一台 USB iPhone')
            self.challenge=dict(challenge=secrets.token_urlsafe(32),deviceId=snapshot['availableDevices'][0],expires=self.clock()+120)
            return dict(self.challenge)

    def request_pairing(self, body):
        with self.lock:
            challenge=self.challenge
            if not challenge or self.clock()>challenge['expires'] or not secrets.compare_digest(str(body.get('challenge','')),challenge['challenge']):
                raise RequestError('配对二维码已失效，请在 Mac 重新生成',403)
            poll=body.get('pollSecret')
            if not isinstance(poll,str) or not re.fullmatch('[0-9a-f]{64}',poll):
                raise RequestError('配对请求无效')
            label=body.get('label','手机浏览器')
            if not isinstance(label,str) or not 1<=len(label)<=80 or any(ord(char)<32 for char in label):
                raise RequestError('控制端名称无效')
            self.pending={key:value for key,value in self.pending.items() if value['expires']>self.clock()}
            if len(self.pending)>=8: raise RequestError('待确认请求过多，请先在 Mac 处理',429)
            request_id=secrets.token_urlsafe(24)
            self.pending[request_id]=dict(deviceId=challenge['deviceId'],label=label,pollHash=secret_hash(poll),expires=self.clock()+120,state='pending')
            self.challenge=None
            return dict(requestId=request_id,state='pending')

    def approve(self, request_id):
        with self.lock:
            pending=self.pending.get(request_id)
            if not pending or pending['expires']<self.clock() or pending['state']!='pending':
                raise ValueError('配对请求已失效')
            if self.service.refresh_devices()['availableDevices'] != [pending['deviceId']]:
                raise ValueError('目标 USB 手机已变化，请重新配对')
            token=secrets.token_urlsafe(32)
            self.grants[secret_hash(token)]=dict(deviceId=pending['deviceId'],label=pending['label'],requests={})
            pending.update(state='approved',token=token)

    def deny(self, request_id):
        with self.lock:
            self.pending.pop(request_id,None)

    def poll_pairing(self, body):
        with self.lock:
            pending=self.pending.get(body.get('requestId'))
            poll=body.get('pollSecret')
            if not pending or pending['expires']<self.clock() or not isinstance(poll,str) or not secrets.compare_digest(pending['pollHash'],secret_hash(poll)):
                raise RequestError('配对请求已失效',403)
            token=pending.get('token')
            if token: del self.pending[body['requestId']]
            return dict(state=pending['state']),token

    def authorize(self, token):
        if not isinstance(token,str) or len(token)>128:
            raise RequestError('请先在 Mac 确认配对授权',401)
        grant=self.grants.get(secret_hash(token))
        if grant is None: raise RequestError('请先在 Mac 确认配对授权',401)
        return grant

    def status(self, token):
        with self.lock:
            grant=self.authorize(token)
            status=self.service.status()
            if status['deviceId'] not in (None,grant['deviceId']):
                if status['sessionId']:
                    raise RequestError('授权目标当前不可用，请在 Mac 检查目标手机',403)
                status.update(deviceId=None,target=None,helperAcceptedBatches=0,queuedMessages=0,adoption='unverified',recovery='not-required',error=None)
            # Only the bound device is disclosed to this controller.
            status['availableDevices']=[grant['deviceId']] if grant['deviceId'] in status['availableDevices'] else []
            return dict(authorized=True,deviceId=grant['deviceId'],status=status)

    def favorite_list(self,token):
        with self.lock:
            grant=self.authorize(token)
            return dict(favorites=self.favorites.list(grant['deviceId']))

    def command(self, token, action, body):
        with self.lock:
            grant=self.authorize(token)
            if body.get('deviceId')!=grant['deviceId']:
                raise RequestError('此控制端未获准操作该手机',403)
            request_id=body.get('requestId')
            timestamp=body.get('timestamp')
            revision=body.get('expectedRevision')
            if not isinstance(request_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}',request_id):
                raise RequestError('请求标识无效')
            if isinstance(timestamp,bool) or not isinstance(timestamp,(int,float)) or not math.isfinite(timestamp) or not -5<=self.clock()-timestamp<=30:
                raise RequestError('请求已过期，请刷新后重试',409)
            if isinstance(revision,bool) or not isinstance(revision,int):
                raise RequestError('缺少当前状态版本')
            grant['requests']={key:value for key,value in grant['requests'].items() if self.clock()-value<=60}
            if request_id in grant['requests']:
                raise RequestError('请求已处理，请刷新后重新操作',409)
            if len(grant['requests'])>=256: raise RequestError('操作过于频繁，请稍后重试',429)
            current=self.service.refresh_devices()
            if body.get('expectedEpoch')!=current['controlEpoch'] or revision!=current['controlRevision']:
                raise RequestError('连接或目标已变化，请刷新后重新操作',409)
            if current['sessionId'] and current['deviceId']!=grant['deviceId']:
                raise RequestError('当前会话不属于已授权手机',403)
            # Record before execution so a failed transport cannot replay the same action.
            grant['requests'][request_id]=self.clock()
            try:
                if action=='apply':
                    point=body.get('point')
                    if not isinstance(point,dict) or point.get('provider','manual')!='manual' or point.get('inputCRS','WGS84')!='WGS84':
                        raise ValueError('请使用明确标注的 WGS84 手工坐标')
                    self.service.apply(grant['deviceId'],point,current['sessionId'])
                elif action=='stop': self.service.stop(expected_session_id=current['sessionId'])
                elif action=='favorites/add':
                    return dict(favorites=self.favorites.add(grant['deviceId'],body.get('name'),body.get('point')))
                elif action=='favorites/remove':
                    return dict(favorites=self.favorites.remove(grant['deviceId'],body.get('favoriteId')))
                else: raise RequestError('操作不存在',404)
            except ValueError as error:
                raise RequestError(str(error)) from None
            return self.status(token)

    def local_status(self):
        with self.lock:
            challenge=self.challenge if self.challenge and self.challenge['expires']>self.clock() else None
            return dict(origin=self.origin,pairingURL=(self.origin+'/#pair='+challenge['challenge']) if challenge and self.origin else None,
                pairingDevice=challenge['deviceId'] if challenge else None,
                pending=[dict(requestId=key,label=value['label'],deviceId=value['deviceId']) for key,value in self.pending.items() if value['state']=='pending' and value['expires']>self.clock()])


class PhoneServer(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=True
    def __init__(self,address,control,advertised_host):
        bind=ipaddress.ip_address(address[0])
        if bind.is_unspecified or not (bind.is_private or bind.is_loopback) or bind.version != 4:
            raise ValueError('手机控制服务需要明确的本机局域网 IPv4 地址')
        if not re.fullmatch(r'[a-zA-Z0-9.-]+',advertised_host):
            raise ValueError('手机控制服务主机名无效')
        self.control=control
        super().__init__(address,PhoneHandler)
        self.authority=advertised_host if self.server_port==80 else f'{advertised_host}:{self.server_port}'
        self.origin='http://'+self.authority
        control.origin=self.origin


class PhoneHandler(BaseHTTPRequestHandler):
    server_version='LocationLab'
    def setup(self):
        super().setup();self.connection.settimeout(5)
    def log_message(self,*args): pass
    def _headers(self,post=False):
        if self.headers.get_all('Host') != [self.server.authority]:
            raise RequestError('主机地址不匹配',403)
        origins=self.headers.get_all('Origin')
        if (post and origins != [self.server.origin]) or (origins is not None and origins != [self.server.origin]):
            raise RequestError('请求来源不匹配',403)
        if self.headers.get('Sec-Fetch-Site')=='cross-site': raise RequestError('请求来源不匹配',403)
    def _cookie(self):
        try:
            cookies=SimpleCookie();cookies.load(self.headers.get('Cookie',''))
            return cookies[COOKIE].value if COOKIE in cookies else None
        except Exception: return None
    def _reply(self,status,body,content_type='application/json; charset=utf-8',cookie=None):
        data=json.dumps(body,ensure_ascii=False,allow_nan=False).encode() if not isinstance(body,bytes) else body
        self.send_response(status)
        self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie: self.send_header('Set-Cookie',f'{COOKIE}={cookie}; HttpOnly; SameSite=Strict; Path=/')
        self.end_headers();self.wfile.write(data)
    def do_GET(self):
        try:
            self._headers()
            if self.path=='/api/status': return self._reply(200,self.server.control.status(self._cookie()))
            if self.path=='/api/favorites': return self._reply(200,self.server.control.favorite_list(self._cookie()))
            static={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8'),'/favorites.js':('favorites.js','text/javascript; charset=utf-8'),'/favorites.css':('favorites.css','text/css; charset=utf-8')}
            if self.path not in static: raise RequestError('页面不存在',404)
            name,mime=static[self.path];self._reply(200,(WEB/name).read_bytes(),mime)
        except RequestError as error: self._reply(error.status,dict(error=str(error)))
        except (OSError,ValueError): self._reply(500,dict(error='请求处理失败'))
    def do_POST(self):
        try:
            self._headers(post=True)
            if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length') or [])!=1:
                raise RequestError('请求长度无效')
            if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json':
                raise RequestError('请求必须为 JSON',415)
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=16384: raise RequestError('请求过大或为空',413)
            raw=self.rfile.read(size)
            if len(raw)!=size: raise RequestError('请求不完整')
            body=json.loads(raw)
            if not isinstance(body,dict): raise RequestError('请求必须为对象')
            control=self.server.control
            if self.path=='/api/pair/request': result,cookie=control.request_pairing(body),None
            elif self.path=='/api/pair/poll': result,cookie=control.poll_pairing(body)
            elif self.path in ('/api/apply','/api/stop','/api/favorites/add','/api/favorites/remove'): result,cookie=control.command(self._cookie(),self.path[5:],body),None
            else: raise RequestError('操作不存在',404)
            self._reply(200,result,cookie=cookie)
        except RequestError as error: self._reply(error.status,dict(error=str(error)))
        except (ValueError,TypeError): self._reply(400,dict(error='请求格式无效'))
        except OSError: self.close_connection=True
