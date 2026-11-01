"""Pinned-TLS native control API. Shares authorization/session rules with the web client."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import tempfile
import threading
from .phone import RequestError
from .maps import public_settings


def tls_identity(directory,host,address):
    directory=Path(directory)
    directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    if directory.is_symlink() or directory.stat().st_uid!=os.getuid() or directory.stat().st_mode&0o077:
        raise ValueError('服务身份目录必须为当前用户私有目录')
    cert,key=directory/'server.cert.pem',directory/'server.key.pem'
    if cert.exists()!=key.exists(): raise ValueError('服务身份不完整，不能静默更换已配对身份')
    if not cert.exists():
        config='[req]\ndistinguished_name=dn\nx509_extensions=ext\nprompt=no\n[dn]\nCN=Location Lab Local\n[ext]\nsubjectAltName=DNS:'+host+',IP:'+address+'\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n'
        descriptor,name=tempfile.mkstemp(dir=directory,prefix='.tls-')
        try:
            with os.fdopen(descriptor,'w') as file: file.write(config)
            result=subprocess.run(['/usr/bin/openssl','req','-x509','-newkey','rsa:2048','-nodes','-sha256','-days','365','-keyout',str(key),'-out',str(cert),'-config',name],capture_output=True,timeout=20)
            if result.returncode: raise ValueError('无法创建本机TLS身份')
            key.chmod(0o600);cert.chmod(0o600)
        finally: os.unlink(name)
    for path in (key,cert):
        if path.is_symlink() or not path.is_file() or path.stat().st_uid!=os.getuid() or path.stat().st_mode&0o077:
            raise ValueError('服务身份文件权限不安全')
    fingerprint=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert.read_text())).hexdigest()
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert,key)
    return context,fingerprint


class NativeServer(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=True
    def __init__(self,address,control,host,state_dir):
        bind=ipaddress.ip_address(address[0])
        if bind.version!=4 or bind.is_unspecified or not bind.is_private: raise ValueError('需要明确的本机局域网地址')
        if not re.fullmatch(r'[A-Za-z0-9.-]{1,253}',host): raise ValueError('主机名无效')
        self.context,self.fingerprint=tls_identity(Path(state_dir)/'tls',host,str(bind))
        self.control=control
        self.slots=threading.BoundedSemaphore(12)
        super().__init__(address,NativeHandler)
        self.origin=f'https://{host}:{self.server_port}'

    def get_request(self):
        connection,address=super().get_request()
        connection.settimeout(3)
        return connection,address

    def handle_error(self,request,client_address): pass

    def process_request(self,request,client_address):
        if not self.slots.acquire(blocking=False): self.shutdown_request(request);return
        try: super().process_request(request,client_address)
        except Exception: self.slots.release();raise

    def process_request_thread(self,request,client_address):
        try:
            secured=self.context.wrap_socket(request,server_side=True)
            super().process_request_thread(secured,client_address)
        except (OSError,ssl.SSLError): self.shutdown_request(request)
        finally: self.slots.release()

    def local_status(self):
        value=self.control.local_status()
        challenge=self.control.challenge
        value.update(origin=self.origin,transport='native-tls',serverFingerprint=self.fingerprint,pairingURL=None)
        if challenge and challenge['expires']>self.control.clock():
            invitation=dict(version=1,endpoint=self.origin,fingerprint=self.fingerprint,challenge=challenge['challenge'])
            encoded=base64.urlsafe_b64encode(json.dumps(invitation,separators=(',',':')).encode()).decode().rstrip('=')
            value['pairingURL']='locationlab://pair?data='+encoded
        return value


class NativeHandler(BaseHTTPRequestHandler):
    server_version='LocationLab'
    def log_message(self,*args): pass
    def do_GET(self): self.handle_api(False)
    def do_POST(self): self.handle_api(True)

    def handle_api(self,post):
        code=200
        try:
            if self.headers.get('Origin') or self.headers.get('Transfer-Encoding'):
                raise RequestError('此接口只供已配对的原生客户端使用',403)
            if self.path not in ('/v1/pair/request','/v1/pair/poll','/v1/status','/v1/apply','/v1/stop','/v1/favorites'):
                raise RequestError('接口不存在',404)
            body={}
            if post:
                try: length=int(self.headers.get('Content-Length','0'))
                except ValueError: raise RequestError('请求长度无效')
                if not 1<=length<=65536 or self.headers.get_content_type()!='application/json': raise RequestError('请求格式无效')
                try: body=json.loads(self.rfile.read(length))
                except (ValueError,UnicodeError): raise RequestError('JSON格式无效')
                if not isinstance(body,dict): raise RequestError('请求必须为对象')
            token=self.headers.get('Authorization','').removeprefix('Bearer ') if self.headers.get('Authorization','').startswith('Bearer ') else None
            control=self.server.control
            if post and self.path=='/v1/pair/request': value=control.request_pairing(body)
            elif post and self.path=='/v1/pair/poll':
                value,issued=control.poll_pairing(body)
                if issued: value['token']=issued
            elif not post and self.path=='/v1/status':
                value=control.status(token)
                backend=control.service.backend
                network=getattr(backend,'current_network',None)
                requires_network=getattr(backend,'requires_network',True)
                if network and requires_network and value['status']['availableDevices'] and not value['status']['sessionId']:network.prepare()
                value['networkReady']=network.ready if network and requires_network else True
                value['networkHint']=network.hint if network and requires_network else None
                value['nativeMapPointsEnabled']=bool(control.maps_config.get('native',{}).get('coordinatePolicy')=='validated-native' and control.maps_config.get('native',{}).get('validationEvidence'))
                value['transport']=getattr(control.service.backend,'lane','usb')
            elif not post and self.path=='/v1/favorites':
                value=control.favorite_list(token)
                with control.lock:
                    backend=control.service.backend;grant=control.authorize(token)
                    legacy=getattr(backend,'legacy_device_id',None)
                    if legacy and grant['deviceId']==getattr(backend,'device_id',None):
                        value['favorites']+=control.favorites.list(legacy)
            elif post and self.path in ('/v1/apply','/v1/stop'): value=control.command(token,self.path.rsplit('/',1)[1],body)
            else: raise RequestError('请求方法无效',405)
            payload=dict(ok=True,**value)
        except RequestError as error: code=error.status;payload=dict(ok=False,error=str(error))
        except (ValueError,TypeError): code=400;payload=dict(ok=False,error='请求内容无效')
        except Exception: code=500;payload=dict(ok=False,error='服务暂不可用，请在Mac检查状态')
        data=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode()
        try:
            self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
            self.send_header('Connection','close');self.end_headers();self.wfile.write(data)
        except (BrokenPipeError,ConnectionError,OSError): pass
        self.close_connection=True
