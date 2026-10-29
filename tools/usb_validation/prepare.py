#!/usr/bin/env python3
"""Prepare an isolated hidden-video receiver overlay. Does not start any process."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path

RESOURCE_LINKS = ('driver', 'gstreamer', 'icons', 'runtime')
ENGINE_FILES = ('CpHelperSock.js', 'ProjectionEnums.js', 'constants.js', 'discovery.js',
                'display.js', 'frameRateFallback.js', 'microphonePermission.js',
                'networkConfig.js', 'phoneSelection.js', 'runtimeControls.js',
                'storage.js', 'videoHealth.js')
ENGINE_LINKS = ('node_modules',)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def prepare(source, output):
    source, output = source.resolve(), output.resolve()
    if output.exists():
        raise ValueError('output must be a new directory')
    repo = Path(__file__).resolve().parents[2]
    if repo == output or repo in output.parents or source == output or source in output.parents:
        raise ValueError('output must be outside the repository and original resources')
    for name in RESOURCE_LINKS:
        if not (source / name).is_dir():
            raise ValueError('missing required resource directory: ' + name)
    for name in ENGINE_FILES + ENGINE_LINKS + ('protocol',):
        if not (source / 'engine' / name).exists():
            raise ValueError('missing required engine dependency: ' + name)
    originals = {name: (source / 'engine' / name).read_text() for name in ('media.js', 'main.js')}
    media, main = originals['media.js'], originals['main.js']
    display = 'exports.addon.macplayWindowHandle(aspect);'
    if media.count(display) != 2:
        raise ValueError('unsupported engine: expected exactly two display calls; inspect upstream changes')
    media = media.replace(display, 'exports.addon.macplayPrepareVideoWindow(aspect);')
    if 'macplayWindowHandle(' in media:
        raise ValueError('unsupported engine: an unhandled presentation path remains')
    replacements = {
        'showCarPlay: true': 'showCarPlay: false, hiddenVideoValidation: true',
        '首帧已解码，CarPlay画面窗口已打开': '首帧已解码，CarPlay画面保持隐藏',
        '已接收CarPlay视频，画面窗口已打开': '已接收CarPlay视频，画面保持隐藏',
    }
    for old, new in replacements.items():
        if main.count(old) != 1:
            raise ValueError('unsupported engine: expected one occurrence of ' + old)
        main = main.replace(old, new)
    modified = {'media.js': media, 'main.js': main}
    output.mkdir(mode=0o700)
    resources = output / 'resources'
    engine = resources / 'engine'
    engine.mkdir(parents=True, mode=0o700)
    (output / 'data').mkdir(mode=0o700)
    for name in RESOURCE_LINKS:
        (resources / name).symlink_to(source / name, target_is_directory=True)
    for name in ENGINE_LINKS:
        entry = source / 'engine' / name
        if entry.exists():
            (engine / name).symlink_to(entry, target_is_directory=entry.is_dir())
    # Node resolves symlinks to their real paths. Linking protocol/ or a top-level
    # module back to the original engine makes ../media load a second instance,
    # separating decoder state from the hidden engine's readiness callback.
    copies = [source / 'engine' / name for name in ENGINE_FILES]
    copies.extend((source / 'engine/protocol').rglob('*.js'))
    for entry in copies:
        target = engine / entry.relative_to(source / 'engine')
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.write_bytes(entry.read_bytes())
        target.chmod(0o600)
    patches, hashes = [], {}
    for name, data in modified.items():
        (engine / name).write_text(data)
        (engine / name).chmod(0o600)
        patches.extend(difflib.unified_diff(originals[name].splitlines(True), data.splitlines(True), fromfile='original/engine/' + name, tofile='hidden/engine/' + name))
        hashes[name] = {'originalSHA256': digest(originals[name].encode()), 'hiddenSHA256': digest(data.encode())}
    (output / 'hidden-video.patch').write_text(''.join(patches))
    manifest = {'mode': 'prepared-only', 'receiverStarted': False, 'positionAdoption': 'unverified',
                'realLocationRecovery': 'unverified', 'sourceResources': str(source), 'hashes': hashes,
                'engineModuleLayout': 'local-js-graph',
                'copiedEngineModules': sorted(str(p.relative_to(source / 'engine')) for p in copies),
                'note': 'Engine JS is copied to preserve module identity. Binary/package dependency links are local-only. Authentication and pairing data are not copied.'}
    (output / 'preparation.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resources', required=True, type=Path, help='existing MacPlay resources directory (read-only)')
    parser.add_argument('--output', required=True, type=Path, help='new private directory outside this repository')
    args = parser.parse_args()
    try:
        prepare(args.resources, args.output)
    except (ValueError, OSError) as error:
        parser.exit(2, str(error) + '\n')
    print('Prepared hidden-video overlay. Receiver not started; device adoption remains unverified.')


if __name__ == '__main__':
    main()
