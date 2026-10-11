"""Charge retained public bytes before accepting another bounded capture."""

import hashlib
import os
import stat
from pathlib import PurePosixPath

from app_store_assets.records import identity, open_directory, open_read, safe_path


def _hash_file(path, before, limit):
    with open_read(path) as stream:
        if identity(os.fstat(stream.fileno())) != identity(before):
            raise ValueError("editing input changed after byte reservation")
        digest = hashlib.sha256()
        count = 0
        while True:
            block = stream.read(min(1024 * 1024, limit - count + 1))
            if not block:
                break
            count += len(block)
            if count > limit:
                raise ValueError("editing input exceeds reserved byte bound")
            digest.update(block)
        if identity(os.fstat(stream.fileno())) != identity(before):
            raise ValueError("editing input changed during bounded hash")
        return digest.hexdigest()


def bounded_inventory(root, limits, total):
    """Validate the exact tree and reserve all sizes before hashing any file."""
    sizes = {}

    def scan(fd, prefix):
        before = identity(os.fstat(fd))
        for name in sorted(os.listdir(fd)):
            relative = (prefix / name).as_posix()
            safe_path(root, relative)
            observed = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISDIR(observed.st_mode):
                child = os.open(
                    name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                )
                try:
                    scan(child, PurePosixPath(relative))
                finally:
                    os.close(child)
            elif stat.S_ISREG(observed.st_mode):
                if relative not in limits:
                    raise ValueError("added file outside reviewed inventory")
                sizes[relative] = observed
            else:
                raise ValueError("symlink or unsupported editing input type")
        if before != identity(os.fstat(fd)):
            raise ValueError("editing directory changed during inventory")

    try:
        with open_directory(root) as fd:
            scan(fd, PurePosixPath("."))
    except OSError as error:
        raise ValueError("unsafe or changed editing directory") from error
    if set(sizes) != set(limits):
        raise ValueError("missing declared editing inventory input")
    if (
        any(sizes[name].st_size > limit for name, limit in limits.items())
        or sum(item.st_size for item in sizes.values()) > total
    ):
        raise ValueError("editing inventory exceeds per-file/total byte bound")
    return {
        name: _hash_file(safe_path(root, name), sizes[name], sizes[name].st_size)
        for name in sorted(limits)
    }


class CaptureBudget:
    def __init__(self, limit):
        if type(limit) is not int or limit < 0:
            raise ValueError("invalid local captured byte bound")
        self.remaining = limit

    def take(self, data):
        if not isinstance(data, bytes) or len(data) > self.remaining:
            raise ValueError("local output exceeds total captured byte bound")
        self.remaining -= len(data)
        return data

    def read(self, path, capture, *, per_file=None):
        limit = self.remaining
        if per_file is not None:
            limit = min(limit, per_file)
        return self.take(capture(path, limit=limit))


def bounded_json(value, canonical, limit):
    data = canonical(value)
    if len(data) > limit:
        raise ValueError("local JSON exceeds the public reader byte bound")
    return data
