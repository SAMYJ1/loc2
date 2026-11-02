"""Capabilities of the explicitly configured, locally installed runtime."""
import hashlib
import json
from pathlib import Path
import re


def supports_wpa3_transition(workspace):
    if not workspace:return False
    driver=Path(workspace).expanduser()/'resources/driver'
    try:
        manifest=driver/'location-lab-capabilities.json'
        if manifest.stat().st_size>4096:return False
        value=json.loads(manifest.read_text())
        if not isinstance(value,dict) or value.get('schemaVersion')!=1 or value.get('wpa3Transition') is not True:return False
        expected=value.get('helperSHA256')
        if not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected):return False
        helper=driver/'livi-helperd'
        if not 0<helper.stat().st_size<=64*1024*1024:return False
        return hashlib.sha256(helper.read_bytes()).hexdigest()==expected
    except (OSError,ValueError):return False
