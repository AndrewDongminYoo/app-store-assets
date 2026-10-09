"""Canonical records and bounded, symlink-free content inventories."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath


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


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    if Path(path).stat().st_size > 8 * 1024 * 1024:
        raise ValueError("JSON record is too large")
    return json.loads(
        Path(path).read_text(),
        object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(
            ValueError("non-finite JSON value")
        ),
    )


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
        raise ValueError(f"path must be canonical and relative: {value}")
    return path


def safe_path(root, relative):
    root = Path(root).resolve()
    path = relative_path(relative)
    public_input_name(path)
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"symlink input is not allowed: {relative}")
    return current


def file_digest(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"missing file or symlink: {path.name}")
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
        after = os.fstat(stream.fileno())
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise ValueError(f"input changed while hashing: {path.name}")
    return digest


def public_input_name(path):
    parts = Path(path).parts
    if any(p.lower() in (".git", ".ssh", ".aws", ".codex") for p in parts):
        raise ValueError("private directory cannot enter public inventory")
    lower = Path(path).name.lower()
    if lower in (
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
        "authorized_keys",
    ) or lower.endswith(".key"):
        raise ValueError("private key cannot enter public inventory")
    if (
        lower in (".env", "key.properties")
        or lower.startswith(".env.")
        or lower.endswith(
            (".p8", ".p12", ".pem", ".jks", ".keystore", ".mobileprovision")
        )
    ):
        raise ValueError(
            f"credential/private input cannot enter a public inventory: {lower}"
        )
    if any(
        word in lower
        for word in ("service-account", "service_account", "credentials.json")
    ):
        raise ValueError("credential input cannot enter an inventory")


def inventory(root, paths):
    root = Path(root).resolve()
    result = {}
    for name in sorted(set(paths)):
        path = safe_path(root, name)
        if not path.exists():
            raise ValueError(f"missing bound input: {name}")
        entries = sorted(path.rglob("*")) if path.is_dir() else [path]
        for entry in entries:
            rel = entry.relative_to(root).as_posix()
            safe_path(root, rel)
            public_input_name(rel)
            if entry.is_file():
                result[rel] = file_digest(entry)
            elif not entry.is_dir():
                raise ValueError(f"unsupported input: {rel}")
    return dict(sorted(result.items()))


def verify_inventory(root, expected, exact=False):
    for name, digest in expected.items():
        if file_digest(safe_path(root, name)) != digest:
            raise ValueError(f"bound input changed: {name}")
    if exact:
        root = Path(root)
        for entry in root.rglob("*"):
            name = entry.relative_to(root).as_posix()
            safe_path(root, name)
            if entry.is_file() and name not in expected:
                raise ValueError(f"added file outside reviewed inventory: {name}")
