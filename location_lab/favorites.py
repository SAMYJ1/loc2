"""Private Mac favorite storage; saving a draft never applies it to a session."""
import copy
import json
import math
import os
from pathlib import Path
import tempfile
import time
import uuid


class FavoritesStorageError(ValueError):
    """Safe startup/write error text, without filesystem paths or file contents."""


def validate_draft(point):
    if not isinstance(point,dict): raise ValueError('收藏位置必须为坐标对象')
    result=copy.deepcopy(point)
    def coordinate(value):
        if not isinstance(value,dict): raise ValueError('收藏坐标缺少来源信息')
        for key,limit in (('latitude',90),('longitude',180)):
            n=value.get(key)
            if isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n) or abs(n)>limit:
                raise ValueError('收藏坐标无效')
        return {key:value[key] for key in ('latitude','longitude')}
    actual=coordinate(result)
    provider=result.get('provider')
    crs=result.get('inputCRS')
    if provider=='manual' and crs=='WGS84':
        if coordinate(result.get('inputCoordinate'))!=actual or coordinate(result.get('normalizedWGS84'))!=actual:
            raise ValueError('收藏坐标与来源信息不一致')
    elif provider=='apple-mapkit-js' and crs in ('unverified-mapkit','WGS84'):
        if coordinate(result.get('inputCoordinate'))!=actual:
            raise ValueError('收藏坐标与来源信息不一致')
        if crs=='unverified-mapkit':
            if result.get('normalizedWGS84') is not None: raise ValueError('未校准地图坐标不能声明归一化结果')
        elif coordinate(result.get('normalizedWGS84'))!=actual:
            raise ValueError('收藏坐标与归一化结果不一致')
        if result.get('selectionMethod') not in ('search','map-tap'):
            raise ValueError('地图收藏缺少选点来源')
    else: raise ValueError('收藏坐标来源或参考系未明确')
    # Keep the declared coordinate metadata; storage does not attest calibration.
    if len(json.dumps(result,allow_nan=False).encode())>4096: raise ValueError('收藏位置数据过大')
    return result


class FavoritesStore:
    def __init__(self,path=None):
        self.path=Path(path) if path is not None else None
        self.devices={}
        if self.path is not None and self.path.is_symlink():
            raise FavoritesStorageError('Mac 收藏文件无法读取；请保留原文件并检查本机配置')
        if self.path is not None and self.path.exists():
            try:
                if self.path.is_symlink() or self.path.stat().st_size>1024*1024:
                    raise ValueError('invalid file')
                saved=json.loads(self.path.read_text())
                if saved.get('version')!=1 or not isinstance(saved.get('devices'),dict): raise ValueError('invalid schema')
                for device,items in saved['devices'].items():
                    if not isinstance(device,str) or not isinstance(items,list) or len(items)>100: raise ValueError('invalid entries')
                    for item in items:
                        if not isinstance(item,dict) or not isinstance(item.get('id'),str) or not isinstance(item.get('name'),str): raise ValueError('invalid favorite')
                        validate_draft(item.get('point'))
                self.devices=saved['devices']
            except (ValueError,TypeError,AttributeError,OSError):
                raise FavoritesStorageError('Mac 收藏文件无法读取；请保留原文件并检查本机配置') from None

    def list(self,device_id):
        return copy.deepcopy(self.devices.get(device_id,[]))

    def _save(self,devices):
        try:
            self._write(devices)
        except OSError:
            raise FavoritesStorageError('Mac 收藏无法保存，请检查本机存储空间与权限') from None

    def _write(self,devices):
        if self.path is not None:
            if self.path.is_symlink(): raise FavoritesStorageError('Mac 收藏路径已变化，请检查本机配置')
            self.path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            data=json.dumps(dict(version=1,devices=devices),ensure_ascii=False,allow_nan=False).encode()
            if len(data)>1024*1024: raise ValueError('Mac 收藏数据过大')
            descriptor,name=tempfile.mkstemp(prefix='.favorites-',suffix='.tmp',dir=self.path.parent)
            try:
                with os.fdopen(descriptor,'wb') as output:
                    output.write(data);output.flush();os.fsync(output.fileno())
                os.replace(name,self.path)
            finally:
                if os.path.exists(name): os.unlink(name)
        self.devices=devices

    def add(self,device_id,name,point):
        if not isinstance(name,str) or not 1<=len(name.strip())<=80 or any(ord(char)<32 for char in name):
            raise ValueError('请填写 1–80 个字符的收藏名称')
        point=validate_draft(point)
        devices=copy.deepcopy(self.devices)
        items=devices.setdefault(device_id,[])
        if len(items)>=100: raise ValueError('该手机最多保存 100 个常用点')
        items.append(dict(id=str(uuid.uuid4()),name=name.strip(),point=point,createdAt=int(time.time())))
        self._save(devices)
        return self.list(device_id)

    def remove(self,device_id,favorite_id):
        if not isinstance(favorite_id,str): raise ValueError('收藏标识无效')
        devices=copy.deepcopy(self.devices)
        items=devices.get(device_id,[])
        if not any(item['id']==favorite_id for item in items): raise ValueError('该收藏不存在')
        devices[device_id]=[item for item in items if item['id']!=favorite_id]
        self._save(devices)
        return self.list(device_id)
