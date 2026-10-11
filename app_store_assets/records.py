"""Canonical records and descriptor-confined, bounded public input reads."""

import hashlib
import json
import os
import stat
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

TEXT_LIMIT = 8 * 1024 * 1024
FILE_LIMIT = 1024 * 1024 * 1024


class _PublicPath(type(Path())):
    """A path validated relative to an explicit caller-owned trusted root."""

    __slots__ = ("_trusted_root",)


def canonical(value):
    return (
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode()


def record_digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def bind_capture(captures, path, digest):
    if captures is not None:
        path = (
            path.absolute() if isinstance(path, _PublicPath) else Path(path).absolute()
        )
        if path in captures and captures[path] != digest:
            raise ValueError("input changed between captures")
        captures[path] = digest


def relative_path(value):
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or any(ord(c) < 32 for c in value)
    ):
        raise ValueError("invalid relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or str(path) != value or value == ".":
        raise ValueError("path must be canonical and relative")
    return path


def public_input_name(path):
    for part in Path(path).parts:
        lower = part.lower()
        if lower in {
            ".git",
            ".ssh",
            ".aws",
            ".codex",
            "id_rsa",
            "id_ed25519",
            "id_ecdsa",
            "authorized_keys",
            ".env",
            "key.properties",
        }:
            raise ValueError("private credential input cannot enter public inventory")
        if lower.startswith(".env.") or lower.endswith(
            (".key", ".p8", ".p12", ".pem", ".jks", ".keystore", ".mobileprovision")
        ):
            raise ValueError("private credential input cannot enter public inventory")
        if any(
            word in lower
            for word in ("service-account", "service_account", "credentials.json")
        ):
            raise ValueError("credential input cannot enter public inventory")


def safe_path(root, relative):
    # Trusted entry roots are canonicalized once by their caller. Child paths
    # are never resolved through symlinks. Opening remains independently safe.
    root = Path(root).absolute()
    path = relative_path(relative)
    public_input_name(path)
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("symlink input is not allowed")
    result = _PublicPath(current)
    result._trusted_root = root
    return result


@contextmanager
def open_directory(path):
    path = Path(path).absolute()
    # Callers validate untrusted components relative to their trusted root.
    # Ancestors still open descriptor-by-descriptor without following symlinks.
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
            )
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


@contextmanager
def open_read(path):
    trusted_root = (
        getattr(path, "_trusted_root", None) if isinstance(path, _PublicPath) else None
    )
    path = Path(path).absolute()
    # Raw path helpers retain complete private-component checks. Only safe_path
    # supplies an explicit root, and every child is checked again before access.
    public_input_name(path if trusted_root is None else path.relative_to(trusted_root))
    try:
        with open_directory(path.parent) as parent:
            fd = os.open(
                path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
            )
    except OSError as error:
        raise ValueError("missing input, symlink or unsafe public parent") from error
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("public input must be a regular file")
        yield stream


def identity(st):
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns


def capture_bytes(path, limit=TEXT_LIMIT, captures=None):
    with open_read(path) as stream:
        before = os.fstat(stream.fileno())
        if before.st_size > limit:
            raise ValueError("public input exceeds byte bound")
        data = stream.read(limit + 1)
        if len(data) > limit or identity(before) != identity(os.fstat(stream.fileno())):
            raise ValueError("input changed during bounded capture")
    bind_capture(captures, path, hashlib.sha256(data).hexdigest())
    return data


def read_text(path, captures=None):
    return (
        capture_bytes(path, captures=captures)
        .decode("utf-8")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )


def read_json(path, captures=None):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    return json.loads(
        read_text(path, captures),
        object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(
            ValueError("non-finite JSON value")
        ),
    )


def digest_stream(stream, limit=FILE_LIMIT):
    before = os.fstat(stream.fileno())
    if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
        raise ValueError("public file exceeds regular-file/size contract")
    digest, count = hashlib.sha256(), 0
    for block in iter(lambda: stream.read(min(1024 * 1024, limit - count + 1)), b""):
        count += len(block)
        if count > limit:
            raise ValueError("public file exceeds byte bound")
        digest.update(block)
    if identity(before) != identity(os.fstat(stream.fileno())):
        raise ValueError("input changed while hashing")
    return digest.hexdigest()


def file_digest(path):
    with open_read(path) as stream:
        return digest_stream(stream)


def _walk(fd, prefix, result, excluded=(), *, reserve=False, reservations=None):
    before = identity(os.fstat(fd))
    for name in sorted(os.listdir(fd)):
        if name in excluded:
            continue
        relative = str(prefix / name)
        relative_path(relative)
        public_input_name(relative)
        try:
            child = os.open(
                name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd
            )
        except OSError as error:
            raise ValueError("symlink or changed public directory entry") from error
        try:
            observed = os.fstat(child)
            mode = observed.st_mode
            if stat.S_ISDIR(mode):
                _walk(
                    child,
                    PurePosixPath(relative),
                    result,
                    reserve=reserve,
                    reservations=reservations,
                )
            elif stat.S_ISREG(mode):
                if reserve:
                    if observed.st_size > FILE_LIMIT:
                        raise ValueError("public file exceeds byte bound")
                    result[relative] = observed
                else:
                    if reservations is not None and (
                        relative not in reservations
                        or identity(observed) != identity(reservations[relative])
                    ):
                        raise ValueError("public inventory changed after reservation")
                    with os.fdopen(os.dup(child), "rb") as stream:
                        result[relative] = digest_stream(
                            stream,
                            limit=observed.st_size
                            if reservations is not None
                            else FILE_LIMIT,
                        )
            else:
                raise ValueError("unsupported public input type")
        finally:
            os.close(child)
    if before != identity(os.fstat(fd)):
        raise ValueError("public directory changed during inventory")


def tree_inventory(root, exclude_root=(), *, total_limit=None):
    result = {}
    with open_directory(root) as fd:
        reserved = None
        if total_limit is not None:
            if type(total_limit) is not int or total_limit < 0:
                raise ValueError("invalid public inventory byte bound")
            reserved = {}
            _walk(fd, PurePosixPath("."), reserved, exclude_root, reserve=True)
            if sum(item.st_size for item in reserved.values()) > total_limit:
                raise ValueError("public inventory exceeds total byte bound")
        _walk(fd, PurePosixPath("."), result, exclude_root, reservations=reserved)
        if reserved is not None and set(result) != set(reserved):
            raise ValueError("public inventory changed after reservation")
    return dict(sorted(result.items()))


def inventory(root, paths):
    root, result = Path(root).absolute(), {}
    for name in sorted(set(paths)):
        path = safe_path(root, name)
        try:
            with open_directory(path.parent) as parent:
                fd = os.open(
                    path.name,
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=parent,
                )
        except OSError as error:
            raise ValueError("missing bound input or symlink") from error
        try:
            mode = os.fstat(fd).st_mode
            if stat.S_ISDIR(mode):
                _walk(fd, PurePosixPath(name), result)
            elif stat.S_ISREG(mode):
                with os.fdopen(os.dup(fd), "rb") as stream:
                    result[name] = digest_stream(stream)
            else:
                raise ValueError("unsupported public input type")
        finally:
            os.close(fd)
    return dict(sorted(result.items()))


def verify_inventory(root, expected, exact=False):
    for name, digest in expected.items():
        if file_digest(safe_path(root, name)) != digest:
            raise ValueError("bound input changed")
    if exact and tree_inventory(root) != expected:
        raise ValueError("added file outside reviewed inventory")
