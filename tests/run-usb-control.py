#!/usr/bin/env python3
"""Real Swift relay + HTTPS round trip with an in-memory device and local USB stand-in."""
from pathlib import Path
import json,socket,subprocess,sys,tempfile,threading
root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root),str(root/'tests')]
from location_lab.native_server import NativeServer,tls_identity
from location_lab.phone import PhoneControl
from location_lab.session import SessionService
from location_lab.usb_control import USBControlBridge
from test_session import USBFixture

with tempfile.TemporaryDirectory(prefix='ll-usb-control-') as directory:
    folder=Path(directory)
    service=SessionService(USBFixture());service.refresh_devices();control=PhoneControl(service)
    invitation=control.create_pairing()
    request=control.request_pairing(dict(challenge=invitation['challenge'],pollSecret='a'*64,label='test client'))
    control.approve(request['requestId'])
    _,token=control.poll_pairing(dict(requestId=request['requestId'],pollSecret='a'*64))
    # Reuse a LAN certificate that intentionally does not name the relay's loopback IP.
    tls_identity(folder/'tls','usb-fixture.invalid','192.0.2.2')
    server=NativeServer(('127.0.0.1',0),control,'usb-fixture.invalid',folder)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1',0));device_port=reservation.getsockname()[1]
    bridge=USBControlBridge('test-phone',server.server_port,device_port=device_port,
        enumerate_devices=lambda:['test-phone'],connect=lambda target,port:socket.create_connection(('127.0.0.1',port),timeout=2))
    bridge.start()
    try:
        profile=folder/'profile.json';profile.write_text(json.dumps(dict(endpoint='https://usb-fixture.invalid:9',fingerprint=server.fingerprint,token=token)));profile.chmod(0o600)
        executable=folder/'probe'
        sources=['Models.swift','Coordinates.swift','Connection.swift','USBControlTunnel.swift']
        sdk=subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()
        compile_result=subprocess.run(['xcrun','swiftc','-sdk',sdk,'-parse-as-library',*[str(root/'native/LocationLabMobile'/name) for name in sources],str(root/'tests/native/USBControlProbe.swift'),'-o',str(executable),'-framework','CoreLocation'],capture_output=True,text=True)
        if compile_result.returncode:print(compile_result.stderr,file=sys.stderr);raise SystemExit(compile_result.returncode)
        subprocess.run([str(executable),str(profile),str(device_port)],check=True,timeout=45)
    finally:bridge.stop();server.shutdown();server.server_close();service.shutdown()
