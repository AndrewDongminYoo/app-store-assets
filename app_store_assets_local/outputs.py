"""Descriptor-relative new-only outputs; no symlink follows or replacements."""

import ctypes
import errno
import os
import re
import stat
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

from app_store_assets.records import public_input_name, relative_path


def _immutable(fd, name):
    if re.fullmatch(r"[0-9a-f]{64}", name):
        try:
            os.stat("manifest.json", dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise ValueError("output/history overlaps immutable snapshot")


@contextmanager
def directory(path, create=False):
    path = Path(path).absolute()
    public_input_name(path)
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for name in path.parts[1:]:
            try:
                child = os.open(
                    name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                )
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(name, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                child = os.open(
                    name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                )
            os.close(fd)
            fd = child
            _immutable(fd, name)
        yield fd
    except OSError as error:
        raise ValueError(
            "unsafe output parent, symlink or missing directory"
        ) from error
    finally:
        os.close(fd)


def preflight_output(path, new=False, allow_leaf_snapshot=False):
    path = Path(path).absolute()
    public_input_name(path)
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for name in path.parts[1:-1]:
            try:
                child = os.open(
                    name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                )
            except FileNotFoundError:
                return path
            os.close(fd)
            fd = child
            _immutable(fd, name)
        try:
            current = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            return path
        if stat.S_ISLNK(current.st_mode):
            raise ValueError("output symlink is forbidden")
        if stat.S_ISDIR(current.st_mode) and not allow_leaf_snapshot:
            child = os.open(
                path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
            )
            try:
                _immutable(child, path.name)
            finally:
                os.close(child)
        if new:
            raise ValueError("output exists; never overwrite an editing tree")
        return path
    except OSError as error:
        raise ValueError("unsafe output parent or symlink") from error
    finally:
        os.close(fd)


def _exclusive_rename():
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        name, flag = "renameatx_np", 4
    elif sys.platform.startswith("linux"):
        name, flag = "renameat2", 1
    else:
        raise ValueError("atomic no-replace directory publication unavailable")
    function = getattr(libc, name, None)
    if function is None:
        raise ValueError("atomic no-replace directory publication unavailable")
    function.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    function.restype = ctypes.c_int

    def rename(fd, source, destination):
        if function(fd, os.fsencode(source), fd, os.fsencode(destination), flag):
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code))

    return rename


@contextmanager
def _child_directory(fd, parts):
    fd = os.dup(fd)
    try:
        for name in parts:
            try:
                os.mkdir(name, 0o700, dir_fd=fd)
            except FileExistsError:
                pass
            child = os.open(
                name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
            )
            os.close(fd)
            fd = child
            _immutable(fd, name)
        yield fd
    finally:
        os.close(fd)


def _write(fd, name, data, mode):
    relative = relative_path(name)
    public_input_name(relative)
    if not isinstance(data, bytes):
        raise ValueError("output must contain captured bytes")
    with _child_directory(fd, relative.parts[:-1]) as parent:
        child = os.open(
            relative.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            mode,
            dir_fd=parent,
        )
        with os.fdopen(child, "wb") as stream:
            stream.write(data)


def _clean(fd):
    for name in os.listdir(fd):
        entry = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if stat.S_ISDIR(entry.st_mode):
            child = os.open(
                name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
            )
            try:
                _clean(child)
            finally:
                os.close(child)
            os.rmdir(name, dir_fd=fd)
        else:
            os.unlink(name, dir_fd=fd)


def publish_tree(path, files, reuse=None, mode=0o644):
    """Publish all files atomically; optional reuse validates the existing winner."""
    rename = _exclusive_rename()  # capabilities checked before creating directories
    path = preflight_output(
        path, new=reuse is None, allow_leaf_snapshot=reuse is not None
    )
    for name, data in files.items():
        relative_path(name)
        public_input_name(name)
        if not isinstance(data, bytes):
            raise ValueError("output must contain captured bytes")
    with directory(path.parent, create=True) as parent:
        temporary = ".publish-" + uuid.uuid4().hex
        os.mkdir(temporary, 0o700, dir_fd=parent)
        fd = os.open(
            temporary, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
        )
        renamed = False
        try:
            for name, data in sorted(files.items()):
                _write(fd, name, data, mode)
            try:
                rename(parent, temporary, path.name)
                renamed = True
            except OSError as error:
                if error.errno not in (errno.EEXIST, errno.ENOTEMPTY) or reuse is None:
                    raise
                reuse(path)
        finally:
            if not renamed:
                _clean(fd)
                os.rmdir(temporary, dir_fd=parent)
            os.close(fd)
    return path


def write_new_file(path, data):
    path = preflight_output(path, new=True)
    if not isinstance(data, bytes):
        raise ValueError("output must contain captured bytes")
    with directory(path.parent, create=True) as parent:
        temporary = ".listing-" + uuid.uuid4().hex
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o644,
            dir_fd=parent,
        )
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
            os.link(
                temporary,
                path.name,
                src_dir_fd=parent,
                dst_dir_fd=parent,
                follow_symlinks=False,
            )
        finally:
            os.unlink(temporary, dir_fd=parent)
    return path
