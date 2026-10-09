"""Offline container kind binding, not a native inspector or transport policy."""

import hashlib
import os
import tempfile
import zipfile

from .identity import git
from .profiles import exact_keys
from .records import file_digest, inventory, read_json, safe_path
from .snapshots import validate_snapshot


def container_kind(path):
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) > 100000 or len(names) != len(set(names)):
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
    except (zipfile.BadZipFile, OSError) as error:
        raise ValueError("artifact container cannot be read") from error


def artifact_record(root, profile, target):
    descriptor = target.get("artifact")
    exact_keys(descriptor, {"path", "record", "kind"}, ("path", "record", "kind"))
    kind = descriptor["kind"]
    supported = {("google", "android"): ("apk", "aab"), ("apple", "ios"): ("ipa",)}
    if kind not in supported.get((target["store"], target["platform"]), ()):
        raise ValueError("unsupported artifact kind/platform")
    path = safe_path(root, descriptor["path"])
    record = read_json(safe_path(root, descriptor["record"]))
    if record.get("type") == "snapshot":
        record = validate_snapshot(safe_path(root, descriptor["record"]).parent)[
            "record"
        ]
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
        os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as source,
        tempfile.TemporaryFile() as captured,
    ):
        observed = hashlib.sha256()
        for block in iter(lambda: source.read(1024 * 1024), b""):
            observed.update(block)
            captured.write(block)
        if observed.hexdigest() != record["sha256"]:
            raise ValueError("artifact changed while capturing container")
        captured.seek(0)
        if container_kind(captured) != kind:
            raise ValueError("artifact container kind differs")
    if file_digest(path) != record["sha256"]:
        raise ValueError("artifact changed during container validation")
    if record.get("evidence") not in ("fixture", "inspected"):
        raise ValueError("artifact inspection declaration is missing")
    if profile["mode"] == "live":
        if record["evidence"] != "inspected":
            raise ValueError("fixture build is not live inspection")
        guards = record.get("native_guards", {})
        if (
            not isinstance(guards, dict)
            or not guards
            or any((v is not True for v in guards.values()))
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
        if (
            inventory(root, record.get("adapter", {}).get("inputs", []))
            != record["source_inputs"]
        ):
            raise ValueError("artifact source inputs differ")
    return record
