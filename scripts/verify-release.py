#!/usr/bin/env python3
"""Verify release hashes, signatures and an isolated, credential-free first launch."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import selectors
import subprocess
import tarfile
import tempfile
import zipfile

parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);args=parser.parse_args()
folder=args.directory.resolve()
for line in (folder/'SHA256SUMS').read_text().splitlines():
    expected,name=line.split('  ',1)
    assert Path(name).name==name
    assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==expected,name
for archive in folder.glob('*.zip'):
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert not any(Path(name).suffix in ('.pk8','.p7b','.p12','.key') or Path(name).name in ('identity.json','grants.json') for name in z.namelist())
for archive in folder.glob('*.tar.gz'):
    with tarfile.open(archive) as t:
        assert not any(Path(m.name).suffix in ('.pk8','.p7b','.p12','.key') or '.private.' in m.name or '/authentication/' in m.name for m in t)
with tempfile.TemporaryDirectory(prefix='loc2-release-smoke-') as temp:
    root=Path(temp)
    subprocess.run(['ditto','-x','-k',str(next(folder.glob('*macOS-arm64.zip'))),str(root)],check=True)
    app=root/'Loc2.app';resources=app/'Contents/Resources'
    subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
    runtime=resources/'Runtime/resources'
    receiver=runtime/'runtime/MacPlayReceiver.app/Contents/MacOS/MacPlayReceiver'
    env=dict(os.environ,MACPLAY_RESOURCES=str(runtime),MACPLAY_DATA=str(root/'probe-data'),GST_REGISTRY=str(root/'gst-registry.bin'),DYLD_LIBRARY_PATH=str(runtime/'gstreamer/macos-arm64/lib'))
    probe=subprocess.run([str(receiver),'-e',"require(process.env.MACPLAY_RESOURCES+'/engine/media.js'); console.log('media-addon-ok')"],env=env,capture_output=True,text=True,timeout=20)
    if probe.returncode or 'media-addon-ok' not in probe.stdout: raise RuntimeError('Relocated media load failed: '+probe.stderr[-2000:])
    gh=resources/'GitHubCLI/bin/gh'
    gh_version=subprocess.check_output([str(gh),'--version'],text=True).splitlines()[0]
    assert gh_version.startswith('gh version ')
    python=resources/'Python/bin/python3'
    version=subprocess.check_output([str(python),'--version'],text=True).strip()
    script='''
from unittest.mock import patch
from loc2 import local_host
from loc2.native_server import NativeServer
class Ephemeral(NativeServer):
    def __init__(self,address,control,host,state_dir):
        super().__init__((address[0],0),control,host,state_dir)
with patch.object(local_host.USBBackend,'device_ids',return_value=[]), patch.object(local_host,'interface_address',return_value='127.0.0.1'), patch.object(local_host,'NativeServer',Ephemeral):
    local_host.main()
'''
    home=root/'fresh-home';home.mkdir()
    process=subprocess.Popen([str(python),'-c',script],cwd=resources,env=dict(os.environ,HOME=str(home),PYTHONPATH=str(resources),PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1'),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        process.stdin.write('{"action":"pairing-create"}\n');process.stdin.flush()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout,selectors.EVENT_READ)
            assert selector.select(20),'Fresh host timed out'
        line=process.stdout.readline()
        if not line: raise RuntimeError(process.stderr.read())
        reply=json.loads(line)
        assert reply['ok'],reply.get('error')
        assert reply['phone']['pairingURL'].startswith('loc2://pair?data=')
        assert reply['runtime']['state']=='missing-authentication',reply['runtime']
        assert reply['status']['sessionId'] is None
        assert not (home/'Library/Application Support/loc2/runtime-bundled/data/authentication').exists()
    finally:
        if process.poll() is None:
            process.stdin.write('{"action":"quit"}\n');process.stdin.flush()
        try: process.communicate(timeout=10)
        except subprocess.TimeoutExpired: process.kill();process.communicate();raise
    assert process.returncode==0
    subprocess.run(['ditto','-x','-k',str(next(folder.glob('*.ipa'))),str(root/'ios')],check=True)
    subprocess.run(['codesign','--verify','--strict',str(root/'ios/Payload/Loc2.app')],check=True)
print('PASS: archive hashes, no authentication assets, relocated signatures, '+version+', relocated media addon, isolated first-launch QR pairing, iOS signature')
