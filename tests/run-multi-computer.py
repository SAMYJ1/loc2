#!/usr/bin/env python3
"""Two independently paired TLS services plus USB relay; no real device connections."""
from pathlib import Path
import json,socket,subprocess,sys,tempfile,threading,time
root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root),str(root/'tests')]
from location_lab.native_server import NativeServer,NativeHandler
from location_lab.phone import PhoneControl
from location_lab.session import SessionService
from location_lab.usb_control import USBControlBridge
from test_session import USBFixture

class RecordingHandler(NativeHandler):
    def handle_api(self,post):
        with self.server.control.lock:
            self.server.actions.append(self.path)
            self.server.tokens.append(self.headers.get('Authorization'))
        super().handle_api(post)

with tempfile.TemporaryDirectory(prefix='ll-multi-computer-') as directory:
    folder=Path(directory);servers=[];profiles=[];services=[];a_off=threading.Event()
    for label in ('a','b'):
        service=SessionService(USBFixture());service.refresh_devices();control=PhoneControl(service)
        challenge=control.create_pairing();request=control.request_pairing(dict(challenge=challenge['challenge'],pollSecret='f'*64,label='fixture'))
        control.approve(request['requestId']);_,token=control.poll_pairing(dict(requestId=request['requestId'],pollSecret='f'*64))
        server=NativeServer(('127.0.0.1',0),control,'localhost',folder/label)
        server.RequestHandlerClass=RecordingHandler;server.actions=[];server.tokens=[]
        threading.Thread(target=server.serve_forever,daemon=True).start();servers.append(server);services.append(service)
        profiles.append(dict(endpoint=f'https://localhost:{server.server_port}',fingerprint=server.fingerprint,token=token))
    with socket.socket() as reservation:reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
    bridge=USBControlBridge('test-phone',servers[1].server_port,device_port=port,enumerate_devices=lambda:['test-phone'],connect=lambda target,p:socket.create_connection(('127.0.0.1',p),timeout=2));bridge.start()
    finished=threading.Event()
    stalled=socket.socket();stalled.bind(('127.0.0.1',0));stalled.listen();stalled.settimeout(.2)
    (folder/'stalled-port').write_text(str(stalled.getsockname()[1]))
    stalled_clients=[]
    def blackhole():
        while not finished.is_set():
            try:connection,_=stalled.accept();stalled_clients.append(connection)
            except socket.timeout:continue
            except OSError:return
    threading.Thread(target=blackhole,daemon=True).start()
    def coordinate():
        while not finished.wait(.05):
            if (folder/'disable-a').exists():
                servers[0].shutdown();servers[0].server_close();a_off.set();(folder/'a-off').touch();return
    threading.Thread(target=coordinate,daemon=True).start()
    try:
        p=folder/'profiles.json';p.write_text(json.dumps(profiles));p.chmod(0o600)
        sources=['Models.swift','Coordinates.swift','Connection.swift','USBControlTunnel.swift','ComputerRegistry.swift','ComputerConnector.swift']
        sdk=subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()
        for probe in ('ComputerRegistryProbe','MultiComputerProbe'):
            executable=folder/probe
            command=['xcrun','swiftc','-sdk',sdk,'-parse-as-library',*[str(root/'native/LocationLabMobile'/n) for n in sources],str(root/f'tests/native/{probe}.swift'),'-o',str(executable),'-framework','CoreLocation']
            built=subprocess.run(command,capture_output=True,text=True)
            if built.returncode:print(built.stderr);raise SystemExit(built.returncode)
            subprocess.run([str(executable),str(folder),str(port)],check=True,timeout=45)
        assert '/v1/apply' not in servers[0].actions and '/v1/stop' not in servers[0].actions
        assert servers[1].actions.count('/v1/apply')==1 and servers[1].actions.count('/v1/stop')==1
        assert 'Bearer '+profiles[0]['token'] not in servers[1].tokens
        assert 'Bearer '+profiles[1]['token'] not in servers[0].tokens
        assert not any(token and 'never-transmit-fixture-' in token for server in servers for token in server.tokens)
        print('PASS: no cross-computer tokens and no extra apply/stop requests')
    finally:
        finished.set();bridge.stop();stalled.close()
        for connection in stalled_clients:connection.close()
        for index,server in enumerate(servers):
            if index!=0 or not a_off.is_set():server.shutdown();server.server_close()
        for service in services:service.shutdown()
