"""USB adapter for the existing local MacPlay experiment runtime.

No authentication material or third-party runtime is shipped by Location Lab.
Raw runtime output remains private to this adapter and is never printed or saved.
"""
import base64
import json
import os
from pathlib import Path
import plistlib
import queue
import re
import signal
import socket
import struct
import subprocess
import tempfile
import threading


def _read_exact(connection, count):
    result = bytearray()
    while len(result) < count:
        part = connection.recv(count-len(result))
        if not part:
            raise ConnectionError('USB enumeration disconnected')
        result.extend(part)
    return bytes(result)


def usb_devices():
    body = plistlib.dumps(dict(MessageType='ListDevices', ClientVersionString='LocationLab',
                              ProgName='LocationLab', kLibUSBMuxVersion=3))
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(2)
        connection.connect('/var/run/usbmuxd')
        connection.sendall(struct.pack('<IIII',16+len(body),1,8,1)+body)
        size, _, _, _ = struct.unpack('<IIII',_read_exact(connection,16))
        if not 16 <= size <= 2_000_000:
            raise ValueError('Invalid USB response')
        response = plistlib.loads(_read_exact(connection,size-16))
    return [d['Properties']['SerialNumber'] for d in response.get('DeviceList',[])
            if d.get('Properties',{}).get('ConnectionType')=='USB']


def usb_connect(serial,port):
    """Open a TCP stream to one explicitly selected physical USB device."""
    if type(port) is not int or not 1<=port<=65535:raise ValueError('USB 控制端口无效')
    def exchange(connection,fields):
        body=plistlib.dumps(dict(fields,ClientVersionString='LocationLab',ProgName='LocationLab',kLibUSBMuxVersion=3))
        connection.sendall(struct.pack('<IIII',16+len(body),1,8,1)+body)
        size,_,_,_=struct.unpack('<IIII',_read_exact(connection,16))
        if not 16<=size<=2_000_000:raise ValueError('USB 控制响应无效')
        return plistlib.loads(_read_exact(connection,size-16))
    with socket.socket(socket.AF_UNIX) as lookup:
        lookup.settimeout(2);lookup.connect('/var/run/usbmuxd')
        response=exchange(lookup,dict(MessageType='ListDevices'))
    matches=[d['DeviceID'] for d in response.get('DeviceList',[]) if d.get('Properties',{}).get('SerialNumber')==serial and d.get('Properties',{}).get('ConnectionType')=='USB']
    if len(matches)!=1:raise ConnectionError('目标 USB iPhone 不可用')
    connection=socket.socket(socket.AF_UNIX)
    try:
        connection.settimeout(3);connection.connect('/var/run/usbmuxd')
        reply=exchange(connection,dict(MessageType='Connect',DeviceID=matches[0],PortNumber=socket.htons(port)))
        if reply.get('Number')!=0:raise ConnectionError('手机 USB 控制端尚未就绪')
        return connection
    except Exception:connection.close();raise


class USBBackend:
    def __init__(self, workspace, enumerate_devices=usb_devices):
        self.workspace = Path(workspace).expanduser().resolve() if workspace else None
        self.enumerate_devices = enumerate_devices
        self.process = None
        self.run = None
        self.socket_path = None

    lane = "usb"

    def device_ids(self):
        return self.enumerate_devices()

    def settings(self, device_id):
        return dict(wireless=False,targetUSB=device_id,width=800,height=480,fps=30,
                    resolution="800x480",audioEnabled=False,volume=0,callVolume=0,
                    wifiInterface="en0",displayID=0,strictPixels=False)

    def start(self, session_id, device_id, emit):
        if self.process is not None:
            raise RuntimeError('A USB session already exists')
        if not self.workspace:
            raise ValueError('请先配置 USB 运行时路径')
        resources, data = self.workspace/'resources', self.workspace/'data'
        executable = resources/'runtime/MacPlayReceiver.app/Contents/MacOS/MacPlayReceiver'
        required = [executable, resources/'engine/main.js', data/'authentication/identity.pk8',
                    data/'authentication/certificate.p7b',data/'cp/macplay-v3/identity.json']
        if any(not path.is_file() for path in required):
            raise ValueError('USB 运行时或本机认证资料不完整')
        if not os.access(executable,os.X_OK):
            raise ValueError('USB 运行时不可执行')
        # Short root keeps the Unix socket below macOS sockaddr_un's 104-byte limit.
        self.run = Path(tempfile.mkdtemp(prefix='ll-',dir='/tmp'))
        self.socket_path = self.run/'control.sock'
        settings = self.settings(device_id)
        # The helper also binds authentication/bluetooth.sock below MACPLAY_DATA.
        # Keep its lexical path short while preserving the original identity files.
        session_data=self.run/'data'
        session_data.symlink_to(data,target_is_directory=True)
        # Pass settings via an inherited pipe: no Wi-Fi password file on disk.
        payload=json.dumps(settings).encode()
        if len(payload)>8192:raise ValueError('运行时设置过大')
        settings_read,settings_write=os.pipe()
        try:
            with os.fdopen(settings_write,'wb') as destination:destination.write(payload)
        except Exception:
            os.close(settings_read);raise
        settings_path=Path('/dev/fd')/str(settings_read)
        env = dict(os.environ,MACPLAY_DATA=str(session_data),MACPLAY_SETTINGS_PATH=str(settings_path),
                   MACPLAY_RESOURCES=str(resources),MACPLAY_LANGUAGE='zh-Hans',
                   MACPLAY_ATTEMPT='location-lab',MACPLAY_TEST_SOCKET=str(self.socket_path),
                   MACPLAY_LOCATION_LANE=self.lane,MACPLAY_WIFI_SECURITY=str(settings.get('wifiSecurity',2)),GST_REGISTRY=str(self.run/'gst-registry.bin'),
                   DYLD_LIBRARY_PATH=str(resources/'gstreamer/macos-arm64/lib'))
        try:
            process = subprocess.Popen([str(executable),str(resources/'engine/main.js')],env=env,
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                text=True,bufsize=1,start_new_session=True,pass_fds=(settings_read,))
            self.process = process
        except Exception:
            self.stop()
            raise
        finally:os.close(settings_read)
        events = queue.Queue(maxsize=1024)
        overflow = threading.Event()
        def enqueue(kind, **data):
            try: events.put_nowait((kind,data))
            except queue.Full: overflow.set()
        def dispatch_events():
            while True:
                event = events.get()
                if overflow.is_set():
                    emit(session_id,'failure')
                    return
                if event is None:
                    emit(session_id,'disconnected')
                    return
                emit(session_id,event[0],**event[1])
        def observe():
            video_ready=False
            try:
                for line in process.stdout:
                    if 'CarPlayAvailability wired=' in line:
                        wireless=line.split('wireless=',1)[-1]
                        if 'available: Some(true)' in wireless: enqueue('diagnostic',stage='carplay-wireless-available')
                        elif 'available: Some(false)' in wireless: enqueue('diagnostic',stage='carplay-wireless-unavailable')
                        else: enqueue('diagnostic',stage='carplay-wireless-availability-unknown')
                    if 'CarPlayStartSession sent' in line: enqueue('diagnostic',stage='network-handoff-started')
                    if 'CarPlayStartSession not sent:' in line: enqueue('diagnostic',stage='network-handoff-not-sent')
                    if 'RFCOMM connected' in line: enqueue('diagnostic',stage='bluetooth-connected')
                    if 'SDP timed out' in line: enqueue('diagnostic',stage='bluetooth-discovery-timeout')
                    if 'privacy-sensitive' in line or 'not authorized' in line.lower(): enqueue('diagnostic',stage='permission-required')
                    if 'control channel closed' in line: enqueue('diagnostic',stage='control-channel-closed')
                    if 'MFi auth succeeded' in line:
                        enqueue('connected')
                    if self.lane == 'usb':
                        if 'location: subscribed' in line:
                            enqueue('subscribed',active=not line.rstrip().endswith('[]'))
                        if 'location: stopped' in line:
                            enqueue('subscribed',active=False)
                    else:
                        if f'[MVP] location-start channel={self.lane} ' in line:
                            enqueue('subscribed',active='[]' not in line)
                        if line.strip() == f'[MVP] location-stop channel={self.lane}':
                            enqueue('subscribed',active=False)
                    if '[MVP] location-message-queued' in line:
                        enqueue('queued',count=1)
                    if '[MVP] location-send-failed' in line or 'unplugged' in line:
                        enqueue('failure')
                    # Only a whitelisted event is exposed; runtime text may contain credentials.
                    try:
                        event = json.loads(line)
                    except (ValueError,TypeError):
                        continue
                    if isinstance(event,dict):
                        stages={'media-preflight-start','media-preflight-ready','starting','network-validation',
                                'network-handoff-started','network-handoff-alternate',
                                'control-connected','first-video-packet','first-decoded-frame','video-recovery',
                                'video-recovery-failed','session-error','配件认证已通过','等待iPhone连接','CarPlay会话已建立','连接已断开'}
                        if event.get('stage') in stages: enqueue('diagnostic',stage=event['stage'])
                        if event.get('stage')=='network-discovery' and not video_ready:
                            detail=event.get('detail')
                            mapping={'控制服务已发现':'carplay-service-discovered','忽略非所选设备的控制服务':'carplay-other-device-filtered',
                                     '控制地址已就绪':'carplay-address-ready','正在探测控制服务':'carplay-control-probe',
                                     '控制服务回应/HTTP':'carplay-control-response','PTR查询已发送':'carplay-discovery-query'}
                            if isinstance(detail,str):
                                fault=re.search(r'(IPv[46])(多播警告|套接字错误|发现接口启动失败)/([A-Z][A-Z0-9_]{0,31})(?:\s|$)',detail)
                                if fault:
                                    enqueue('diagnostic',stage='discovery-'+fault[1].lower()+'-warning-'+fault[3])
                                for label,stage in [('IPv4发现接口已就绪','discovery-ipv4-ready'),('IPv6发现接口已就绪','discovery-ipv6-ready'),('接收服务广播已发送','discovery-advertised')]:
                                    if label in detail:enqueue('diagnostic',stage=stage)
                                for text,stage in mapping.items():
                                    if text in detail:enqueue('diagnostic',stage=stage);break
                        if event.get('stage')=='handoff-summary' and isinstance(event.get('detail'),dict):
                            detail=event['detail'];counts=[]
                            for key,label in [('discoverySockets','sockets'),('discoveryResponses','responses'),('controlServices','services'),('probeEndpoints','endpoints'),('probeAccepted','accepted')]:
                                value=detail.get(key)
                                if type(value) is not int or not 0<=value<=1_000_000:break
                                counts.append(f'{label}={value}')
                            if len(counts)==5:enqueue('diagnostic',stage='discovery-summary:'+','.join(counts))
                        if event.get('type')=='videoStatistics':
                            enqueue('video-statistics',received=max(0,int(event.get('receivedFrames',0))),decoded=max(0,int(event.get('decodedFrames',0))))
                        if event.get('showCarPlay') is True or event.get('hiddenVideoValidation') is True:
                            video_ready=True
                            enqueue('video-ready')
                        if event.get('disconnected'):
                            enqueue('disconnected')
            except (OSError,ValueError):
                pass
            finally:
                try: events.put_nowait(None)
                except queue.Full: overflow.set()
        threading.Thread(target=dispatch_events,daemon=True,name='usb-event-dispatch').start()
        threading.Thread(target=observe,daemon=True,name='usb-events').start()

    def take_stop_request(self):
        # A private, random run plus the expected revision prevents delayed stops
        # from cancelling a later target, even inside the same receiver process.
        if not self.run: return None
        path=self.run/'STOP'
        try:
            descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
            with os.fdopen(descriptor) as source:
                value=json.loads(source.read(2048))
            path.unlink()
            return value if isinstance(value,dict) else None
        except FileNotFoundError: return None
        except (OSError,ValueError):
            try:path.unlink()
            except OSError:pass
            return None

    def send(self, frame):
        if not self.process or self.process.poll() is not None:
            raise ConnectionError('USB runtime is not running')
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(2)
            connection.connect(str(self.socket_path))
            command = 'location '+base64.b64encode(frame.encode('ascii')).decode('ascii')+'\n'
            connection.sendall(command.encode('ascii'))
            response = bytearray()
            while b'\n' not in response and len(response)<10000:
                part=connection.recv(1024)
                if not part:
                    raise ConnectionError('USB helper closed before acknowledgement')
                response.extend(part)
            parsed=json.loads(response.split(b'\n',1)[0])
            if not isinstance(parsed,dict) or parsed.get('ok') is not True:
                raise ConnectionError('USB helper rejected location')

    def stop(self):
        process, self.process = self.process, None
        if process:
            try:
                process.stdin.write('stop\n');process.stdin.flush()
            except (BrokenPipeError,OSError,ValueError):
                pass
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try: os.killpg(process.pid,signal.SIGTERM)
                except ProcessLookupError: pass
                try: process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    try: os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError: pass
                    process.wait(timeout=2)
            # Receiver may finish before its helper: terminate only our dedicated group.
            try: os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError: pass
            for stream in (process.stdin,process.stdout):
                try: stream.close()
                except (OSError,ValueError): pass
        if self.run:
            import shutil
            shutil.rmtree(self.run,ignore_errors=True)
        self.run = self.socket_path = None
