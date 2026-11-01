"""Read sanitized local diagnostics or request stop for exactly the observed run."""
import argparse
import json
import os
from pathlib import Path
import stat
import time
import tempfile


def request_stop(snapshot):
    if not snapshot.get('sessionActive'): return False
    path=Path(snapshot.get('stopFile') or '')
    # Never create a missing run directory or redirect a stop toward another path.
    if path.name!='STOP' or not path.parent.name.startswith('ll-') or path.parent.parent!=Path('/tmp'):
        raise ValueError('停止路径无效')
    info=path.parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:
        raise ValueError('会话目录不可安全访问')
    fd,name=tempfile.mkstemp(prefix='.stop-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as file:
            json.dump({key:snapshot.get(key) for key in ('sessionId','controlEpoch','controlRevision')},file)
            file.flush();os.fsync(file.fileno())
        # Publish a complete request atomically; do not overwrite another stop.
        os.link(name,path)
    finally:
        os.unlink(name)
    return True


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['status','stop'])
    parser.add_argument('--config',type=Path,default=Path.home()/'.config/location-lab/config.json')
    args=parser.parse_args()
    configuration=json.loads(args.config.read_text())
    path=Path(configuration.get('stateDirectory',args.config.parent)).expanduser()/'latest-status.private.json'
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd) as source:
        info=os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077 or info.st_size>65536:
            raise ValueError('诊断文件不可安全读取')
        snapshot=json.load(source)
    if time.time()-snapshot['updatedAt']>5:raise ValueError('服务状态已过期，不执行停止')
    if args.action=='stop':
        print('已请求停止当前会话' if request_stop(snapshot) else '当前没有活动会话')
    else:
        print(json.dumps({k:v for k,v in snapshot.items() if k not in ['stopFile','sessionId','controlEpoch']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
