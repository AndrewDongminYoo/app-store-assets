"""Synthetic offline projects; only local Git identity and image decoding run."""

import importlib
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def module(*args):
    name = args[-1]
    package = (
        "app_store_assets_local"
        if name in {"publisher", "metadata_io", "staging", "write_cli", "outputs"}
        else "app_store_assets"
    )
    return importlib.import_module(package + "." + name)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n")


def git(root, *args):
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(root),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_OPTIONAL_LOCKS": "0",
    }
    return subprocess.check_output(
        [
            "git",
            "-c",
            "core.hooksPath=" + os.devnull,
            "-c",
            "user.name=Dongmin Yu",
            "-c",
            "user.email=ydm2790@gmail.com",
            "-C",
            str(root),
            *args,
        ],
        env=env,
        text=True,
    ).strip()


def container(path, kind):
    files = {
        "apk": ["AndroidManifest.xml", "classes.dex"],
        "aab": ["BundleConfig.pb", "base/manifest/AndroidManifest.xml"],
        "ipa": ["Payload/Fixture.app/Info.plist"],
    }[kind]
    with zipfile.ZipFile(path, "w") as z:
        for name in files:
            z.writestr(name, b"synthetic container, not native inspection")


def fixture(test, store="apple", kind=None):
    tmp = tempfile.TemporaryDirectory(prefix="offline space $ literal '")
    test.addCleanup(tmp.cleanup)
    root = Path(tmp.name).resolve()
    runtime = root / "tools/app-store-assets"
    shutil.copytree(
        ROOT, runtime, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc")
    )
    git(runtime, "init", "-q")
    git(runtime, "add", ".")
    git(runtime, "commit", "-qm", "Pinned offline fixture")
    git(
        runtime,
        "remote",
        "add",
        "origin",
        "https://example.invalid/app-store-assets.git",
    )
    pin = {
        "path": "tools/app-store-assets",
        "url": "https://example.invalid/app-store-assets.git",
        "commit": git(runtime, "rev-parse", "HEAD"),
        "files": module("identity").runtime_inventory(runtime),
    }
    (root / "helpers").mkdir()
    (root / "helpers/source.txt").write_text("bound public source\n")
    (root / "artifacts").mkdir()
    kind = kind or ("ipa" if store == "apple" else "aab")
    artifact = "artifacts/app." + kind
    container(root / artifact, kind)
    target = {
        "store": store,
        "platform": "ios" if store == "apple" else "android",
        "account": "personal",
        "account_id": "fixture-public-id",
        "app_id": "com.example.fixture",
        "flavor": "production",
        "stage": "production",
        "version": {"name": "1.0", "build": "9"},
        "inputs": ["helpers"],
        "artifact": {"path": artifact, "record": "artifact.json", "kind": kind},
        "metadata": "metadata/listing.json",
        "remote": "remote.json",
    }
    if store == "google":
        target.update(track="alpha", release_status="completed")
    identity = module("profiles").target_identity(target)
    listing = {
        "schema_version": 1,
        "type": "metadata",
        "target": identity,
        "fields": {"en-US": {"description": "Approved description"}},
        "images": {},
    }
    write_json(root / "metadata/listing.json", listing)
    notes = root / "metadata/en-US/changelogs/9.txt"
    notes.parent.mkdir(parents=True)
    notes.write_text("Approved notes\n")
    write_json(
        root / "remote.json",
        {
            "schema_version": 1,
            "type": "metadata-snapshot",
            "target": identity,
            "version_id": "exact-version",
            "editable": True,
            "review_active": False,
            "app_info_id": "exact-info",
            "fields": {
                "en-US": {
                    "description": "Approved description",
                    **(
                        {
                            "name": "Valid Name",
                            "privacy_url": "https://example.invalid/privacy",
                        }
                        if store == "apple"
                        else {}
                    ),
                }
            },
            "images": {},
        },
    )
    write_json(
        root / "artifact.json",
        {
            "schema_version": 1,
            "type": "build",
            "app_id": target["app_id"],
            "platform": target["platform"],
            "flavor": target["flavor"],
            "version": target["version"],
            "sha256": module("records").file_digest(root / artifact),
            "kind": kind,
            "evidence": "fixture",
        },
    )
    profile = {
        "schema_version": 1,
        "type": "offline-profile",
        "project": "synthetic",
        "mode": "fixture",
        "runtime": pin,
        "targets": {"production": target},
    }
    write_json(root / "store-upload.json", profile)
    return (root, profile)
