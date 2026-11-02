"""Bundled program resources and private, per-Mac runtime state."""
import os
from pathlib import Path
import shutil
import stat
import tempfile

AUTH_FILES=('identity.pk8','certificate.p7b')


def _private_directory(path):
    path=Path(path)
    path.mkdir(mode=0o700,parents=True,exist_ok=True)
    info=path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:
        raise ValueError('运行时数据目录需要当前用户独享的 0700 权限')
    return path


def bundled_workspace(bundle_resources=None, home=None):
    resources=Path(bundle_resources) if bundle_resources else Path(__file__).resolve().parent.parent/'Runtime'/'resources'
    if not resources.is_dir(): return None
    if not (resources/'driver/loc2-capabilities.json').is_file():
        raise ValueError('App 内置运行时不完整，请重新下载完整安装包')
    root=_private_directory((Path(home) if home else Path.home())/'Library/Application Support/loc2/runtime-bundled')
    link=root/'resources'
    if link.exists() and not link.is_symlink():
        raise ValueError('内置运行时目录被其他文件占用，原内容保持不变')
    temporary=root/'.resources-next'
    if temporary.exists() or temporary.is_symlink(): temporary.unlink()
    temporary.symlink_to(resources.resolve(),target_is_directory=True)
    os.replace(temporary,link)
    data=_private_directory(root/'data')
    _private_directory(data/'cp')
    _private_directory(data/'cp/macplay-v3')
    return root


def runtime_status(workspace):
    if not workspace: return dict(ready=False,state='missing-runtime',message='当前 App 未包含定位运行时，请安装完整版或配置本机运行时')
    root=Path(workspace).expanduser()
    programs=('resources/runtime/MacPlayReceiver.app/Contents/MacOS/MacPlayReceiver',
              'resources/engine/main.js','resources/driver/livi-helperd')
    if any(not (root/name).is_file() for name in programs):
        return dict(ready=False,state='missing-runtime',message='定位运行时文件不完整，请重新安装完整版')
    if any(not (root/'data/authentication'/name).is_file() for name in AUTH_FILES):
        return dict(ready=False,state='missing-authentication',message='运行时已内置；请从 Mac 菜单导入本机认证材料，再应用位置')
    return dict(ready=True,state='ready',message='已找到运行时与本机认证文件')


def import_authentication(workspace, source):
    if not workspace: raise ValueError('请先安装包含运行时的完整版 App')
    source=Path(source).expanduser()
    # Accept either the authentication folder or the data folder selected by user.
    if (source/'authentication').is_dir(): source=source/'authentication'
    values={}
    for name in AUTH_FILES:
        path=source/name
        if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=1024*1024:
            raise ValueError('请选择含 identity.pk8 和 certificate.p7b 的认证目录')
        values[name]=path.read_bytes()
    data=_private_directory(Path(workspace).expanduser()/'data')
    target=data/'authentication'
    if target.exists() or target.is_symlink():
        if not target.is_symlink() and target.is_dir() and all((target/name).is_file() and (target/name).read_bytes()==value for name,value in values.items()):
            return
        raise ValueError('已存在认证材料，未覆盖；更换身份需先单独处理原有绑定')
    temporary=Path(tempfile.mkdtemp(prefix='.authentication-',dir=data))
    try:
        for name,value in values.items():
            path=temporary/name
            with path.open('xb') as file: file.write(value)
            path.chmod(0o600)
        os.rename(temporary,target)
    finally:
        if temporary.exists(): shutil.rmtree(temporary)
