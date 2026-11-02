"""Fresh-machine pairing through the real JSONL host and native TLS service."""
import json
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import unittest

from loc2.local_host import runtime_config


class FirstLaunchTests(unittest.TestCase):
    def test_missing_config_creates_native_pairing_and_keeps_identity(self):
        # Only hardware/network discovery is substituted. The host, TLS identity,
        # pairing challenge and persistent storage are production implementations.
        script = '''
from unittest.mock import patch
from loc2 import local_host
from loc2.native_server import NativeServer
def current_address(interface):
    assert interface is None
    return '127.0.0.1'
with patch.object(local_host.USBBackend, 'device_ids', return_value=[]), \\
     patch.object(local_host, 'interface_address', side_effect=current_address), \\
     patch.object(local_host, 'NativeServer', type('EphemeralServer', (NativeServer,), {
         '__init__': lambda self, address, control, host, state_dir:
             NativeServer.__init__(self, (address[0], 0), control, host, state_dir)
     })):
    local_host.main()
'''
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)/'fresh'/'config.json'
            fingerprints = []
            for _ in range(2):
                process = subprocess.Popen([sys.executable, '-c', script, '--config', str(config)],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    process.stdin.write('{"id":1,"action":"pairing-create"}\n')
                    process.stdin.flush()
                    with selectors.DefaultSelector() as selector:
                        selector.register(process.stdout, selectors.EVENT_READ)
                        self.assertTrue(selector.select(10), 'Host did not respond')
                    response = json.loads(process.stdout.readline())
                    self.assertTrue(response['ok'], response.get('error'))
                    self.assertTrue(response['phone']['pairingURL'].startswith('loc2://pair?data='))
                    self.assertEqual(response['phone']['transport'], 'native-tls')
                    fingerprints.append(response['phone']['serverFingerprint'])
                    self.assertIsNone(response['status']['sessionId'])
                finally:
                    if process.poll() is None:
                        process.stdin.write('{"action":"quit"}\n');process.stdin.flush()
                    try: process.communicate(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill();process.communicate();raise
                self.assertEqual(process.returncode, 0)
            self.assertEqual(fingerprints[0], fingerprints[1])
            self.assertFalse(config.exists(), 'Defaults must not overwrite user configuration')
            self.assertEqual((config.parent/'tls/server.key.pem').stat().st_mode & 0o077, 0)

    def test_explicit_phone_settings_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'config.json'
            for config in ({'nativePhone': False}, {'phone': {'bindAddress': '127.0.0.1'}},
                           {'nativePhone': {'interface': 'en7', 'port': 9876}}):
                path.write_text(json.dumps(config))
                self.assertEqual(runtime_config(path), config)

    def test_runtime_only_config_also_enables_native_pairing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'config.json'
            path.write_text('{"runtime":"/example/runtime"}')
            config = runtime_config(path)
            self.assertTrue(config.get('nativePhone'))
            self.assertEqual(config['nativePhone'], {'port': 8767})
            self.assertEqual(config['runtime'], '/example/runtime')
            self.assertEqual(json.loads(path.read_text()), {'runtime': '/example/runtime'})
