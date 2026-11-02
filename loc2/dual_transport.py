"""One authorized phone, with USB preferred when starting an explicit session."""
import subprocess


class DualTransportBackend:
    def __init__(self, usb, wireless, target_usb):
        if not isinstance(target_usb,str) or not target_usb:
            raise ValueError('双通道模式需要绑定目标 iPhone 的 USB 标识')
        self.usb,self.wireless,self.target_usb=usb,wireless,target_usb
        # Preserve existing wireless grants when adding the wired transport.
        self.device_id=wireless.device_id
        self.legacy_device_id=target_usb
        self.current_network=wireless.current_network
        self.active=None
        self.selected=None
        self.prepared=None
        self.unavailable_reason=None
        self.disconnect_reason=None
        self.awake=None

    @property
    def lane(self):
        backend=self.active or self.selected
        return getattr(backend,'lane','unavailable')

    @property
    def available_lane(self): return getattr(self.selected,'lane',None)

    transport_policy='usb-preferred'

    @property
    def run(self): return getattr(self.active,'run',None)

    @property
    def requires_network(self): return self.lane!='usb'

    def device_ids(self):
        wired=self.usb.device_ids()
        if self.target_usb in wired:
            preferred=self.usb
            hint=None
        elif self.wireless.device_id in self.wireless.device_ids():
            preferred=self.wireless
            hint=self.wireless.unavailable_reason
        else:
            preferred=None
            hint=self.wireless.unavailable_reason
        self.selected=preferred
        self.unavailable_reason=hint
        self.disconnect_reason=None
        if self.active is not None and preferred is not self.active:
            self.disconnect_reason='transport-changed'
            self.unavailable_reason='连接通道已变化，本次报点已停止；请重新应用位置'
            return []
        return [self.device_id] if preferred is not None else []

    def prepare_for_apply(self):
        if self.device_ids()!=[self.device_id]:raise ValueError(self.unavailable_reason or '目标 iPhone 不可用')
        if self.selected is self.wireless:self.wireless.prepare_for_apply()
        self.prepared=self.selected

    def start(self,session_id,device_id,emit):
        if self.active is not None:raise RuntimeError('已有定位会话')
        if device_id!=self.device_id or self.device_ids()!=[self.device_id]:raise ValueError('目标 iPhone 不可用')
        if self.prepared is not self.selected:raise ValueError('连接通道已变化，请重新应用位置')
        self.prepared=None
        self.active=self.selected
        try:
            self.active.start(session_id,self.target_usb if self.active is self.usb else self.wireless.device_id,emit)
            process=getattr(self.active,'process',None)
            if self.active is self.usb and process is not None:
                self.awake=subprocess.Popen(['/usr/bin/caffeinate','-i','-w',str(process.pid)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except Exception:
            self.stop();raise

    def send(self,frame):
        if self.active is None:raise ConnectionError('定位会话未启动')
        # Recheck the physical path before every send; never silently fall back.
        if self.device_ids()!=[self.device_id]:raise ConnectionError('定位通道已变化')
        self.active.send(frame)

    def take_stop_request(self):
        return getattr(self.active,'take_stop_request',lambda:None)()

    def stop(self):
        backend,self.active=self.active,None
        self.prepared=None
        if backend is not None:backend.stop()
        if self.awake:
            if self.awake.poll() is None:self.awake.terminate()
            try:self.awake.wait(timeout=3)
            except subprocess.TimeoutExpired:self.awake.kill();self.awake.wait()
        self.awake=None
