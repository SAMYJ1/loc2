import base64
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from loc2.github_materials import download,fetch_materials,github_environment,GitHubAPI,DownloadError,REPOSITORY


class GitHubMaterialsTests(unittest.TestCase):
    def setUp(self):
        self.sha='a'*40;self.calls=[]
        self.files={'authentication/identity.pk8':b'synthetic-private-fixture','authentication/certificate.p7b':b'synthetic-certificate-fixture'}
        self.files['SHA256SUMS']=''.join(hashlib.sha256(data).hexdigest()+'  '+name+'\n' for name,data in self.files.items()).encode()
        self.private=True
    def api(self,endpoint):
        self.calls.append(endpoint)
        if endpoint=='repos/'+REPOSITORY:return {'private':self.private,'full_name':REPOSITORY}
        if endpoint.endswith('/git/ref/heads/main'):return {'object':{'type':'commit','sha':self.sha}}
        prefix='repos/'+REPOSITORY+'/contents/'
        self.assertTrue(endpoint.startswith(prefix));path,ref=endpoint[len(prefix):].split('?ref=')
        self.assertEqual(ref,self.sha)
        data=self.files[path]
        return {'type':'file','path':path,'encoding':'base64','size':len(data),'content':base64.b64encode(data).decode()}
    def test_same_commit_checksums_and_private_permissions(self):
        with tempfile.TemporaryDirectory() as folder:
            result=download(self.api,folder)
            for name in ('identity.pk8','certificate.p7b'):
                self.assertEqual((result/name).read_bytes(),self.files['authentication/'+name])
                self.assertEqual((result/name).stat().st_mode & 0o077,0)
            self.assertEqual(result.stat().st_mode & 0o077,0)
        self.assertEqual(len(self.calls),5)
    def test_rejects_public_repository_before_fetching_files(self):
        self.private=False
        with self.assertRaisesRegex(DownloadError,'Private'):fetch_materials(self.api)
        self.assertEqual(len(self.calls),1)
    def test_checksum_mismatch_writes_nothing(self):
        self.files['authentication/identity.pk8']=b'tampered'
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(DownloadError,'摘要不匹配'):download(self.api,folder)
            self.assertEqual(list(Path(folder).iterdir()),[])
    def test_rejects_extra_or_duplicate_checksum_entries(self):
        original=self.files['SHA256SUMS']
        for extra in (original.splitlines(keepends=True)[0],b'f'*64+b'  ../outside\n'):
            self.files['SHA256SUMS']=original+extra
            with self.assertRaises(DownloadError):fetch_materials(self.api)
    def test_bad_content_and_reference_are_rejected(self):
        for field,value in [('type','symlink'),('size',1024*1024+1),('encoding','none'),('content','!invalid')]:
            def bad(endpoint):
                result=self.api(endpoint)
                if '/contents/authentication/identity.pk8' in endpoint:result[field]=value
                return result
            with self.assertRaises(DownloadError):fetch_materials(bad)
    def test_debug_and_token_environment_are_not_inherited(self):
        with patch.dict(os.environ,{'GH_TOKEN':'private-token','GITHUB_TOKEN':'another','GH_DEBUG':'api'}):
            env=github_environment()
        self.assertNotIn('GH_TOKEN',env);self.assertNotIn('GITHUB_TOKEN',env);self.assertNotIn('GH_DEBUG',env)
    def test_cli_error_body_is_never_exposed(self):
        class Failed:
            returncode=1
            def communicate(self,timeout):return b'private-response',b'private-token'
            def poll(self):return 1
        with patch('loc2.github_materials.subprocess.Popen',return_value=Failed()):
            with self.assertRaises(DownloadError) as context:GitHubAPI('/fake/gh')('repos/'+REPOSITORY)
        self.assertNotIn('private-token',str(context.exception));self.assertNotIn('private-response',str(context.exception))
