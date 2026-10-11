"""Offline container kind binding, not a native inspector or transport policy."""

import hashlib
import os
import stat
import struct
import tempfile
import zipfile
from contextlib import nullcontext
from pathlib import Path

from .identity import git
from .profiles import exact_keys
from .record_types import validate_build
from .records import (
    FILE_LIMIT,
    bind_capture,
    file_digest,
    identity,
    inventory,
    open_read,
    read_json,
    safe_path,
)
from .snapshots import validate_snapshot

ENTRY_LIMIT = 100000
DIRECTORY_LIMIT = 64 * 1024 * 1024


def _preflight_directory(source):
    # Match the stdlib's bounded EOCD/ZIP64 reader and prefix-offset arithmetic.
    # Scan fixed headers without allocating ZipInfo objects or directory bytes.
    end = zipfile._EndRecData(source)
    if end is None:
        raise ValueError("artifact container cannot be read")
    size = end[zipfile._ECD_SIZE]
    count = end[zipfile._ECD_ENTRIES_TOTAL]
    if size > DIRECTORY_LIMIT or count > ENTRY_LIMIT:
        raise ValueError("oversized artifact central directory bound")
    if (
        end[zipfile._ECD_DISK_NUMBER]
        or end[zipfile._ECD_DISK_START]
        or end[zipfile._ECD_ENTRIES_THIS_DISK] != count
    ):
        raise ValueError("unsupported split artifact container")
    start = end[zipfile._ECD_LOCATION] - size
    if end[zipfile._ECD_SIGNATURE] == zipfile.stringEndArchive64:
        start -= zipfile.sizeEndCentDir64 + zipfile.sizeEndCentDir64Locator
    if start < 0:
        raise ValueError("invalid artifact central directory offset")
    source.seek(start)
    consumed = observed = 0
    while consumed < size:
        header = source.read(zipfile.sizeCentralDir)
        if len(header) != zipfile.sizeCentralDir:
            raise ValueError("truncated artifact central directory")
        fields = struct.unpack(zipfile.structCentralDir, header)
        if fields[zipfile._CD_SIGNATURE] != zipfile.stringCentralDir:
            raise ValueError("invalid artifact central directory header")
        consumed += zipfile.sizeCentralDir + sum(fields[12:15])
        observed += 1
        if consumed > size or observed > ENTRY_LIMIT:
            raise ValueError("oversized artifact central directory bound")
        source.seek(sum(fields[12:15]), os.SEEK_CUR)
    if observed != count:
        raise ValueError("artifact central directory entry count differs")
    source.seek(0)


def container_kind(path):
    opened = open_read(path) if isinstance(path, (str, Path)) else nullcontext(path)
    with opened as source, tempfile.TemporaryFile() as captured:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > FILE_LIMIT:
            raise ValueError("artifact exceeds byte bound")
        source.seek(0)
        count = 0
        for block in iter(lambda: source.read(1024 * 1024), b""):
            count += len(block)
            if count > FILE_LIMIT:
                raise ValueError("artifact exceeds byte bound")
            captured.write(block)
        if identity(before) != identity(os.fstat(source.fileno())):
            raise ValueError("artifact changed during capture")
        captured.seek(0)
        return _container_kind(captured)


def _container_kind(path):
    try:
        _preflight_directory(path)
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) > ENTRY_LIMIT or len(names) != len(set(names)):
                raise ValueError("ambiguous or oversized artifact container")
            names = set(names)
            kinds = []
            if "AndroidManifest.xml" in names:
                kinds.append("apk")
            if {"BundleConfig.pb", "base/manifest/AndroidManifest.xml"} <= names:
                kinds.append("aab")
            infos = [
                n
                for n in names
                if n.startswith("Payload/")
                and n.endswith(".app/Info.plist")
                and (len(n.split("/")) == 3)
            ]
            if len(infos) == 1:
                kinds.append("ipa")
            if len(kinds) != 1:
                raise ValueError("unsupported or ambiguous artifact container kind")
            return kinds[0]
    except (
        zipfile.BadZipFile,
        OSError,
        struct.error,
        UnicodeError,
        NotImplementedError,
    ) as error:
        raise ValueError("artifact container cannot be read") from error


def artifact_record(root, profile, target, captures=None):
    descriptor = target.get("artifact")
    exact_keys(descriptor, {"path", "record", "kind"}, ("path", "record", "kind"))
    kind = descriptor["kind"]
    supported = {("google", "android"): ("apk", "aab"), ("apple", "ios"): ("ipa",)}
    if kind not in supported.get((target["store"], target["platform"]), ()):
        raise ValueError("unsupported artifact kind/platform")
    path = safe_path(root, descriptor["path"])
    record = read_json(safe_path(root, descriptor["record"]), captures)
    if not isinstance(record, dict):
        raise ValueError("invalid supplied build record")
    if record.get("type") == "snapshot":
        record = validate_snapshot(
            safe_path(root, descriptor["record"]).parent, captures
        )["record"]
    record = validate_build(
        record,
        {
            k: v
            for k, v in target.items()
            if k
            in (
                "store",
                "platform",
                "account",
                "account_id",
                "app_id",
                "flavor",
                "stage",
                "version",
                "track",
            )
        },
    )
    if record.get("schema_version") != 1 or record.get("type") != "build":
        raise ValueError("unsupported build record")
    for key in ("app_id", "platform", "flavor", "version"):
        if record.get(key) != target[key]:
            raise ValueError("artifact build identity differs: " + key)
    if record.get("kind") != kind or path.suffix != "." + kind:
        raise ValueError("artifact kind record/extension differs")
    if file_digest(path) != record.get("sha256"):
        raise ValueError("artifact hash differs from build record")
    # The classifier reads only a captured stream bound to the supplied digest.
    with (
        open_read(path) as source,
        tempfile.TemporaryFile() as captured,
    ):
        observed = hashlib.sha256()
        source.seek(0)
        count = 0
        for block in iter(lambda: source.read(1024 * 1024), b""):
            count += len(block)
            if count > FILE_LIMIT:
                raise ValueError("artifact exceeds byte bound")
            observed.update(block)
            captured.write(block)
        if observed.hexdigest() != record["sha256"]:
            raise ValueError("artifact changed while capturing container")
        captured.seek(0)
        if _container_kind(captured) != kind:
            raise ValueError("artifact container kind differs")
    if file_digest(path) != record["sha256"]:
        raise ValueError("artifact changed during container validation")
    bind_capture(captures, path, record["sha256"])
    if record.get("evidence") not in ("fixture", "inspected"):
        raise ValueError("artifact inspection declaration is missing")
    if profile["mode"] == "live":
        if record["evidence"] != "inspected":
            raise ValueError("fixture build is not live inspection")
        guards = record.get("native_guards", {})
        if (
            not isinstance(guards, dict)
            or not guards
            or any(v is not True for v in guards.values())
        ):
            raise ValueError("native guard declarations missing/failed")
        if (
            not record.get("source_inputs")
            or not record.get("source_commit")
            or (not record.get("inspector"))
        ):
            raise ValueError("native source/inspection declaration missing")
        if git(root, "rev-parse", "HEAD") != record["source_commit"]:
            raise ValueError("artifact source commit differs")
        source_inputs = inventory(root, record.get("adapter", {}).get("inputs", []))
        if source_inputs != record["source_inputs"]:
            raise ValueError("artifact source inputs differ")
        for name, digest in source_inputs.items():
            bind_capture(captures, safe_path(root, name), digest)
    return record
