import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from loc2.runtime_capabilities import supports_wpa3_transition


class RuntimeCapabilityTests(unittest.TestCase):
    def test_capability_is_bound_to_the_installed_helper_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);driver=root/'resources/driver';driver.mkdir(parents=True)
            helper=driver/'livi-helperd';helper.write_bytes(b'tested-fixture')
            manifest=driver/'loc2-capabilities.json'
            self.assertFalse(supports_wpa3_transition(root))
            manifest.write_text(json.dumps(dict(schemaVersion=1,wpa3Transition=True,
                helperSHA256=hashlib.sha256(helper.read_bytes()).hexdigest())))
            self.assertTrue(supports_wpa3_transition(root))
            helper.write_bytes(b'replaced-fixture')
            self.assertFalse(supports_wpa3_transition(root))
            manifest.write_text('{}')
            self.assertFalse(supports_wpa3_transition(root))
