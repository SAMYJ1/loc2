"""Private authorization persistence; USB sessions and raw tokens are never stored."""
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile

LIMIT = 65536
MAX_GRANTS = 64
FIELDS = ('grantId','deviceId','label','createdAt')


class AuthorizationStorageError(ValueError):
    pass


def _validate(value):
    if not isinstance(value,dict) or value.get('version')!=1 or not isinstance(value.get('grants'),dict):
        raise ValueError('授权存储格式不正确')
    if len(value['grants'])>MAX_GRANTS: raise ValueError('授权存储数量超限')
    grants={}
    identifiers=set()
    for key,grant in value['grants'].items():
        if not isinstance(key,str) or not re.fullmatch('[0-9a-f]{64}',key) or not isinstance(grant,dict) or set(grant)!=set(FIELDS):
            raise ValueError('授权记录格式不正确')
        if not isinstance(grant['grantId'],str) or not re.fullmatch('[A-Za-z0-9_-]{24}',grant['grantId']) or grant['grantId'] in identifiers:
            raise ValueError('授权标识无效')
        identifiers.add(grant['grantId'])
        for field,limit in [('deviceId',256),('label',80)]:
            if not isinstance(grant[field],str) or not 1<=len(grant[field])<=limit or any(ord(c)<32 for c in grant[field]):
                raise ValueError('授权目标或名称无效')
        when=grant['createdAt']
        if isinstance(when,bool) or not isinstance(when,(int,float)) or not math.isfinite(when):
            raise ValueError('授权时间无效')
        grants[key]=dict(grant,requests={})
    return grants


class GrantStore:
    def __init__(self,path):
        self.path=Path(path) if path else None

    def _private_directory(self,create=False):
        directory=self.path.parent
        if create: directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        info=directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid():
            raise ValueError('授权目录必须是当前用户的私有目录')
        if create: os.chmod(directory,0o700)
        elif stat.S_IMODE(info.st_mode)&0o077:
            raise ValueError('授权目录权限须为 0700')

    def load(self):
        if not self.path: return {}
        if not self.path.parent.exists(): return {}
        try:
            self._private_directory()
            descriptor=os.open(self.path,os.O_RDONLY|os.O_NOFOLLOW)
        except FileNotFoundError: return {}
        except (OSError,ValueError):
            raise AuthorizationStorageError('授权存储不可安全读取；手机控制已停用，请检查本机授权文件') from None
        try:
            with os.fdopen(descriptor,'rb') as source:
                info=os.fstat(source.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077 or info.st_size>LIMIT:
                    raise ValueError('授权文件权限或大小不正确')
                raw=source.read(LIMIT+1)
            if len(raw)>LIMIT: raise ValueError('授权文件过大')
            return _validate(json.loads(raw))
        except (OSError,ValueError,TypeError):
            raise AuthorizationStorageError('授权存储损坏或权限不安全；手机控制已停用，原文件保持不变') from None

    def save(self,grants):
        if not self.path: return
        self._private_directory(create=True)
        if self.path.is_symlink(): raise ValueError('授权文件不能是符号链接')
        data=dict(version=1,grants={key:{field:grant[field] for field in FIELDS} for key,grant in grants.items()})
        _validate(data)
        payload=json.dumps(data,ensure_ascii=False,allow_nan=False).encode()
        if len(payload)>LIMIT: raise ValueError('授权存储已满，请撤销不用的控制端')
        descriptor,name=tempfile.mkstemp(prefix='.grants-',dir=self.path.parent)
        try:
            with os.fdopen(descriptor,'wb') as output:
                output.write(payload);output.flush();os.fsync(output.fileno())
            os.replace(name,self.path)
            directory=os.open(self.path.parent,os.O_RDONLY)
            try: os.fsync(directory)
            finally: os.close(directory)
        finally:
            if os.path.exists(name): os.unlink(name)
