#!/usr/bin/env python3
"""Build portable release archives from local, explicitly selected build inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
MAGIC={b'\xcf\xfa\xed\xfe',b'\xce\xfa\xed\xfe',b'\xca\xfe\xba\xbe',b'\xbe\xba\xfe\xca'}
PRIVATE_SUFFIXES={'.pk8','.p7b','.key','.p12','.pfx','.mobileprovision'}


def run(*args,**kwargs):
    return subprocess.run([str(a) for a in args],check=True,**kwargs)


def digest(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as file:
        for chunk in iter(lambda:file.read(1024*1024),b''): result.update(chunk)
    return result.hexdigest()


def check_runtime_tree(root):
    root=Path(root).resolve()
    for path in root.rglob('*'):
        if path.is_symlink(): raise ValueError('Runtime resources must be a complete tree without symlinks')
        if path.is_file() and (path.suffix.lower() in PRIVATE_SUFFIXES or path.name in ('identity.json','grants.json','config.json') or '.private.' in path.name):
            raise ValueError('Private runtime material is not a release input: '+str(path.relative_to(root)))
    required=('engine/main.js','driver/livi-helperd','driver/loc2-capabilities.json','runtime/MacPlayReceiver.app/Contents/MacOS/MacPlayReceiver')
    if any(not (root/name).is_file() for name in required): raise ValueError('Runtime resources are incomplete')
    capability=json.loads((root/'driver/loc2-capabilities.json').read_text())
    if capability.get('schemaVersion')!=1 or capability.get('wpa3Transition') is not True or capability.get('helperSHA256')!=digest(root/'driver/livi-helperd'):
        raise ValueError('Runtime capability receipt does not match helper')
    return capability


def macho_files(root):
    for path in Path(root).rglob('*'):
        if path.is_file() and not path.is_symlink():
            with path.open('rb') as file: magic=file.read(4)
            if magic in MAGIC: yield path


def load_commands(path):
    output=run('otool','-l',path,capture_output=True,text=True).stdout
    for block in output.split('Load command ')[1:]:
        command=re.search(r'\n\s+cmd (\S+)',block)
        value=re.search(r'\n\s+(?:name|path) (.+) \(offset \d+\)',block)
        if command and value: yield command[1],value[1]


def relocate_runtime(root, original):
    binaries=list(macho_files(root));minimum=(13,0)
    for path in binaries:
        changes=[];seen=set()
        for command,value in load_commands(path):
            if (command,value) in seen: continue
            seen.add((command,value))
            if command=='LC_ID_DYLIB':
                changes+=['-id','@rpath/'+path.name];continue
            if command not in ('LC_LOAD_DYLIB','LC_LOAD_WEAK_DYLIB','LC_REEXPORT_DYLIB','LC_RPATH'): continue
            if not value.startswith('/') or value.startswith(('/usr/lib/','/System/Library/')): continue
            try: target=Path(root)/Path(value).relative_to(original)
            except ValueError:
                matches=list(Path(root).rglob(Path(value).name))
                if len(matches)!=1: raise ValueError('Unresolved external runtime dependency: '+value)
                target=matches[0]
            if not target.exists(): raise ValueError('Missing relocated dependency: '+str(target))
            replacement='@loader_path/'+os.path.relpath(target,path.parent)
            changes+=['-rpath' if command=='LC_RPATH' else '-change',value,replacement]
        if changes: run('install_name_tool',*changes,path,capture_output=True)
        run('codesign','--force','--sign','-','--timestamp=none',path,capture_output=True)
        metadata=run('xcrun','vtool','-show-build',path,capture_output=True,text=True).stdout
        for value in re.findall(r'\bminos ([0-9.]+)',metadata): minimum=max(minimum,tuple(int(n) for n in value.split('.')))
        for command,value in load_commands(path):
            if command!='LC_ID_DYLIB' and value.startswith('/') and not value.startswith(('/usr/lib/','/System/Library/')):
                raise ValueError('Runtime is still tied to a developer path')
    run('codesign','--force','--sign','-','--timestamp=none',Path(root)/'runtime/MacPlayReceiver.app',capture_output=True)
    return '.'.join(str(n) for n in minimum)


def obtain_python(cache, source_archive=None):
    lock=json.loads((ROOT/'release/python-runtime.json').read_text())
    archive=cache/'python.tar.gz'
    if source_archive is not None:
        if digest(source_archive)!=lock['sha256']: raise ValueError('Cached Python archive checksum mismatch')
        shutil.copyfile(source_archive,archive)
    if not archive.exists() or digest(archive)!=lock['sha256']:
        with urllib.request.urlopen(lock['url'],timeout=90) as response, archive.open('wb') as file: shutil.copyfileobj(response,file)
    if digest(archive)!=lock['sha256']: raise ValueError('Python download checksum mismatch')
    destination=cache/'extracted'
    destination.mkdir()
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            target=destination/member.name
            if member.name.startswith('/') or '..' in Path(member.name).parts or member.isdev() or member.isfifo() or member.islnk(): raise ValueError('Unsafe Python archive')
            if member.issym():
                resolved=(target.parent/member.linkname).resolve()
                if not resolved.is_relative_to(destination.resolve()): raise ValueError('Unsafe Python symlink')
        tar.extractall(destination)
    return destination/'python',lock



def obtain_github_cli(cache, source_archive=None):
    lock=json.loads((ROOT/'release/github-cli.json').read_text())
    archive=cache/'github-cli.zip'
    if source_archive is not None:
        if digest(source_archive)!=lock['sha256']: raise ValueError('Cached GitHub CLI checksum mismatch')
        shutil.copyfile(source_archive,archive)
    else:
        with urllib.request.urlopen(lock['url'],timeout=90) as response,archive.open('wb') as file: shutil.copyfileobj(response,file)
    if digest(archive)!=lock['sha256']: raise ValueError('GitHub CLI download checksum mismatch')
    destination=cache/'GitHubCLI';(destination/'bin').mkdir(parents=True)
    prefix='gh_'+lock['version']+'_macOS_arm64/'
    with zipfile.ZipFile(archive) as source:
        (destination/'bin/gh').write_bytes(source.read(prefix+'bin/gh'))
        (destination/'LICENSE').write_bytes(source.read(prefix+'LICENSE'))
    (destination/'bin/gh').chmod(0o755)
    return destination,lock


def source_bundle(source, destination, runtime_resources):
    source=Path(source).resolve()
    excluded={'target','node_modules','.git','.build','build','dist','authentication','__pycache__'}
    def ignore(directory,names):
        return [name for name in names if name in excluded or name.startswith('.env') or Path(name).suffix in PRIVATE_SUFFIXES or '.private.' in name or name.endswith(('.app','.log','.dmg'))]
    shutil.copytree(source,destination,ignore=ignore,symlinks=False)
    baseline=json.loads((ROOT/'docs/native-runtime-manifest-2026-11-02.json').read_text())
    helper=destination/'native/livi-helperd'
    for name,expected in baseline['baselineFileSHA256'].items():
        if digest(helper/name)!=expected: raise ValueError('Third-party source baseline mismatch: '+name)
    run('patch','-p1','--batch','-i',ROOT/'tools/runtime-patches/wpa3-transition.patch',cwd=helper,capture_output=True)
    # Preserve the actual shipped, locally modified JS in addition to upstream TS.
    shutil.copytree(Path(runtime_resources)/'engine',destination/'loc2-runtime-engine')
    shutil.copy2(ROOT/'tools/runtime-patches/wpa3-transition.patch',destination/'loc2-wpa3-transition.patch')
    (destination/'LOC2-BUILD-NOTES.txt').write_text('MacPlay/LIVI source snapshot with Loc2 WPA3 transition patch applied.\nBuild helper: cd native/livi-helperd && cargo build --locked --release -p livi-helperd\nThe loc2-runtime-engine directory contains the actual shipped JavaScript overlay.\nAuthentication assets and machine identities are excluded.\nGStreamer upstream: https://gstreamer.freedesktop.org/src/\nPython build source and licenses: https://github.com/astral-sh/python-build-standalone\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version',required=True)
    parser.add_argument('--build',required=True)
    parser.add_argument('--runtime-resources',required=True,type=Path)
    parser.add_argument('--third-party-source',required=True,type=Path)
    parser.add_argument('--mac-app',type=Path,default=ROOT/'build/Loc2.app')
    parser.add_argument('--ios-app',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--python-archive',type=Path,help='Optional cached archive; must match pinned SHA-256')
    parser.add_argument('--github-cli-archive',type=Path,help='Optional checksum-verified GitHub CLI ZIP')
    args=parser.parse_args()
    if not re.fullmatch(r'\d+\.\d+\.\d+',args.version) or not args.build.isdigit(): parser.error('Version/build must be numeric')
    capability=check_runtime_tree(args.runtime_resources)
    for binary in (args.mac_app/'Contents/MacOS/loc2', args.runtime_resources/'driver/livi-helperd', args.runtime_resources/'runtime/MacPlayReceiver.app/Contents/MacOS/MacPlayReceiver'):
        if 'arm64' not in run('lipo','-archs',binary,capture_output=True,text=True).stdout.split():
            raise ValueError('This release requires arm64 build inputs')
    args.output.mkdir(parents=True,exist_ok=False)
    print('Packaging portable Mac runtime and signed IPA…',flush=True)
    with tempfile.TemporaryDirectory(prefix='loc2-release-') as temporary:
        stage=Path(temporary)
        app=stage/'Loc2.app';shutil.copytree(args.mac_app,app,symlinks=True)
        resources=app/'Contents/Resources'
        runtime=resources/'Runtime/resources'
        shutil.copytree(args.runtime_resources,runtime)
        for obsolete in (runtime/'driver/livi-helperd.wpa2-baseline',runtime/'gstreamer/macos-x64'):
            if obsolete.is_dir(): shutil.rmtree(obsolete)
            elif obsolete.exists(): obsolete.unlink()
        minimum=relocate_runtime(runtime,args.runtime_resources.resolve())
        capability.update(sourceHelperSHA256=capability['helperSHA256'],helperSHA256=digest(runtime/'driver/livi-helperd'))
        (runtime/'driver/loc2-capabilities.json').write_text(json.dumps(capability,indent=2)+'\n')
        python,python_lock=obtain_python(stage,args.python_archive)
        shutil.copytree(python,resources/'Python',symlinks=True)
        github_cli,github_lock=obtain_github_cli(stage,args.github_cli_archive)
        shutil.copytree(github_cli,resources/'GitHubCLI')
        run('codesign','--force','--sign','-','--timestamp=none',resources/'GitHubCLI/bin/gh',capture_output=True)
        licenses=resources/'ThirdPartyLicenses';licenses.mkdir(exist_ok=True)
        shutil.copy2(github_cli/'LICENSE',licenses/'GitHub-CLI-LICENSE')
        for name in ('LICENSE','NOTICE','CREDITS.md'): shutil.copy2(args.third_party_source/name,licenses/('MacPlay-'+name))
        for folder in ('assets/licenses','assets/gstreamer/LICENSES'):
            shutil.copytree(args.third_party_source/folder,licenses/Path(folder).parent.name,dirs_exist_ok=True)
        (licenses/'LOC2-DISTRIBUTION.txt').write_text('The upstream NOTICE references authentication assets. Those assets, all private keys, machine identities, pairing records and user configurations are excluded from this Loc2 distribution. Corresponding MacPlay/LIVI sources and the Loc2 overlay are supplied as a separate release asset.\n')
        (resources/'release.json').write_text(json.dumps(dict(version=args.version,build=args.build,architecture='arm64',minimumMacOS=minimum,python=python_lock,githubCLI=github_lock,sourceRevision=run('git','rev-parse','HEAD',cwd=ROOT,capture_output=True,text=True).stdout.strip()),indent=2)+'\n')
        info=app/'Contents/Info.plist'
        value=plistlib.loads(info.read_bytes());value.update(CFBundleShortVersionString=args.version,CFBundleVersion=args.build,LSMinimumSystemVersion=minimum)
        info.write_bytes(plistlib.dumps(value))
        details=run('codesign','-dvv',args.mac_app,capture_output=True,text=True).stderr
        authority=next((line.split('=',1)[1] for line in details.splitlines() if line.startswith('Authority=')),None)
        if not authority: raise ValueError('Release Mac app requires an available signing identity')
        identities=run('security','find-identity','-v','-p','codesigning',capture_output=True,text=True).stdout
        identity=next((line.split()[1] for line in identities.splitlines() if '"'+authority+'"' in line),None)
        if not identity: raise ValueError('Existing Mac signing identity is unavailable')
        run('codesign','--force','--sign',identity,'--timestamp=none',app,capture_output=True)
        run('codesign','--verify','--deep','--strict',app,capture_output=True)
        mac_archive=args.output/f'Loc2-{args.version}-macOS-arm64.zip'
        run('ditto','-c','-k','--keepParent','--norsrc',app,mac_archive)
        # An IPA is the signed iOS app under Payload; its provisioning restrictions remain.
        run('codesign','--verify','--strict',args.ios_app,capture_output=True)
        ios_info=plistlib.loads((args.ios_app/'Info.plist').read_bytes())
        if ios_info.get('CFBundleShortVersionString')!=args.version or ios_info.get('CFBundleVersion')!=args.build:
            raise ValueError('iOS app version/build differs from release metadata')
        payload=stage/'Payload';payload.mkdir();shutil.copytree(args.ios_app,payload/'Loc2.app',symlinks=True)
        ipa=args.output/f'Loc2-{args.version}-iOS-development.ipa'
        run('ditto','-c','-k','--keepParent','--norsrc',payload,ipa)
        profile=run('security','cms','-D','-i',args.ios_app/'embedded.mobileprovision',capture_output=True).stdout
        provision=plistlib.loads(profile)
        sources=stage/'Loc2-runtime-sources';source_bundle(args.third_party_source,sources,args.runtime_resources)
        with tarfile.open(args.output/f'Loc2-{args.version}-runtime-sources.tar.gz','w:gz') as tar: tar.add(sources,arcname=sources.name)
        metadata=dict(version=args.version,build=args.build,minimumMacOS=minimum,architecture='arm64',notarized=False,
            iosProfileExpires=provision['ExpirationDate'].isoformat()+'Z',iosProvisionedDeviceCount=len(provision.get('ProvisionedDevices',[])),
            credentialsIncluded=False,sourceRevision=run('git','rev-parse','HEAD',cwd=ROOT,capture_output=True,text=True).stdout.strip())
        (args.output/'release-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
        files=sorted(p for p in args.output.iterdir() if p.is_file())
        (args.output/'SHA256SUMS').write_text(''.join(digest(p)+'  '+p.name+'\n' for p in files))
        print(json.dumps(metadata,indent=2))
        print(args.output)


if __name__=='__main__': main()
