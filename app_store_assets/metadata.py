"""Public metadata snapshots and explicit target-aware diffs."""

import collections
import copy
import re
from urllib.parse import parse_qs, urlsplit

from .records import public_input_name, record_digest, relative_path

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
}


def has_selected_binary(target, remote):
    if not remote:
        return False
    if target["store"] == "apple":
        return remote.get("binary") is not None
    return target["store"] == "google" and bool(remote.get("build_exists"))


def remote_observation(record):
    """Remove only local download annotations; retain provider state and order."""
    result = copy.deepcopy(record)
    for groups in result.get("images", {}).values():
        for images in groups.values():
            for image in images:
                image.pop("file", None)
                image.pop("sha256", None)
    return result


def normalize_fields(fields):
    result = {}
    for locale, values in fields.items():
        if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", locale):
            raise ValueError("unsupported metadata locale")
        if set(values) - PUBLIC_FIELDS:
            raise ValueError("unsupported/private metadata field")
        clean = {}
        for key, value in values.items():
            if not isinstance(value, str) or "\x00" in value:
                raise ValueError("metadata field must be public text")
            if key.endswith("_url") or key == "video":
                if not value:
                    clean[key] = value
                    continue
                if any(c.isspace() or ord(c) < 32 for c in value) or "\\" in value:
                    raise ValueError("invalid public URL")
                try:
                    parsed = urlsplit(value)
                    _port = parsed.port
                    host = parsed.hostname
                except ValueError as error:
                    raise ValueError("invalid public URL") from error
                if parsed.scheme not in ("http", "https") or not host:
                    raise ValueError("public URL requires HTTP(S) protocol and host")
                if (
                    parsed.username
                    or parsed.password
                    or any(
                        re.search("token|secret|signature|password|credential", k, re.I)
                        for k in parse_qs(parsed.query, keep_blank_values=True)
                    )
                ):
                    raise ValueError(
                        "private credential URL cannot enter public metadata"
                    )
            clean[key] = value
        result[locale] = clean
    return result


def normalize_remote(record, target):
    if record.get("target") != target:
        raise ValueError("downloaded metadata target differs")
    effects = record.get("effects", ["read"])
    if not isinstance(effects, list) or set(effects) - {"read", "open-read-session"}:
        raise ValueError("download must be read-only; commit/write effect is forbidden")
    result = {
        "schema_version": 1,
        "type": "metadata-snapshot",
        "origin": "remote",
        "target": copy.deepcopy(target),
        "fields": normalize_fields(record.get("fields", {})),
        "images": {},
    }
    for key in (
        "revision",
        "version_id",
        "editable",
        "review_active",
        "app_info_id",
        "binary",
        "build_exists",
        "releases",
        "effects",
    ):
        if key in record:
            result[key] = copy.deepcopy(record[key])
    for locale, groups in record.get("images", {}).items():
        normalize_fields({locale: {}})
        result["images"][locale] = {}
        for slot, images in groups.items():
            if not re.fullmatch(r"[A-Za-z0-9_-]+", slot) or not isinstance(
                images, list
            ):
                raise ValueError("unsupported image group")
            result["images"][locale][slot] = [
                {k: copy.deepcopy(v) for k, v in item.items() if k in IMAGE_FIELDS}
                for item in images
            ]
    return result


def selected_notes(record):
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


def validate_public_metadata(record, target):
    """Validate supplied public records, without any freshness/authentication claim."""
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
    if not isinstance(record, dict) or set(record) - allowed:
        raise ValueError("unsupported/private public metadata record key")
    if record.get("schema_version") != 1 or record.get("type") not in (
        "metadata",
        "metadata-snapshot",
        "metadata-import",
    ):
        raise ValueError("unsupported public metadata schema/type")
    if record.get("target") != target:
        raise ValueError("public metadata target differs")
    clean = copy.deepcopy(record)
    clean["fields"] = validate_fields(
        clean.get("fields", {}),
        target["store"],
        proposed=clean["type"] != "metadata-snapshot",
    )

    def public_text(value):
        return isinstance(value, str) and "\x00" not in value

    for key in (
        "origin",
        "revision",
        "version_id",
        "app_info_id",
        "source_snapshot",
        "source_export",
    ):
        if key in clean and clean[key] is not None and not public_text(clean[key]):
            raise ValueError("invalid public metadata text value: " + key)
    for key in ("editable", "review_active", "build_exists"):
        if key in clean and clean[key] is not None and type(clean[key]) is not bool:
            raise ValueError("invalid public metadata state value: " + key)
    for key in ("inputs", "changelogs", "release_notes"):
        if key in clean and not isinstance(clean[key], dict):
            raise ValueError("invalid public metadata mapping: " + key)
    for name, digest in clean.get("inputs", {}).items():
        public_input_name(relative_path(name))
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("invalid public input hash")
    for locale, name in clean.get("changelogs", {}).items():
        normalize_fields({locale: {}})
        public_input_name(relative_path(name))
    binary = clean.get("binary")
    if binary is not None:
        keys = {"app_id", "platform", "version", "processing_state", "source_sha256"}
        if not isinstance(binary, dict) or set(binary) - keys:
            raise ValueError("unsupported public binary observation")
        if any(
            binary.get(key) != target[key] for key in ("app_id", "platform", "version")
        ):
            raise ValueError("binary observation target differs")
        if not public_text(binary.get("processing_state")):
            raise ValueError("invalid public binary state")
        digest = binary.get("source_sha256")
        if digest is not None and (
            not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            raise ValueError("invalid public binary hash")
    images = clean.get("images", {})
    if not isinstance(images, dict):
        raise ValueError("unsupported public image mapping")
    for locale, groups in images.items():
        normalize_fields({locale: {}})
        if not isinstance(groups, dict):
            raise ValueError("unsupported public image groups")
        for slot, items in groups.items():
            if not re.fullmatch(r"[A-Za-z0-9_-]+", slot) or not isinstance(items, list):
                raise ValueError("unsupported public image group")
            for item in items:
                if not isinstance(item, dict) or set(item) - IMAGE_FIELDS - {"size"}:
                    raise ValueError("unsupported/private public image field")
                for key, value in item.items():
                    if key in ("width", "height"):
                        if type(value) is not int or value <= 0:
                            raise ValueError("invalid public image dimension")
                    elif key == "size":
                        if (
                            not isinstance(value, list)
                            or len(value) != 2
                            or any(type(v) is not int or v <= 0 for v in value)
                        ):
                            raise ValueError("invalid public image size")
                    elif value is not None and not public_text(value):
                        raise ValueError("invalid public image text value")
                    if key == "file":
                        public_input_name(relative_path(value))

    if "effects" in clean and (
        not isinstance(clean["effects"], list)
        or set(clean["effects"]) - {"read", "open-read-session"}
    ):
        raise ValueError("supplied metadata must declare only read effects")
    if "releases" in clean:
        if target["store"] != "google" or not isinstance(clean["releases"], list):
            raise ValueError("unsupported public track releases")
        for release in clean["releases"]:
            if not isinstance(release, dict) or set(release) - {
                "name",
                "status",
                "version_codes",
                "notes",
            }:
                raise ValueError("unsupported public track release field")

            for key in ("name", "status"):
                if (
                    key in release
                    and release[key] is not None
                    and not public_text(release[key])
                ):
                    raise ValueError("invalid public release text value")
            if not isinstance(release.get("notes", {}), dict):
                raise ValueError("invalid public release-notes mapping")
            codes = release.get("version_codes")
            if not isinstance(codes, list) or any(
                not isinstance(code, str) or not code.isdigit() for code in codes
            ):
                raise ValueError("release requires explicit version_codes")
            for locale, note in release.get("notes", {}).items():
                normalize_fields({locale: {"release_notes": note}})
                if len(note) > 500:
                    raise ValueError("release-notes limit exceeded")
    for locale, note in clean.get("release_notes", {}).items():
        normalize_fields({locale: {"release_notes": note}})
        if target["store"] == "google" and len(note) > 500:
            raise ValueError("release-notes limit exceeded")
    selected_notes(clean)
    return clean


def metadata_diff(before, after):
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
