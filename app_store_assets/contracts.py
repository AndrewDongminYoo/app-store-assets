"""Shared exact public types; no inspection or write implementation."""

import copy
import re
from urllib.parse import parse_qsl, urlsplit

from .records import public_input_name, relative_path

IMAGE_KEYS = {
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
IDENTITY_KEYS = {
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


def exact_keys(value, allowed, required=()):
    if (
        not isinstance(value, dict)
        or set(value) - set(allowed)
        or set(required) - set(value)
    ):
        raise ValueError("unknown/private key or invalid public object")


def public_text(value, label="public text", empty=False):
    if (
        not isinstance(value, str)
        or (not value and not empty)
        or any(ord(c) < 32 for c in value)
    ):
        raise ValueError("invalid " + label)
    return value


def digest(value, length=64):
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9a-f]{" + str(length) + "}", value
    ):
        raise ValueError("invalid public hash")
    return value


def public_path(value):
    path = relative_path(value)
    public_input_name(path)
    return value


def hash_inventory(value):
    if not isinstance(value, dict):
        raise ValueError("invalid public inventory mapping")
    for name, sha in value.items():
        public_path(name)
        digest(sha)
    return value


def locale(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", value
    ):
        raise ValueError("unsupported metadata locale")
    return value


def public_url(value, origin=False):
    public_text(value, "public URL")
    if any(c.isspace() for c in value) or "\\" in value:
        raise ValueError("invalid public URL")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ValueError("invalid public URL protocol/port") from error
    if (
        parsed.scheme not in ({"https"} if origin else {"http", "https"})
        or not parsed.hostname
    ):
        raise ValueError("public URL requires protocol and host")
    if parsed.username is not None or parsed.password is not None or parsed.fragment:
        raise ValueError("credential/fragment URL cannot enter public records")
    seen = set()
    for key, item in parse_qsl(parsed.query, keep_blank_values=True):
        if origin or key not in {"lang", "hl", "locale"} or key in seen:
            raise ValueError("credential or unsupported public URL query")
        locale(item)
        seen.add(key)
    if origin and parsed.query:
        raise ValueError("runtime origin requires a query-free public URL")
    if port is not None and not 0 < port <= 65535:
        raise ValueError("invalid public URL port")
    return value


def version(value):
    exact_keys(value, {"name", "build"}, {"name", "build"})
    if not isinstance(value["name"], str) or not re.fullmatch(
        r"[0-9]+(?:\.[0-9]+){0,3}", value["name"]
    ):
        raise ValueError("invalid numeric version")
    if not isinstance(value["build"], str) or not re.fullmatch(
        r"[0-9]+", value["build"]
    ):
        raise ValueError("invalid numeric build")
    return value


def target_identity(value):
    required = IDENTITY_KEYS - {"account_id", "track"}
    exact_keys(value, IDENTITY_KEYS, required)
    for key in required - {"version"}:
        public_text(value[key], "target " + key)
    if (
        value["store"] not in {"apple", "google"}
        or value["platform"]
        not in {"apple": {"ios", "macos"}, "google": {"android"}}[value["store"]]
    ):
        raise ValueError("store/platform mismatch")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", value["app_id"]):
        raise ValueError("invalid app identifier")
    version(value["version"])
    if "account_id" in value:
        public_text(value["account_id"], "public account label")
    if value["store"] == "google":
        public_text(value.get("track"), "Google track")
    elif "track" in value:
        raise ValueError("Apple has no Google track")
    return copy.deepcopy(value)


def runtime_record(value, pin=False):
    keys = {"url", "commit", "files"} | ({"path"} if pin else set())
    exact_keys(value, keys, keys)
    public_url(value["url"], origin=True)
    digest(value["commit"], 40)
    hash_inventory(value["files"])
    if pin:
        public_path(value["path"])
    return value


def image_entry(value, grouped=False, required_file=False):
    exact_keys(
        value,
        IMAGE_KEYS | ({"locale", "slot"} if grouped else set()),
        {"file"} if required_file else (),
    )
    for key, item in value.items():
        if key in {"width", "height"}:
            if type(item) is not int or item <= 0:
                raise ValueError("invalid public image dimension")
        elif key == "size":
            if (
                not isinstance(item, list)
                or len(item) != 2
                or any(type(v) is not int or v <= 0 for v in item)
            ):
                raise ValueError("invalid public image size")
        elif key in {"sha256", "source_sha256", "provider_sha256"}:
            digest(item)
        elif key == "file":
            public_path(item)
        elif key == "locale":
            locale(item)
        elif key == "slot":
            if not isinstance(item, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", item):
                raise ValueError("invalid public image slot")
        elif item is not None:
            public_text(item, "public image text", empty=True)
    if grouped and not {"locale", "slot"} <= set(value):
        raise ValueError("missing public image group")
    return copy.deepcopy(value)
