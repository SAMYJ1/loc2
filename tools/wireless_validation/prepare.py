"""Prepare a hidden, prewarmed wireless overlay without changing source resources."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
from tools.usb_validation.prepare import prepare as prepare_hidden

MARKER='// Location Lab: use interface-name IPv6 zones and fail-closed target discovery.\n'


def patch_discovery(source):
    if source.startswith(MARKER):return source
    replacements={
        "address.address.split('%')[0] + '%' + interfaceScope(address.address, address.scopeid)":
            "address.address.split('%')[0] + '%' + this.iface",
        "const scope = ipv6 ? interfaceScope(local.address, local.scopeid) : undefined;":
            "const scope = ipv6 ? this.iface : undefined;",
        "if (this.targetBt && id && normalizeId(id) !== normalizeId(this.targetBt))":
            "if (this.targetBt && (!id || normalizeId(id) !== normalizeId(this.targetBt)))",
        "// Missing TXT does not prevent address resolution or alter the old matching\n            // policy: reject only an explicitly advertised ID that differs from the target.":
            "// Resolve addresses while TXT is pending, but never probe an unidentified device.",
        "socket.on('warning', (error) => this.diagnostic('warning-' + family + '-' + this.errorCode(error), family + '多播警告/' + this.errorCode(error)));":
            """socket.on('warning', (error) => {
                    this.diagnostic('warning-' + family + '-' + this.errorCode(error), family + '多播警告/' + this.errorCode(error));
                    this.sockets = this.sockets.filter(candidate => candidate !== socket);
                    socket.destroy();
                });""",
        "socket.on('ready', () => {\n                    if (this.closed)":
            "socket.on('ready', () => {\n                    if (this.closed || !this.sockets.includes(socket))",
    }
    for old,new in replacements.items():
        if source.count(old)!=1:raise ValueError('Unsupported discovery version; inspect before preparing runtime')
        source=source.replace(old,new)
    return MARKER+source


def prepare(resources,output):
    resources,output=Path(resources),Path(output)
    original_discovery=(resources/'engine/discovery.js').read_text()
    fixed_discovery=patch_discovery(original_discovery)
    manifest=prepare_hidden(resources,output)
    engine=output/'resources/engine';main=engine/'main.js';before_main=main.read_text();after_main=before_main
    if 'media_1.addon.probeCodecs();' not in before_main:
        anchor='const identity = (0, identity_1.loadOrCreateIdentity)();'
        if before_main.count(anchor)!=1:raise ValueError('Unsupported startup; cannot place preflight safely')
        before='''diagnostic('media-preflight-start');
const mediaPreflightStarted = Date.now();
media_1.addon.probeCodecs();
diagnostic('media-preflight-ready', { durationMs: Date.now() - mediaPreflightStarted });
'''
        after_main=before_main.replace(anchor,before+anchor)
    stats="diagnostic('media-statistics', { videoPackets: counts[0], audioPackets: counts[1] });"
    periodic="diagnostic('handoff-summary', discovery?.summary());\n            "+stats
    if periodic not in after_main:
        if after_main.count(stats)!=1:raise ValueError('Unsupported media statistics; cannot add discovery diagnostics')
        after_main=after_main.replace(stats,periodic)
    main.write_text(after_main);(engine/'discovery.js').write_text(fixed_discovery)
    patches=[]
    for name,before,after in [('main.js',before_main,after_main),('discovery.js',original_discovery,fixed_discovery)]:
        patches.extend(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='hidden/engine/'+name,tofile='wireless/engine/'+name))
    (output/'wireless.patch').write_text(''.join(patches))
    manifest['wireless']={'prewarm':True,'ipv6Zones':'interface-name','requireTargetTXT':True,'periodicDiscoverySummary':True,
        'finalSHA256':{name:hashlib.sha256((engine/name).read_bytes()).hexdigest() for name in ['main.js','media.js','discovery.js']}}
    (output/'preparation.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resources',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();prepare(args.resources,args.output)
    print('Prepared wireless overlay. No receiver started; no credentials copied.')
if __name__=='__main__':main()
