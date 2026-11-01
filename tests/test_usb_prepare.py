"""Offline checks at the preparation CLI; never loads the USB receiver."""
import json
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest

PREPARE = Path(__file__).resolve().parents[1] / 'tools/usb_validation/prepare.py'

class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'original'
        (self.source / 'engine').mkdir(parents=True)
        for name in ['driver', 'gstreamer', 'icons', 'runtime']:
            (self.source / name).mkdir()
        for name in ['CpHelperSock', 'ProjectionEnums', 'constants', 'discovery', 'display', 'frameRateFallback', 'microphonePermission', 'networkConfig', 'phoneSelection', 'runtimeControls', 'storage', 'videoHealth']:
            (self.source / ('engine/' + name + '.js')).write_text('')
        for name in ['node_modules', 'protocol']:
            (self.source / 'engine' / name).mkdir()
        # Minimal standalone engine fixture exercising the two presentation paths.
        (self.source / 'engine/media.js').write_text('''exports.addon = require('livi-gst-video');
function firstFrame(aspect) { exports.addon.macplayWindowHandle(aspect); }
function showVideoWindow(aspect) { exports.addon.macplayWindowHandle(aspect); }
''')
        (self.source / 'engine/main.js').write_text("console.log({ showCarPlay: true });\nconsole.log('首帧已解码，CarPlay画面窗口已打开');\nconsole.log('已接收CarPlay视频，画面窗口已打开');\n")
        (self.source / 'authentication').mkdir()
        (self.source / 'authentication/secret').write_text('private-test-data')
        self.dest = self.root / 'prepared'

    def invoke(self):
        return subprocess.run([sys.executable, str(PREPARE), '--resources', str(self.source), '--output', str(self.dest)], capture_output=True, text=True)

    def test_prepares_hidden_engine_without_linking_authentication_or_changing_source(self):
        original = (self.source / 'engine/media.js').read_bytes()
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.source / 'engine/media.js').read_bytes(), original)
        self.assertFalse((self.dest / 'resources/authentication').exists())
        self.assertFalse((self.dest / 'ARM_LOCATION').exists())
        manifest = json.loads((self.dest / 'preparation.json').read_text())
        self.assertFalse(manifest['receiverStarted'])
        self.assertEqual(manifest['positionAdoption'], 'unverified')
        self.assertNotIn('macplayWindowHandle(', (self.dest / 'resources/engine/media.js').read_text())
        self.assertTrue((self.dest / 'hidden-video.patch').exists())

    def test_rejects_unknown_engine_before_creating_output(self):
        (self.source / 'engine/media.js').write_text('unknown upstream engine')
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.dest.exists())

    def test_does_not_link_unrelated_engine_files(self):
        (self.source / 'engine/credentials.json').write_text('private-test-data')
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.dest / 'resources/engine/credentials.json').exists())

    @unittest.skipUnless(shutil.which('node'), 'Node is required to verify the prepared module graph')
    def test_protocol_and_top_level_events_reach_the_prepared_media_callback(self):
        package = self.source / 'engine/node_modules/livi-gst-video'
        package.mkdir()
        (package / 'index.js').write_text('module.exports = {};')
        (self.source / 'engine/protocol/probe.js').write_text(
            "exports.notify = () => require('../media').onVideo?.();")
        (self.source / 'engine/runtimeControls.js').write_text(
            "exports.notify = () => require('./media').onVideo?.();")
        (self.source / 'engine/protocol/private.json').write_text('private-test-data')
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        engine = self.dest / 'resources/engine'
        observed = subprocess.run(['node', '-e', '''
            const path = require('node:path');
            const root = process.argv[1];
            let signals = 0;
            require(path.join(root, 'media.js')).onVideo = () => signals++;
            require(path.join(root, 'protocol/probe.js')).notify();
            require(path.join(root, 'runtimeControls.js')).notify();
            if (signals !== 2) throw new Error('readiness signals did not reach prepared media: ' + signals);
        ''', str(engine)], capture_output=True, text=True)
        self.assertEqual(observed.returncode, 0, observed.stderr)
        self.assertFalse((engine / 'protocol/private.json').exists())

if __name__ == '__main__':
    unittest.main()
