#!/usr/bin/env python3
"""Exercise the actual Swift pinning delegate against a freshly generated TLS server."""
from pathlib import Path
import sys,tempfile,subprocess,json,threading
root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root),str(root/'tests')]
from location_lab.native_server import NativeServer
from location_lab.phone import PhoneControl
from location_lab.session import SessionService
from test_session import USBFixture
with tempfile.TemporaryDirectory(prefix='ll-tls-') as directory:
    folder=Path(directory);service=SessionService(USBFixture());control=PhoneControl(service)
    server=NativeServer(('127.0.0.1',0),control,'LOCALHOST',folder)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        profile=folder/'profile.json';profile.write_text(json.dumps(dict(endpoint=f'https://LOCALHOST:{server.server_port}',fingerprint=server.fingerprint)))
        executable=folder/'probe'
        sources=['Models.swift','Coordinates.swift','Connection.swift','USBControlTunnel.swift']
        sdk=subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()
        arch=subprocess.check_output(['uname','-m'],text=True).strip()
        compile_result=subprocess.run(['xcrun','swiftc','-sdk',sdk,'-target',arch+'-apple-macosx13.0','-parse-as-library',*[str(root/'native/LocationLabMobile'/name) for name in sources],str(root/'tests/native/TLSProbe.swift'),'-o',str(executable),'-framework','CoreLocation'],capture_output=True,text=True)
        if compile_result.returncode:
            print(compile_result.stderr,file=sys.stderr);raise SystemExit(compile_result.returncode)
        subprocess.run([str(executable),str(profile)],check=True)
    finally:server.shutdown();server.server_close()
