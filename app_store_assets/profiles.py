"""Public offline configuration; effect descriptors are deliberately unsupported."""

import re

from .records import read_json, relative_path, safe_path

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


def exact_keys(value, allowed, required=()):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError("unknown configuration key or invalid offline object")
    if set(required) - set(value):
        raise ValueError("missing required configuration key")


def text(value, label):
    if not isinstance(value, str) or not value or any((ord(c) < 32 for c in value)):
        raise ValueError("invalid " + label)
    return value


def target_identity(target):
    result = {key: target[key] for key in IDENTITY_KEYS}
    if target["store"] == "google":
        result["track"] = target["track"]
    if "account_id" in target:
        result["account_id"] = target["account_id"]
    return result


def load_profile(root, path, name):
    profile = read_json(safe_path(root, path))
    exact_keys(profile, TOP_KEYS, TOP_KEYS)
    if (
        profile["schema_version"] != 1
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
    if (
        not isinstance(profile["targets"], dict)
        or not profile["targets"]
        or name not in profile["targets"]
    ):
        raise ValueError("unknown target")
    target = dict(profile["targets"][name])
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
            version_file.read_text(),
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
