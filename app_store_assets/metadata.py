"""Public metadata snapshots and explicit target-aware diffs."""
import collections
import copy
import re
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .records import inventory, record_digest
from .snapshots import publish_snapshot

PUBLIC_FIELDS = {'name', 'title', 'subtitle', 'description', 'full_description', 'short_description',
                 'keywords', 'promotional_text', 'release_notes', 'support_url', 'marketing_url',
                 'privacy_url', 'copyright', 'video'}
IMAGE_FIELDS = {'id', 'file', 'sha256', 'source_sha256', 'provider_sha256', 'processing_state', 'width', 'height'}


def remote_observation(record):
    """Remove only local download annotations; retain provider state and order."""
    result = copy.deepcopy(record)
    for groups in result.get('images', {}).values():
        for images in groups.values():
            for image in images:
                image.pop('file', None)
                image.pop('sha256', None)
    return result


def normalize_fields(fields):
    result = {}
    for locale, values in fields.items():
        if not re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', locale):
            raise ValueError('unsupported metadata locale')
        if set(values) - PUBLIC_FIELDS:
            raise ValueError('unsupported/private metadata field')
        clean = {}
        for key, value in values.items():
            if not isinstance(value, str) or '\x00' in value:
                raise ValueError('metadata field must be public text')
            if key.endswith('_url') or key == 'video':
                parsed = urlsplit(value)
                if parsed.username or parsed.password or any(re.search('token|secret|signature|password|credential', k, re.I)
                                                            for k in parse_qs(parsed.query)):
                    raise ValueError('private credential URL cannot enter public metadata')
            clean[key] = value
        result[locale] = clean
    return result


def normalize_remote(record, target):
    if record.get('target') != target:
        raise ValueError('downloaded metadata target differs')
    effects = record.get('effects', ['read'])
    if not isinstance(effects, list) or set(effects) - {'read', 'open-read-session'}:
        raise ValueError('download must be read-only; commit/write effect is forbidden')
    result = {'schema_version': 1, 'type': 'metadata-snapshot', 'origin': 'remote',
              'target': copy.deepcopy(target), 'fields': normalize_fields(record.get('fields', {})), 'images': {}}
    for key in ('revision', 'version_id', 'editable', 'review_active', 'app_info_id', 'binary', 'build_exists', 'releases', 'effects'):
        if key in record:
            result[key] = copy.deepcopy(record[key])
    for locale, groups in record.get('images', {}).items():
        normalize_fields({locale: {}})
        result['images'][locale] = {}
        for slot, images in groups.items():
            if not re.fullmatch(r'[A-Za-z0-9_-]+', slot) or not isinstance(images, list):
                raise ValueError('unsupported image group')
            result['images'][locale][slot] = [{k: copy.deepcopy(v) for k, v in item.items() if k in IMAGE_FIELDS}
                                             for item in images]
    return result


def metadata_diff(before, after):
    if before.get('target') != after.get('target'):
        raise ValueError('metadata diff target/version conflict')
    changes = []
    def visit(path, a, b):
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(set(a) | set(b)):
                name = path + '.' + key if path else key
                if key not in a:
                    changes.append({'path': name, 'kind': 'add', 'after': b[key]})
                elif key not in b:
                    changes.append({'path': name, 'kind': 'remove', 'before': a[key]})
                else:
                    visit(name, a[key], b[key])
        elif a != b:
            kind = 'change'
            if isinstance(a, list) and isinstance(b, list):
                if collections.Counter(map(record_digest, a)) == collections.Counter(map(record_digest, b)):
                    kind = 'reorder'
            changes.append({'path': path, 'kind': kind, 'before': a, 'after': b})
    for key in ('fields', 'images'):
        a, b = copy.deepcopy(before.get(key, {})), copy.deepcopy(after.get(key, {}))
        if key == 'images':
            for record in (a, b):
                for groups in record.values():
                    for images in groups.values():
                        for image in images:
                            image.pop('file', None)
        visit(key, a, b)
    return changes


def download_snapshot(provider, target, state):
    state = Path(state)
    state.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.download-', dir=state) as temp:
        folder = Path(temp)
        response = provider.download(target, folder)
        record = normalize_remote(response['record'], target)
        files = inventory(folder, [p.name for p in folder.iterdir()])
        return publish_snapshot(state, record, {name: folder / name for name in files})
