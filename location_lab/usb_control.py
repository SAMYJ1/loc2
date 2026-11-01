"""USB byte forwarding; TLS and authorization stay in the existing native API."""
import select
import socket
import threading
from .backend import usb_devices,usb_connect

USB_CONTROL_PORT=32145


class USBControlBridge:
    def __init__(self,target,server_port,device_port=USB_CONTROL_PORT,enumerate_devices=usb_devices,connect=usb_connect,pool_size=3):
        self.target,self.server_port,self.device_port=target,server_port,device_port
        self.enumerate_devices,self.connect=enumerate_devices,connect
        self.pool_size=pool_size
        self.done=threading.Event();self.available=threading.Event()
        self.lock=threading.Lock();self.sockets=set();self.usb_sockets=set();self.threads=[]

    @property
    def connected(self):
        with self.lock:return bool(self.usb_sockets) and self.available.is_set()

    def start(self):
        if self.threads:return
        for name,work in [('usb-control-monitor',self._monitor)]+[(f'usb-control-{i}',self._worker) for i in range(self.pool_size)]:
            thread=threading.Thread(target=work,name=name,daemon=True);self.threads.append(thread);thread.start()

    def _close_streams(self):
        with self.lock:streams=list(self.sockets)
        for connection in streams:
            try:connection.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            connection.close()

    def _monitor(self):
        while not self.done.is_set():
            try:present=self.target in self.enumerate_devices()
            except Exception:present=False
            if present:self.available.set()
            else:
                self.available.clear();self._close_streams()
            self.done.wait(1)

    def _worker(self):
        while not self.done.is_set():
            if not self.available.wait(.5):continue
            if self.done.is_set():break
            usb=local=None
            retry_delay=.05
            try:
                usb=self.connect(self.target,self.device_port)
                with self.lock:
                    self.sockets.add(usb);self.usb_sockets.add(usb)
                usb.settimeout(1)
                # Wait for the client's TLS ClientHello before connecting to the
                # HTTPS server, whose idle-handshake timeout is intentionally short.
                first=None
                while not self.done.is_set() and self.available.is_set():
                    try:first=usb.recv(65536);break
                    except socket.timeout:continue
                if not first:raise ConnectionError('USB stream closed before TLS')
                local=socket.create_connection(('127.0.0.1',self.server_port),timeout=3)
                with self.lock:self.sockets.add(local)
                local.sendall(first);usb.settimeout(3)
                while not self.done.is_set() and self.available.is_set():
                    readable,_,_=select.select([usb,local],[],[],.5)
                    ended=False
                    for source in readable:
                        data=source.recv(65536)
                        if not data:ended=True;break
                        (local if source is usb else usb).sendall(data)
                    if ended:break
            except (OSError,ValueError):retry_delay=1
            finally:
                with self.lock:
                    self.sockets.discard(usb);self.sockets.discard(local);self.usb_sockets.discard(usb)
                for connection in (usb,local):
                    if connection is not None:connection.close()
            self.done.wait(retry_delay)

    def stop(self):
        self.done.set();self.available.set();self._close_streams()
        for thread in self.threads:thread.join(timeout=2)
        self.threads=[]
