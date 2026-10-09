"""Content-addressed immutable local history with exact inventory checks."""
import errno
import shutil
import tempfile
from pathlib import Path

from .records import canonical, file_digest, inventory, public_input_name, read_json, record_digest, safe_path


def validate_snapshot(folder):
    folder = Path(folder)
    if folder.is_symlink():
        raise ValueError('snapshot cache may not be a symlink')
    manifest = read_json(folder / 'manifest.json')
    if manifest.get('schema_version') != 1 or manifest.get('type') != 'snapshot':
        raise ValueError('unsupported snapshot manifest')
    if folder.name != record_digest(manifest):
        raise ValueError('snapshot content address differs from manifest')
    actual = inventory(folder, [p.name for p in folder.iterdir() if p.name != 'manifest.json'])
    if actual != manifest['files']:
        raise ValueError('snapshot inventory/hash differs from manifest')
    return manifest


def publish_snapshot(root, record, files, expected_hashes=None):
    root = Path(root)
    if root.is_symlink():
        raise ValueError('snapshot history may not be a symlink')
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.publish-', dir=root) as temp:
        folder = Path(temp)
        hashes = {}
        for name, source in sorted(files.items()):
            public_input_name(name)
            if name == 'manifest.json':
                raise ValueError('snapshot content may not replace its manifest')
            destination = safe_path(folder, name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(source, bytes):
                destination.write_bytes(source)
            else:
                source = Path(source)
                expected = file_digest(source)
                shutil.copyfile(source, destination, follow_symlinks=False)
                if file_digest(destination) != expected:
                    raise ValueError('snapshot source changed during copy')
            hashes[name] = file_digest(destination)
            if expected_hashes is not None and hashes[name] != expected_hashes[name]:
                raise ValueError('published artifact hash differs from inspected digest')
        manifest = {'schema_version': 1, 'type': 'snapshot', 'record': record, 'files': hashes}
        (folder / 'manifest.json').write_bytes(canonical(manifest))
        destination = root / record_digest(manifest)
        try:
            folder.rename(destination)
        except OSError as error:
            if error.errno not in (errno.EEXIST, errno.ENOTEMPTY):
                raise
        if validate_snapshot(destination) != manifest:
            raise ValueError('existing snapshot cache differs from expected manifest')
        return destination
