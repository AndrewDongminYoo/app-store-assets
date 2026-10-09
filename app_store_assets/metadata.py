"""Complete public metadata types and explicit target-aware diffs."""

import collections
import copy

from .contracts import (
    digest,
    exact_keys,
    hash_inventory,
    image_entry,
    locale,
    public_path,
    public_text,
    public_url,
    target_identity,
    version,
)
from .records import record_digest

PUBLIC_FIELDS = {
    "name",
    "title",
    "subtitle",
    "description",
    "full_description",
    "short_description",
    "keywords",
    "promotional_text",
    "release_notes",
    "support_url",
    "marketing_url",
    "privacy_url",
    "copyright",
    "video",
}
IMAGE_FIELDS = {
    "id",
    "file",
    "sha256",
    "source_sha256",
    "provider_sha256",
    "processing_state",
    "width",
    "height",
    "size",
}


def text(value):
    if not isinstance(value, str) or "\x00" in value:
        raise ValueError("metadata field must be public text")
    return value


def has_selected_binary(target, remote):
    if not remote:
        return False
    identity = target_identity(
        {
            k: target[k]
            for k in target
            if k
            in {
                "store",
                "platform",
                "account",
                "account_id",
                "app_id",
                "flavor",
                "stage",
                "version",
                "track",
            }
        }
    )
    remote = validate_public_metadata(remote, identity)
    return (
        remote.get("binary") is not None
        if identity["store"] == "apple"
        else bool(remote.get("build_exists"))
    )


def remote_observation(record):
    result = validate_public_metadata(
        record, record.get("target") if isinstance(record, dict) else None
    )
    for groups in result.get("images", {}).values():
        for images in groups.values():
            for image in images:
                image.pop("file", None)
                image.pop("sha256", None)
    return result


def normalize_fields(fields):
    if not isinstance(fields, dict):
        raise ValueError("unsupported public metadata mapping")
    result = {}
    for name, values in fields.items():
        locale(name)
        exact_keys(values, PUBLIC_FIELDS)
        clean = {}
        for key, value in values.items():
            text(value)
            if value and (key.endswith("_url") or key == "video"):
                public_url(value)
            clean[key] = value
        result[name] = clean
    return result


def normalize_remote(record, target):
    # Validate all supplied keys before normalizing any provider observation.
    result = validate_public_metadata(record, target)
    if result["type"] != "metadata-snapshot":
        raise ValueError("download requires a public metadata-snapshot")
    result["origin"] = "remote"
    return validate_public_metadata(result, target)


def _selected_notes(record):
    target = record["target"]
    notes = copy.deepcopy(record.get("release_notes", {}))
    if target["store"] == "google" and "releases" in record:
        matches = [
            release
            for release in record["releases"]
            if target["version"]["build"] in release["version_codes"]
        ]
        if len(matches) > 1:
            raise ValueError("ambiguous selected track release notes")
        supplied = matches[0].get("notes", {}) if matches else {}
        if notes and notes != supplied:
            raise ValueError("conflicting selected release notes")
        notes = supplied
    return notes


def selected_notes(record):
    clean = validate_public_metadata(
        record, record.get("target") if isinstance(record, dict) else None
    )
    return _selected_notes(clean)


def validate_public_metadata(record, target):
    """Validate the entire supplied public record, without freshness/auth claims."""
    from .catalog import validate_fields

    allowed = {
        "schema_version",
        "type",
        "target",
        "origin",
        "fields",
        "images",
        "revision",
        "version_id",
        "editable",
        "review_active",
        "app_info_id",
        "binary",
        "build_exists",
        "releases",
        "effects",
        "release_notes",
        "changelogs",
        "source_snapshot",
        "source_export",
        "inputs",
    }
    exact_keys(record, allowed, {"schema_version", "type", "target"})
    if (
        type(record["schema_version"]) is not int
        or record["schema_version"] != 1
        or record["type"] not in ("metadata", "metadata-snapshot", "metadata-import")
    ):
        raise ValueError("unsupported public metadata schema/type")
    identity = target_identity(record["target"])
    if identity != target_identity(target):
        raise ValueError("public metadata target differs")
    clean = copy.deepcopy(record)
    clean["fields"] = validate_fields(
        clean.get("fields", {}),
        identity["store"],
        proposed=clean["type"] != "metadata-snapshot",
    )
    for key in ("origin", "revision", "version_id", "app_info_id"):
        if key in clean and clean[key] is not None:
            public_text(clean[key], "metadata " + key, empty=True)
    if "source_snapshot" in clean:
        public_path(clean["source_snapshot"])
    if "source_export" in clean:
        digest(clean["source_export"])
    for key in ("editable", "review_active", "build_exists"):
        if key in clean and clean[key] is not None and type(clean[key]) is not bool:
            raise ValueError("invalid public metadata state: " + key)
    if "inputs" in clean:
        hash_inventory(clean["inputs"])
    for key in ("changelogs", "release_notes"):
        if key in clean and not isinstance(clean[key], dict):
            raise ValueError("invalid public metadata mapping: " + key)
    for name, path in clean.get("changelogs", {}).items():
        locale(name)
        public_path(path)
    binary = clean.get("binary")
    if binary is not None:
        keys = {"app_id", "platform", "version", "processing_state", "source_sha256"}
        exact_keys(binary, keys, keys - {"source_sha256"})
        version(binary["version"])
        if any(
            binary[key] != identity[key] for key in ("app_id", "platform", "version")
        ):
            raise ValueError("binary observation target differs")
        public_text(binary["processing_state"], "public binary state")
        if "source_sha256" in binary and binary["source_sha256"] is not None:
            digest(binary["source_sha256"])
    images = clean.get("images", {})
    if not isinstance(images, dict):
        raise ValueError("unsupported public image mapping")
    for name, groups in images.items():
        locale(name)
        if not isinstance(groups, dict):
            raise ValueError("unsupported public image groups")
        for slot, items in groups.items():
            image_entry({"locale": name, "slot": slot}, grouped=True)
            if not isinstance(items, list):
                raise ValueError("unsupported public image group")
            for item in items:
                image_entry(item)
    if "effects" in clean:
        effects = clean["effects"]
        if not isinstance(effects, list) or any(
            not isinstance(v, str) or v not in {"read", "open-read-session"}
            for v in effects
        ):
            raise ValueError("supplied metadata must declare only read effects")
    if "releases" in clean:
        if identity["store"] != "google" or not isinstance(clean["releases"], list):
            raise ValueError("unsupported public track releases")
        for release in clean["releases"]:
            exact_keys(
                release, {"name", "status", "version_codes", "notes"}, {"version_codes"}
            )
            for key in ("name", "status"):
                if key in release and release[key] is not None:
                    public_text(release[key], "public release " + key, empty=True)
            codes = release["version_codes"]
            if not isinstance(codes, list) or any(
                not isinstance(code, str) or not code.isascii() or not code.isdigit()
                for code in codes
            ):
                raise ValueError("release requires explicit version_codes")
            notes = release.get("notes", {})
            if not isinstance(notes, dict):
                raise ValueError("invalid public release-notes mapping")
            for name, note in notes.items():
                normalize_fields({name: {"release_notes": note}})
                if len(note) > 500:
                    raise ValueError("release-notes limit exceeded")
    for name, note in clean.get("release_notes", {}).items():
        normalize_fields({name: {"release_notes": note}})
        if identity["store"] == "google" and len(note) > 500:
            raise ValueError("release-notes limit exceeded")
    _selected_notes(clean)
    return clean


def metadata_diff(before, after):
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise ValueError("invalid metadata diff record")
    if before.get("target") != after.get("target"):
        raise ValueError("metadata diff target/version conflict")
    before = validate_public_metadata(before, before["target"])
    after = validate_public_metadata(after, before["target"])
    before["release_notes"] = selected_notes(before)
    after["release_notes"] = selected_notes(after)
    changes = []

    def visit(path, a, b):
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(set(a) | set(b)):
                name = path + "." + key if path else key
                if key not in a:
                    changes.append({"path": name, "kind": "add", "after": b[key]})
                elif key not in b:
                    changes.append({"path": name, "kind": "remove", "before": a[key]})
                else:
                    visit(name, a[key], b[key])
        elif a != b:
            kind = "change"
            if isinstance(a, list) and isinstance(b, list):
                if collections.Counter(map(record_digest, a)) == collections.Counter(
                    map(record_digest, b)
                ):
                    kind = "reorder"
            changes.append({"path": path, "kind": kind, "before": a, "after": b})

    for key in ("fields", "images", "release_notes"):
        a, b = copy.deepcopy(before.get(key, {})), copy.deepcopy(after.get(key, {}))
        if key == "images":
            for record in (a, b):
                for groups in record.values():
                    for images in groups.values():
                        for image in images:
                            image.pop("file", None)
        visit(key, a, b)
    return changes
