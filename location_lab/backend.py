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


class USBBackend:
    def __init__(self, workspace, enumerate_devices=usb_devices):
        self.workspace = Path(workspace).expanduser().resolve() if workspace else None
        self.enumerate_devices = enumerate_devices
        self.process = None
        self.run = None
        self.socket_path = None

    def device_ids(self):
        return self.enumerate_devices()

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
        settings = dict(wireless=False,targetUSB=device_id,width=800,height=480,fps=30,
                        resolution='800x480',audioEnabled=False,volume=0,callVolume=0,
                        wifiInterface='en0',displayID=0,strictPixels=False)
        settings_path = self.run/'settings.json'
        descriptor = os.open(settings_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(descriptor,'w') as handle:
            json.dump(settings,handle)
        env = dict(os.environ,MACPLAY_DATA=str(data),MACPLAY_SETTINGS_PATH=str(settings_path),
                   MACPLAY_RESOURCES=str(resources),MACPLAY_LANGUAGE='zh-Hans',
                   MACPLAY_ATTEMPT='location-lab',MACPLAY_TEST_SOCKET=str(self.socket_path),
                   MACPLAY_LOCATION_LANE='usb',GST_REGISTRY=str(self.run/'gst-registry.bin'),
                   DYLD_LIBRARY_PATH=str(resources/'gstreamer/macos-arm64/lib'))
        try:
            process = subprocess.Popen([str(executable),str(resources/'engine/main.js')],env=env,
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                text=True,bufsize=1,start_new_session=True)
            self.process = process
        except Exception:
            self.stop()
            raise
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
            try:
                for line in process.stdout:
                    if 'MFi auth succeeded' in line:
                        enqueue('connected')
                    if 'location: subscribed' in line:
                        enqueue('subscribed',active=not line.rstrip().endswith('[]'))
                    if 'location: stopped' in line:
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
                    if isinstance(event,dict) and event.get('disconnected'):
                        enqueue('disconnected')
            except (OSError,ValueError):
                pass
            finally:
                try: events.put_nowait(None)
                except queue.Full: overflow.set()
        threading.Thread(target=dispatch_events,daemon=True,name='usb-event-dispatch').start()
        threading.Thread(target=observe,daemon=True,name='usb-events').start()

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
