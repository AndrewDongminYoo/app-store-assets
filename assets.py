#!/usr/bin/env python3
"""Prepare immutable App Store image bundles without changing capture inputs."""
import argparse
import collections
import errno
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


# Explicitly scoped to the existing personal iPhone/iPad pipelines.
# New display classes require App Store Connect reference-data discovery.
SCREENSHOT_SIZES = {
    (1320, 2868): 'iphone-67', (1260, 2736): 'iphone-67',
    (1290, 2796): 'iphone-67', (1284, 2778): 'iphone-65',
    (1242, 2688): 'iphone-65',
    (1206, 2622): 'iphone-medium', (1179, 2556): 'iphone-medium',
    (1170, 2532): 'iphone-58',
    (2064, 2752): 'ipad-large', (2048, 2732): 'ipad-large',
}
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg'}
FORMAT_EXTENSIONS = {'PNG': {'.png', '.PNG'}, 'JPEG': {'.jpg', '.JPG', '.jpeg', '.JPEG'}}


def digest(file):
    return hashlib.sha256(file.read_bytes()).hexdigest()


def image_info(file):
    if file.name.startswith('.'):
        raise ValueError(f'hidden screenshot would be skipped by Fastlane: {file}')
    if file.suffix not in set().union(*FORMAT_EXTENSIONS.values()):
        raise ValueError(f'unsupported Fastlane image extension: {file}')
    # Decode the pixel stream, not just the IHDR header. Warnings also reject
    # truncated images that ImageMagick might otherwise recover.
    result = subprocess.run(['magick', str(file), '-regard-warnings', '-format', '%w|%h|%[channels]|%m\n', 'info:'], capture_output=True, text=True, timeout=60)
    if result.returncode or result.stderr:
        raise ValueError(f'cannot decode image: {file}')
    values = result.stdout.strip().split('|')
    if len(values) != 4 or '\n' in result.stdout.strip():
        raise ValueError(f'expected one still image: {file}')
    if file.suffix not in FORMAT_EXTENSIONS.get(values[3], set()):
        raise ValueError(f'image format does not match extension: {file}')
    width, height = map(int, values[:2])
    header = file.read_bytes()[:26]
    alpha = values[2].split()[0].lower().endswith('a')
    if header.startswith(b'\x89PNG\r\n\x1a\n'):
        # Fully opaque RGBA still has an alpha channel. Palette transparency
        # is detected by the decoder above.
        alpha = alpha or header[25] in (4, 6)
    return width, height, alpha


def screenshot_info(file):
    width, height, alpha = image_info(file)
    if alpha:
        raise ValueError(f'alpha channel is not allowed: {file}')
    profile = SCREENSHOT_SIZES.get((min(width, height), max(width, height)))
    if not profile:
        raise ValueError(f'unsupported screenshot size {width}x{height}: {file}')
    return [width, height], profile


def inside(root, relative):
    file = (root / relative).resolve()
    if not file.is_relative_to(root.resolve()):
        raise ValueError(f'path escapes bundle: {relative}')
    return file


def validate(folder):
    folder = Path(folder).resolve()
    manifest = json.loads((folder / 'manifest.json').read_text())
    if manifest.get('schema_version') != 1 or manifest.get('account') != 'personal':
        raise ValueError('unsupported manifest schema or account')
    assets = manifest['assets']
    if not assets:
        raise ValueError('empty asset bundle')
    files = [item['file'] for item in assets]
    if len(files) != len(set(files)):
        raise ValueError('duplicate bundle file')
    counts = collections.Counter()
    for item in assets:
        file = inside(folder, item['file'])
        if digest(file) != item['sha256']:
            raise ValueError(f'final hash differs: {file}')
        size, profile = screenshot_info(file)
        if size != item['size'] or profile != item['profile']:
            raise ValueError(f'final image specification differs: {file}')
        counts[item['locale'], profile] += 1
    if any(count > 10 for count in counts.values()):
        raise ValueError('more than 10 screenshots in one locale/display class')
    actual = {str(p.relative_to(folder)) for p in (folder / 'screenshots').rglob('*') if p.is_file()}
    if actual != set(files):
        raise ValueError('screenshot inventory differs from manifest')
    return manifest


def prepare(args):
    source = Path(args.source).resolve()
    if not source.is_dir():
        raise ValueError(f'screenshot source is missing: {source}')
    output = Path(args.out).resolve()
    if output == source or output.is_relative_to(source):
        raise ValueError('bundle output must be outside the source tree')
    subdir = Path(args.subdir)
    if subdir.is_absolute() or '..' in subdir.parts:
        raise ValueError('subdir must stay inside each locale')
    inputs = []
    for locale in sorted(source.iterdir()):
        if not locale.is_dir() or locale.name.startswith('.'):
            continue
        locale_files = []
        for file in sorted((locale / subdir).glob('*')):
            if file.is_file() and file.suffix.lower() in IMAGE_EXTENSIONS:
                if not file.resolve().is_relative_to(source):
                    raise ValueError(f'image is outside source tree: {file}')
                locale_files.append(file)
                inputs.append((locale.name, file))
        if any(file.stem.lower().endswith('_framed') for file in locale_files):
            if any('framed' not in file.name.lower() and 'watch' not in file.name.lower() for file in locale_files):
                raise ValueError(f'mixed framed filenames would make Fastlane skip images: {locale.name}')
    if not inputs:
        raise ValueError('no screenshot inputs found')
    # Keep partial output invisible to uploaders; never replace caller files.
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.prepare-', dir=output) as scratch:
        folder = Path(scratch)
        assets = []
        for locale, file in inputs:
            source_hash = digest(file)
            relative = Path('screenshots') / locale / file.name
            final = folder / relative
            final.parent.mkdir(parents=True, exist_ok=True)
            _, _, alpha = image_info(file)
            if alpha and args.normalize_alpha:
                if file.suffix.lower() != '.png':
                    raise ValueError(f'alpha normalization requires PNG: {file}')
                opaque = subprocess.run(['magick', str(file), '-format', '%[opaque]', 'info:'], capture_output=True, text=True, timeout=60)
                if opaque.returncode or opaque.stdout.strip().lower() != 'true':
                    raise ValueError(f'transparent pixels require an explicit composition background: {file}')
                result = subprocess.run(['magick', str(file), '-alpha', 'off', '-depth', '8', '-define', 'png:exclude-chunk=date,time', 'PNG24:' + str(final)], capture_output=True, text=True, timeout=60)
                if result.returncode:
                    raise ValueError(f'normalization failed: {file}')
            else:
                shutil.copyfile(file, final)
            size, profile = screenshot_info(final)
            assets.append(dict(file=str(relative), locale=locale, kind='screenshot', profile=profile, size=size, sha256=digest(final), source_sha256=source_hash, source_file=str(file)))
        manifest = dict(schema_version=1, project=args.project, account='personal', bundle_id=args.bundle_id, provenance={'status': 'unverified-import'}, replacement_policy='replace-localized-sets', assets=assets)
        encoded = json.dumps(manifest, sort_keys=True, indent=2) + '\n'
        (folder / 'manifest.json').write_text(encoded)
        validate(folder)
        destination = output / hashlib.sha256(encoded.encode()).hexdigest()
        if not destination.exists():
            try:
                folder.rename(destination)
            except OSError as error:
                # Another preparer may have atomically published this bundle.
                # Permission, I/O and other rename failures must still fail.
                if error.errno not in (errno.EEXIST, errno.ENOTEMPTY):
                    raise
        if validate(destination) != manifest:
            raise ValueError(f'cached bundle differs from expected manifest: {destination}')
        return dict(bundle=str(destination), screenshots_path=str(destination / 'screenshots'), assets=len(assets))


def main():
    if len(sys.argv) > 1 and sys.argv[1] in {'doctor', 'plan', 'diff', 'generate', 'build', 'download', 'execute', 'verify'}:
        sys.dont_write_bytecode = True
        from app_store_assets.cli import main as pipeline_main
        return pipeline_main(sys.argv[1:])
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    command = commands.add_parser('prepare-screenshots')
    command.add_argument('--source', required=True)
    command.add_argument('--out', required=True)
    command.add_argument('--project', required=True)
    command.add_argument('--bundle-id', required=True)
    command.add_argument('--subdir', default='.')
    command.add_argument('--normalize-alpha', action='store_true')
    command = commands.add_parser('validate')
    command.add_argument('bundle')
    args = parser.parse_args()
    try:
        result = prepare(args) if args.command == 'prepare-screenshots' else validate(args.bundle)
        print(json.dumps(result, sort_keys=True))
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
