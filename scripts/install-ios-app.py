#!/usr/bin/env python3
"""Build/reinstall this app using a private, selected-device development configuration."""
import argparse,json,os,re,signal,subprocess,sys,time
from pathlib import Path

parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path,default=Path.home()/'.config/location-lab/config.json');args=parser.parse_args()
current=None

def emit(stage,ok=True):print(json.dumps(dict(stage=stage,ok=ok),ensure_ascii=False),flush=True)
def inactive(config):
    path=Path(config.get('stateDirectory',args.config.parent))/'latest-status.private.json'
    if path.exists():
        value=json.loads(path.read_text())
        if time.time()-value.get('updatedAt',0)<5 and value.get('sessionActive'):raise ValueError('请先恢复位置，再更新手机 App')

def stop_child():
    if current and current.poll() is None:
        try:os.killpg(current.pid,signal.SIGTERM);current.wait(timeout=3)
        except (ProcessLookupError,subprocess.TimeoutExpired):
            try:os.killpg(current.pid,signal.SIGKILL)
            except ProcessLookupError:pass

def interrupted(signum,frame):stop_child();raise SystemExit(130)
signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
try:
    config=json.loads(args.config.read_text());mobile=config['mobile'];project=Path(mobile['projectRoot']).expanduser().resolve()
    team,device=mobile['teamID'],mobile['deviceID']
    if not re.fullmatch('[A-Z0-9]{10}',team) or not re.fullmatch('[A-Za-z0-9.-]{1,128}',device):raise ValueError('本机签名或目标设备配置无效')
    if not (project/'scripts/build-ios-app.sh').is_file():raise ValueError('找不到本机开发项目，请检查 projectRoot')
    inactive(config)
    log_path=args.config.parent/'install-last.private.log'
    fd=os.open(log_path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600);os.fchmod(fd,0o600)
    with os.fdopen(fd,'w') as log:
        commands=[('正在构建并更新开发签名',['sh',str(project/'scripts/build-ios-app.sh'),'device'],600),
                  ('正在安装到已绑定的 iPhone',['xcrun','devicectl','device','install','app','--device',device,str(project/'build/ios-device/Build/Products/Debug-iphoneos/toAnywhere.app')],120)]
        for stage,command,timeout in commands:
            inactive(config);emit(stage)
            current=subprocess.Popen(command,cwd=project,env=dict(os.environ,LOCATION_LAB_TEAM=team),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            try:code=current.wait(timeout=timeout)
            except subprocess.TimeoutExpired:stop_child();raise ValueError('更新超时，请确认手机解锁、同网并在 Xcode 登录')
            if code:raise ValueError('更新未完成，请在 Mac 查看安装诊断，确认手机连接及开发者账号')
    emit('手机 App 已更新，现有收藏和授权保留')
except (ValueError,KeyError,OSError) as error:
    emit(str(error) if isinstance(error,ValueError) else '本机安装配置不完整，请检查开发环境',False);sys.exit(1)
finally:stop_child()
