"""Frozen supported store slots; decoded bytes, not extensions or assumptions."""
import collections
from pathlib import Path

from assets import image_info
from .metadata import normalize_fields
from .records import file_digest, read_json, safe_path

CATALOG_FILE = Path(__file__).resolve().parents[1] / 'catalog/store-rules-v1.json'


def rules():
    return read_json(CATALOG_FILE)


def slot_rule(store, slot):
    try:
        return rules()['stores'][store]['slots'][slot]
    except KeyError:
        raise ValueError(f'unsupported store image slot: {store}/{slot}') from None


def encoded_format(path):
    path = Path(path)
    if path.name.startswith('.'):
        raise ValueError('hidden image would be omitted by the reader')
    with path.open('rb') as stream:
        header = stream.read(26)
    if header.startswith(b'\x89PNG\r\n\x1a\n'):
        fmt, extensions = 'PNG', {'.png', '.PNG'}
    elif header.startswith(b'\xff\xd8\xff'):
        fmt, extensions = 'JPEG', {'.jpg', '.JPG', '.jpeg', '.JPEG'}
    else:
        raise ValueError('image format signature is not PNG/JPEG; no delegate will be invoked')
    if path.suffix not in extensions:
        raise ValueError('image format/extension differs from the Fastlane reader')
    return fmt, header


def validate_images(root, entries, store):
    result = []
    seen = set()
    counts = collections.Counter()
    for entry in entries:
        path = safe_path(root, entry['file'])
        if entry['file'] in seen:
            raise ValueError('duplicate image inventory entry')
        seen.add(entry['file'])
        normalize_fields({entry['locale']: {}})
        rule = slot_rule(store, entry['slot'])
        fmt, header = encoded_format(path)
        width, height, alpha = image_info(path)
        if fmt not in rule['formats']:
            raise ValueError('image format is unsupported for slot')
        if rule['alpha'] == 'forbidden' and alpha:
            raise ValueError('alpha channel is forbidden for slot')
        if rule['alpha'] == 'required-rgba32' and (fmt != 'PNG' or len(header) < 26 or header[24:26] != bytes([8, 6])):
            raise ValueError('icon requires a 32-bit RGBA PNG')
        if 'sizes' in rule:
            accepted = rule['sizes'] + ([size[::-1] for size in rule['sizes']] if rule.get('rotate') else [])
            if [width, height] not in accepted:
                raise ValueError('image dimensions do not match slot')
        elif min(width, height) < rule['min_dimension'] or max(width, height) > rule['max_dimension']:
            raise ValueError('image dimensions exceed slot limits')
        elif max(width, height) / min(width, height) > rule['max_aspect']:
            raise ValueError('image aspect ratio exceeds slot limit')
        if path.stat().st_size > rule.get('max_bytes', float('inf')):
            raise ValueError('image file size exceeds slot limit')
        digest = file_digest(path)
        if entry.get('sha256', digest) != digest:
            raise ValueError('listing image hash differs')
        counts[entry['locale'], entry['slot']] += 1
        if counts[entry['locale'], entry['slot']] > rule['max_count']:
            raise ValueError('too many images in one locale/slot')
        result.append(dict(entry, size=[width, height], sha256=digest))
    return result


def validate_fields(fields, store):
    clean = normalize_fields(fields)
    limits = rules()['stores'].get(store, {}).get('text_limits', {})
    for values in clean.values():
        for key, value in values.items():
            if key in limits:
                limit, unit = limits[key]
                length = len(value.encode('utf-8')) if unit == 'utf8-bytes' else len(value)
                if length > limit:
                    raise ValueError(f'metadata field limit exceeded: {key}')
    return clean


def submission_readiness(store, slots, supports_ipad=False):
    required = rules()['stores'][store]['submission_required']
    if store == 'apple':
        selected = [required['iphone']] + ([required['ipad']] if supports_ipad else [])
        missing = sorted(set(selected) - set(slots))
        return {'ready': not missing, 'missing': missing, 'scope': 'required-image-classes-only'}
    return {'ready': False, 'missing': ['verify-total-screenshot-count'], 'scope': 'listing-not-release-approval'}
