"""MapKit page configuration and explicit, locally validated coordinate policy."""
import copy
import math
import re


def public_settings(config):
    token=config.get('token')
    # Browser Maps JWT only. No signing key or unrelated local config crosses HTTP.
    if not isinstance(token,str) or len(token)>8192 or not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',token):
        token=None
    evidence=config.get('validationEvidence')
    validated=(config.get('coordinatePolicy')=='validated-wgs84' and
               isinstance(evidence,str) and bool(evidence.strip()) and len(evidence)<=2048)
    return dict(token=token,coordinatePolicy='validated-wgs84' if validated else 'unverified',canApplyMapPoints=validated)


def validate_map_point(point,config):
    if not public_settings(config)['canApplyMapPoints']:
        raise ValueError('Apple 地图坐标尚未完成 WGS84 校准，请使用手工坐标')
    if point.get('inputCRS')!='WGS84':
        raise ValueError('此地图草稿尚未校准，请重新选择或使用手工坐标')
    if point.get('selectionMethod') not in ('search','map-tap'):
        raise ValueError('地图选点来源无效')
    for key,limit in [('latitude',90),('longitude',180)]:
        value=point.get(key)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or abs(value)>limit:
            raise ValueError('地图坐标无效')
        for field in ('inputCoordinate','normalizedWGS84'):
            coordinates=point.get(field)
            if not isinstance(coordinates,dict) or isinstance(coordinates.get(key),bool) or coordinates.get(key)!=value:
                raise ValueError('地图输入、归一化坐标和目标不一致')
    return copy.deepcopy(point)
