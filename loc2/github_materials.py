"""Download the fixed private authentication repository through the official gh client.

No token is read, printed, passed on a command line or stored by this module.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess

REPOSITORY='SAMYJ1/loc2-private-auth'
FILES=('authentication/identity.pk8','authentication/certificate.p7b')
LIMIT=1024*1024


class DownloadError(ValueError): pass


def github_environment():
    env=dict(os.environ)
    for name in ('GH_TOKEN','GITHUB_TOKEN','GH_ENTERPRISE_TOKEN','GITHUB_ENTERPRISE_TOKEN','GH_DEBUG','GH_CONFIG_DIR','GH_HOST','GH_FORCE_TTY'):
        env.pop(name,None)
    env.update(GH_PROMPT_DISABLED='1',GH_NO_UPDATE_NOTIFIER='1',GH_PAGER='cat',NO_COLOR='1')
    return env


class GitHubAPI:
    def __init__(self, executable): self.executable=executable;self.child=None
    def stop(self):
        if self.child is not None and self.child.poll() is None:
            self.child.terminate()
            try: self.child.wait(timeout=3)
            except subprocess.TimeoutExpired: self.child.kill();self.child.wait()
    def __call__(self, endpoint):
        args=[self.executable,'api','--hostname','github.com','--method','GET','-H','Accept: application/vnd.github+json',endpoint]
        self.child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=github_environment())
        try:
            output,_=self.child.communicate(timeout=40)
            if self.child.returncode:
                raise DownloadError('无法读取私有仓库；请确认登录账号有访问权限，或重新登录')
            if len(output)>2*LIMIT: raise DownloadError('仓库响应超过允许大小')
            value=json.loads(output)
            if not isinstance(value,dict): raise DownloadError('仓库响应格式不正确')
            return value
        except subprocess.TimeoutExpired:
            self.child.kill();self.child.communicate()
            raise DownloadError('GitHub 请求超时，请检查网络后重试') from None
        except (ValueError,UnicodeError) as error:
            if isinstance(error,DownloadError): raise
            raise DownloadError('GitHub 响应无法校验') from None
        finally:
            self.stop();self.child=None


def decode_file(value, path, limit=LIMIT):
    if value.get('type')!='file' or value.get('path')!=path or value.get('encoding')!='base64':
        raise DownloadError('仓库文件格式不正确')
    if type(value.get('size')) is not int or not 0<value['size']<=limit:
        raise DownloadError('仓库文件大小不符合要求')
    try: content=base64.b64decode(''.join(value['content'].split()),validate=True)
    except (KeyError,ValueError,AttributeError): raise DownloadError('仓库文件编码不正确') from None
    if len(content)!=value['size']: raise DownloadError('仓库文件不完整')
    return content


def fetch_materials(api):
    metadata=api('repos/'+REPOSITORY)
    if metadata.get('private') is not True or metadata.get('full_name','').lower()!=REPOSITORY.lower():
        raise DownloadError('认证仓库必须保持 Private，已停止下载')
    reference=api('repos/'+REPOSITORY+'/git/ref/heads/main')
    commit=reference.get('object',{}).get('sha')
    if reference.get('object',{}).get('type')!='commit' or not isinstance(commit,str) or not re.fullmatch('[0-9a-f]{40}',commit):
        raise DownloadError('无法锁定认证仓库提交')
    def fetch(path,limit=LIMIT):
        return decode_file(api('repos/'+REPOSITORY+'/contents/'+path+'?ref='+commit),path,limit)
    try: checksum=fetch('SHA256SUMS',4096).decode('ascii')
    except UnicodeError: raise DownloadError('仓库校验文件格式不正确') from None
    expected={}
    for line in checksum.splitlines():
        match=re.fullmatch(r'([0-9a-f]{64})  (authentication/(?:identity\.pk8|certificate\.p7b))',line)
        if not match or match[2] in expected: raise DownloadError('仓库校验文件包含无效或重复条目')
        expected[match[2]]=match[1]
    if set(expected)!=set(FILES): raise DownloadError('仓库校验文件不完整')
    values={}
    for path in FILES:
        data=fetch(path)
        if hashlib.sha256(data).hexdigest()!=expected[path]: raise DownloadError('认证材料摘要不匹配，未导入')
        values[Path(path).name]=data
    return values


def download(api, output):
    output=Path(output)
    if output.is_symlink() or not output.is_dir() or output.stat().st_uid!=os.getuid() or output.stat().st_mode&0o077:
        raise DownloadError('临时下载目录必须为当前用户私有目录')
    values=fetch_materials(api)
    destination=output/'authentication';destination.mkdir(mode=0o700,exist_ok=False)
    for name,data in values.items():
        path=destination/name
        descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(descriptor,'wb') as file: file.write(data)
    return destination


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--gh',required=True);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    api=GitHubAPI(args.gh)
    def cancel(_signal,_frame): api.stop();raise SystemExit(130)
    signal.signal(signal.SIGTERM,cancel);signal.signal(signal.SIGINT,cancel)
    try:
        download(api,args.output)
        print(json.dumps({'ok':True,'message':'认证材料已下载并通过摘要校验'},ensure_ascii=False),flush=True)
    except DownloadError as error:
        print(json.dumps({'ok':False,'message':str(error)},ensure_ascii=False),flush=True);raise SystemExit(1)
    except Exception:
        print(json.dumps({'ok':False,'message':'下载未完成，未导入认证材料，请重试'},ensure_ascii=False),flush=True);raise SystemExit(1)


if __name__=='__main__': main()
