import json
from pathlib import Path
import tempfile
import unittest

from loc2.runtime_bundle import bundled_workspace, import_authentication, runtime_status


class RuntimeBundleTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name)
        self.resources=self.root/'App/Contents/Resources/Runtime/resources'
        for name in ('engine/main.js','driver/livi-helperd','driver/loc2-capabilities.json','runtime/MacPlayReceiver.app/Contents/MacOS/MacPlayReceiver'):
            path=self.resources/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('{}')
        self.home=self.root/'home'

    def test_first_launch_uses_bundle_without_copying_private_identity(self):
        workspace=bundled_workspace(self.resources,self.home)
        self.assertEqual((workspace/'resources').resolve(),self.resources.resolve())
        self.assertEqual(runtime_status(workspace)['state'],'missing-authentication')
        self.assertFalse((workspace/'data/cp/macplay-v3/identity.json').exists())
        self.assertEqual((workspace/'data').stat().st_mode & 0o077,0)

    def test_app_move_preserves_private_state(self):
        workspace=bundled_workspace(self.resources,self.home)
        private=workspace/'data/cp/macplay-v3/identity.json';private.write_text('local-only')
        moved=self.root/'MovedResources';self.resources.rename(moved)
        self.assertEqual(bundled_workspace(moved,self.home),workspace)
        self.assertEqual((workspace/'resources').resolve(),moved.resolve())
        self.assertEqual(private.read_text(),'local-only')

    def test_import_is_private_idempotent_and_never_overwrites_identity(self):
        workspace=bundled_workspace(self.resources,self.home)
        source=self.root/'import';source.mkdir()
        for name in ('identity.pk8','certificate.p7b'): (source/name).write_bytes(b'synthetic-test-identity')
        import_authentication(workspace,source)
        self.assertTrue(runtime_status(workspace)['ready'])
        self.assertEqual((workspace/'data/authentication/identity.pk8').stat().st_mode & 0o077,0)
        import_authentication(workspace,source)
        (source/'identity.pk8').write_bytes(b'different')
        with self.assertRaisesRegex(ValueError,'未覆盖'): import_authentication(workspace,source)
        self.assertEqual((workspace/'data/authentication/identity.pk8').read_bytes(),b'synthetic-test-identity')
        self.assertFalse((workspace/'data/cp/macplay-v3/identity.json').exists())

    def test_missing_bundle_and_partial_auth_are_distinct(self):
        self.assertIsNone(bundled_workspace(self.root/'missing',self.home))
        self.assertEqual(runtime_status(None)['state'],'missing-runtime')
        workspace=bundled_workspace(self.resources,self.home)
        source=self.root/'partial';source.mkdir();(source/'identity.pk8').write_bytes(b'test')
        with self.assertRaises(ValueError): import_authentication(workspace,source)
        self.assertFalse((workspace/'data/authentication').exists())

    def test_existing_resources_directory_is_not_replaced(self):
        workspace=bundled_workspace(self.resources,self.home)
        (workspace/'resources').unlink();(workspace/'resources').mkdir()
        marker=workspace/'resources/user-file';marker.write_text('keep')
        with self.assertRaises(ValueError): bundled_workspace(self.resources,self.home)
        self.assertEqual(marker.read_text(),'keep')
