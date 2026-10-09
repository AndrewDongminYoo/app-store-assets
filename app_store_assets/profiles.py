"""Public offline configuration; effect descriptors are deliberately unsupported."""

import copy
import re

from .contracts import exact_keys, locale, public_path, public_text, runtime_record
from .contracts import target_identity as validate_identity
from .contracts import version as validate_version
from .records import read_json, read_text, relative_path, safe_path

TOP_KEYS = {"schema_version", "type", "project", "mode", "runtime", "targets"}
TARGET_KEYS = {
    "store",
    "platform",
    "account",
    "account_id",
    "app_id",
    "flavor",
    "stage",
    "version",
    "version_source",
    "inputs",
    "artifact",
    "metadata",
    "remote",
    "track",
    "release_status",
    "replacement",
    "changelogs",
    "assets",
}
IDENTITY_KEYS = ("store", "platform", "account", "app_id", "flavor", "stage", "version")


def text(value, label):
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        raise ValueError("invalid " + label)
    return value


def target_identity(target):
    result = {key: target[key] for key in IDENTITY_KEYS}
    if target["store"] == "google":
        result["track"] = target["track"]
    if "account_id" in target:
        result["account_id"] = target["account_id"]
    return validate_identity(result)


def validate_target_shape(target):
    exact_keys(target, TARGET_KEYS, IDENTITY_KEYS[:-1] + ("inputs",))
    value = dict(target)
    if "version" in value:
        validate_version(value["version"])
    elif "version_source" in value:
        value["version"] = {"name": "0", "build": "0"}
    else:
        raise ValueError("target requires version or version source")
    target_identity(value)
    if "version_source" in target:
        exact_keys(target["version_source"], {"file"}, {"file"})
        public_path(target["version_source"]["file"])
    inputs = target["inputs"]
    if (
        not isinstance(inputs, list)
        or not inputs
        or any(not isinstance(v, str) for v in inputs)
        or len(set(inputs)) != len(inputs)
    ):
        raise ValueError("declared public source inventory is required")
    for item in inputs:
        public_path(item)
    for key in ("metadata", "remote"):
        if key in target:
            public_path(target[key])
    if "artifact" in target:
        value = target["artifact"]
        exact_keys(value, {"path", "record", "kind"}, {"path", "record", "kind"})
        public_path(value["path"])
        public_path(value["record"])
        public_text(value["kind"], "artifact kind")
        if value["kind"] not in {"apk", "aab", "ipa"}:
            raise ValueError("unsupported artifact kind")
    if "assets" in target:
        exact_keys(target["assets"], {"manifest"}, {"manifest"})
        public_path(target["assets"]["manifest"])
    if "replacement" in target:
        value = target["replacement"]
        exact_keys(
            value,
            {"locales", "slots", "allow_delete"},
            {"locales", "slots", "allow_delete"},
        )
        if type(value["allow_delete"]) is not bool:
            raise ValueError("invalid replacement deletion policy")
        for key in ("locales", "slots"):
            if (
                not isinstance(value[key], list)
                or not value[key]
                or any(not isinstance(v, str) for v in value[key])
                or len(set(value[key])) != len(value[key])
            ):
                raise ValueError("invalid replacement groups")
        for item in value["locales"]:
            locale(item)
        for item in value["slots"]:
            if not re.fullmatch(r"[A-Za-z0-9_-]+", item):
                raise ValueError("invalid replacement slot")
    if "changelogs" in target:
        if not isinstance(target["changelogs"], dict):
            raise ValueError("invalid changelog mapping")
        for key, item in target["changelogs"].items():
            locale(key)
            public_path(item)
    if target["store"] == "google":
        if target.get("release_status") not in ("draft", "completed"):
            raise ValueError("Google requires explicit release_status")
    elif "release_status" in target:
        raise ValueError("Apple has no Google release status")


def load_profile(root, path, name, captures=None):
    profile = read_json(safe_path(root, path), captures)
    exact_keys(profile, TOP_KEYS, TOP_KEYS)
    if (
        type(profile["schema_version"]) is not int
        or profile["schema_version"] != 1
        or profile["type"] != "offline-profile"
        or profile["mode"] not in ("fixture", "live")
    ):
        raise ValueError("unsupported offline profile schema/mode")
    text(profile["project"], "project")
    exact_keys(
        profile["runtime"],
        {"path", "url", "commit", "files"},
        {"path", "url", "commit", "files"},
    )
    relative_path(profile["runtime"]["path"])
    runtime_record(profile["runtime"], pin=True)
    if (
        not isinstance(profile["targets"], dict)
        or not profile["targets"]
        or name not in profile["targets"]
    ):
        raise ValueError("unknown target")
    for target_name, value in profile["targets"].items():
        public_text(target_name, "target name")
        validate_target_shape(value)
    target = copy.deepcopy(profile["targets"][name])
    exact_keys(target, TARGET_KEYS, IDENTITY_KEYS[:-1] + ("inputs",))
    for key in IDENTITY_KEYS[:-1]:
        text(target[key], "target " + key)
    if (
        target["store"] not in ("apple", "google")
        or target["platform"]
        not in {"apple": ("ios", "macos"), "google": ("android",)}[target["store"]]
    ):
        raise ValueError("store/platform mismatch")
    if not re.fullmatch("[A-Za-z0-9_.-]+", target["app_id"]):
        raise ValueError("invalid app identifier")
    if "account_id" in target:
        text(target["account_id"], "account_id")
    if "version_source" in target:
        exact_keys(target["version_source"], {"file"}, ("file",))
        version_file = safe_path(root, target["version_source"]["file"])
        matches = re.findall(
            "^version:\\s*([^\\s+]+)\\+([0-9]+)\\s*$",
            read_text(version_file, captures),
            re.MULTILINE,
        )
        if len(matches) != 1:
            raise ValueError("version source must contain one exact pubspec version")
        derived = dict(zip(("name", "build"), matches[0], strict=True))
        if "version" in target and target["version"] != derived:
            raise ValueError("configured version differs from source")
        target["version"] = derived
    exact_keys(target.get("version"), {"name", "build"}, ("name", "build"))
    version = target["version"]
    if (
        not isinstance(version["name"], str)
        or not re.fullmatch("[0-9]+(?:\\.[0-9]+){0,3}", version["name"])
        or (not isinstance(version["build"], str))
        or (not re.fullmatch("[0-9]+", version["build"]))
    ):
        raise ValueError("version requires numeric name/build strings")
    if not isinstance(target["inputs"], list) or not target["inputs"]:
        raise ValueError("declared public source inventory is required")
    for item in target["inputs"]:
        relative_path(item)
    for key in ("metadata", "remote"):
        if key in target:
            relative_path(target[key])
    if target["store"] == "google":
        text(target.get("track"), "Google track")
        if target.get("release_status") not in ("draft", "completed"):
            raise ValueError("Google requires explicit release_status")
    elif "track" in target or "release_status" in target:
        raise ValueError("Apple has no Google track/release_status")
    if "changelogs" in target:
        if not isinstance(target["changelogs"], dict):
            raise ValueError("changelogs must be a locale/path object")
        for item in target["changelogs"].values():
            p = relative_path(item)
            if "changelogs" in p.parts and p.name != version["build"] + ".txt":
                raise ValueError("changelog differs from target build")
    return (profile, target)
