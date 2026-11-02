import hashlib
import json
from pathlib import Path
import runpy
import tempfile
import unittest

PACKAGER=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/package-release.py'))

class ReleasePackagingTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name)
        for name in ('engine/main.js','driver/livi-helperd','runtime/MacPlayReceiver.app/Contents/MacOS/MacPlayReceiver'):
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'fixture-program')
        (self.root/'driver/loc2-capabilities.json').write_text(json.dumps({'schemaVersion':1,'wpa3Transition':True,'helperSHA256':hashlib.sha256(b'fixture-program').hexdigest()}))
    def test_rejects_credentials_and_external_links(self):
        PACKAGER['check_runtime_tree'](self.root)
        key=self.root/'identity.pk8';key.write_bytes(b'not-a-real-key')
        with self.assertRaisesRegex(ValueError,'Private'): PACKAGER['check_runtime_tree'](self.root)
        key.unlink();key.symlink_to('/nonexistent')
        with self.assertRaisesRegex(ValueError,'symlinks'): PACKAGER['check_runtime_tree'](self.root)
    def test_rejects_unmatched_capability_receipt(self):
        (self.root/'driver/livi-helperd').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'receipt'): PACKAGER['check_runtime_tree'](self.root)
