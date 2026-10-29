#!/usr/bin/env python3
"""Prepare an isolated hidden-video receiver overlay. Does not start any process."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path

RESOURCE_LINKS = ('driver', 'gstreamer', 'icons', 'runtime')
ENGINE_LINKS = ('CpHelperSock.js', 'ProjectionEnums.js', 'constants.js', 'discovery.js',
                'display.js', 'frameRateFallback.js', 'microphonePermission.js',
                'networkConfig.js', 'phoneSelection.js', 'runtimeControls.js',
                'storage.js', 'videoHealth.js', 'node_modules', 'protocol')


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
    for name in ENGINE_LINKS:
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
    patches, hashes = [], {}
    for name, data in modified.items():
        (engine / name).write_text(data)
        (engine / name).chmod(0o600)
        patches.extend(difflib.unified_diff(originals[name].splitlines(True), data.splitlines(True), fromfile='original/engine/' + name, tofile='hidden/engine/' + name))
        hashes[name] = {'originalSHA256': digest(originals[name].encode()), 'hiddenSHA256': digest(data.encode())}
    (output / 'hidden-video.patch').write_text(''.join(patches))
    manifest = {'mode': 'prepared-only', 'receiverStarted': False, 'positionAdoption': 'unverified',
                'realLocationRecovery': 'unverified', 'sourceResources': str(source), 'hashes': hashes,
                'note': 'Local dependency links are not a distributable bundle. Authentication and pairing data are not copied.'}
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
