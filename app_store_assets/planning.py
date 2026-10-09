"""Offline intent records: no provider construction and no execution authority."""

from pathlib import Path

from .artifacts import artifact_record
from .catalog import (
    CATALOG_FILE,
    rules,
    validate_apple_localizations,
    validate_images,
)
from .identity import runtime_identity, verify_executing_runtime
from .metadata import (
    has_selected_binary,
    normalize_fields,
    remote_observation,
    resolve_changelogs,
    selected_notes,
    validate_public_metadata,
)
from .profiles import exact_keys, load_profile, target_identity
from .records import (
    bind_capture,
    file_digest,
    inventory,
    read_json,
    read_text,
    record_digest,
    safe_path,
)
from .snapshots import validate_snapshot

OPERATIONS = {"binary", "metadata", "images"}


def local_context(root, profile_path, target_name, captures=None):
    profile, target = load_profile(root, profile_path, target_name, captures)
    runtime = runtime_identity(
        safe_path(root, profile["runtime"]["path"]), profile["runtime"]
    )
    verify_executing_runtime(runtime)
    return (profile, target, runtime)


def make_plan(root, profile_path, target_name, operation):
    root = Path(root).resolve()
    if operation not in OPERATIONS:
        raise ValueError("unsupported offline operation")
    captures = {}
    profile, target, runtime = local_context(root, profile_path, target_name, captures)
    identity = target_identity(target)
    if operation == "binary" and target["stage"] == "development":
        raise ValueError("development binary planning is blocked")
    paths = [profile_path, *target["inputs"]]
    if "version_source" in target:
        paths.append(target["version_source"]["file"])
    build = None
    if operation == "binary":
        build = artifact_record(root, profile, target, captures)
        paths.extend(target["artifact"][k] for k in ("path", "record"))
    listing = None
    assets = None
    notes = {}
    if operation in ("metadata", "images"):
        if not target.get("metadata"):
            raise ValueError("operation requires a declared listing")
        paths.append(target["metadata"])
        listing = validate_public_metadata(
            read_json(safe_path(root, target["metadata"]), captures=captures), identity
        )
        if listing["type"] != "metadata":
            raise ValueError("metadata schema/target/account/track/version differs")
        listing = resolve_changelogs(root, listing, identity, captures)
        notes = selected_notes(listing)
        if operation == "images":
            policy = target.get("replacement")
            exact_keys(
                policy,
                {"locales", "slots", "allow_delete"},
                ("locales", "slots", "allow_delete"),
            )
            if type(policy["allow_delete"]) is not bool or any(
                not isinstance(policy[k], list)
                or not policy[k]
                or any(not isinstance(v, str) for v in policy[k])
                or (len(set(policy[k])) != len(policy[k]))
                for k in ("locales", "slots")
            ):
                raise ValueError(
                    "explicit replacement locale/slot/deletion policy required"
                )
            entries = [
                dict(item, locale=locale, slot=slot)
                for locale, groups in listing.get("images", {}).items()
                for slot, images in groups.items()
                for item in images
            ]
            if not entries:
                raise ValueError("empty image listing")
            validated = validate_images(root, entries, target["store"])
            for item in validated:
                bind_capture(captures, safe_path(root, item["file"]), item["sha256"])
            if set(policy["locales"]) != {i["locale"] for i in validated} or set(
                policy["slots"]
            ) != {i["slot"] for i in validated}:
                raise ValueError("replacement policy differs from listing groups")
            listing["images"] = {}
            for item in validated:
                locale, slot = (item["locale"], item["slot"])
                clean = {k: v for k, v in item.items() if k not in ("locale", "slot")}
                listing["images"].setdefault(locale, {}).setdefault(slot, []).append(
                    clean
                )
            paths.extend(i["file"] for i in validated)
            descriptor = target.get("assets")
            if profile["mode"] == "live" and (not descriptor):
                raise ValueError("live image intent requires immutable asset snapshot")
            if descriptor:
                exact_keys(descriptor, {"manifest"}, ("manifest",))
                manifest_path = safe_path(root, descriptor["manifest"])
                if manifest_path.name != "manifest.json":
                    raise ValueError("asset snapshot requires manifest.json")
                assets = validate_snapshot(manifest_path.parent, captures)["record"]
                if (
                    assets.get("type") != "asset-manifest"
                    or assets.get("target") != identity
                ):
                    raise ValueError("asset manifest target/version differs")
                if assets.get("provenance", {}).get("status") not in (
                    "widget-rendered",
                    "unverified-import",
                ):
                    raise ValueError("unsupported asset provenance declaration")
                prefix = manifest_path.parent.relative_to(root)
                intended = [
                    (str(prefix / i["file"]), i["locale"], i["slot"], i["sha256"])
                    for i in assets["assets"]
                ]
                actual = [
                    (i["file"], i["locale"], i["slot"], i["sha256"]) for i in validated
                ]
                if intended != actual:
                    raise ValueError(
                        "asset manifest ordered inventory differs from listing"
                    )
                paths.append(manifest_path.parent.relative_to(root).as_posix())
    remote = None
    if target.get("remote"):
        paths.append(target["remote"])
        remote = read_json(safe_path(root, target["remote"]), captures=captures)
        content_root = root
        if not isinstance(remote, dict):
            raise ValueError("invalid supplied remote record")
        if remote.get("type") == "snapshot":
            path = safe_path(root, target["remote"])
            if path.name != "manifest.json":
                raise ValueError("remote snapshot requires manifest.json")
            remote = validate_snapshot(path.parent, captures)["record"]
            content_root = path.parent
            paths.append(path.parent.relative_to(root).as_posix())
        if remote.get("target") != identity:
            raise ValueError("supplied snapshot target differs")
        if remote.get("type") != "metadata-snapshot":
            raise ValueError("supplied remote requires metadata-snapshot type")
        remote = remote_observation(
            resolve_changelogs(
                root, remote, identity, captures, content_root=content_root
            )
        )
        if operation == "binary" and has_selected_binary(target, remote):
            raise ValueError("selected build already exists in supplied snapshot")
    if target["store"] == "apple" and operation in ("metadata", "images"):
        if remote is None:
            raise ValueError("Apple requires a supplied selected-version snapshot")
        validate_apple_localizations(listing, remote, operation)
    if operation == "binary":
        if target["store"] == "apple" and target.get("changelogs"):
            raise ValueError("Apple binary notes require a separate adapter contract")
        for locale, path in target.get("changelogs", {}).items():
            normalize_fields({locale: {}})
            notes[locale] = read_text(safe_path(root, path), captures)
            normalize_fields({locale: {"release_notes": notes[locale]}})
            if len(notes[locale]) > rules()["stores"]["google"]["release_notes_limit"]:
                raise ValueError("release-notes limit exceeded")
            paths.append(path)
    paths.extend(path.relative_to(root).as_posix() for path in captures)
    inputs = inventory(root, paths)
    for path, digest in captures.items():
        if inputs.get(path.relative_to(root).as_posix()) != digest:
            raise ValueError("parsed/validated input changed before plan inventory")
    verify_executing_runtime(runtime)
    payload = {
        "schema_version": 1,
        "type": "offline-release-plan",
        "executable": False,
        "effects": [],
        "planned_changes": ["upload-" + operation],
        "remote_verified": False,
        "remote_evidence": "supplied-snapshot-freshness-unverified"
        if remote is not None
        else "not-supplied",
        "profile": profile_path,
        "target_name": target_name,
        "mode": profile["mode"],
        "target": identity,
        "operation": operation,
        "runtime": runtime,
        "runtime_path": profile["runtime"]["path"],
        "input_paths": sorted(set(paths)),
        "inputs": inputs,
        "catalog_sha256": file_digest(CATALOG_FILE),
        "artifact": target.get("artifact") if build else None,
        "build": build,
        "artifact_verification": "container-and-supplied-record-only"
        if build
        else "not-applicable",
        "listing": listing,
        "assets": assets,
        "remote": remote,
        "release_notes": notes,
        "replacement": target.get("replacement") if operation == "images" else None,
        "release_status": target.get("release_status"),
    }
    if build and profile["mode"] == "live":
        payload["native_evidence"] = "supplied-inspection-claims-unverified"
    if target["store"] == "google":
        payload["planned_changes"].append(
            "shared-listing-across-tracks"
            if operation != "binary"
            else "append-draft-track-release"
            if target["release_status"] == "draft"
            else "replace-track-releases"
        )
    if notes and operation != "images":
        payload["planned_changes"].append("release-notes")
    return {"payload": payload, "digest": record_digest(payload)}


def verify_plan(root, plan):
    if (
        not isinstance(plan, dict)
        or set(plan) != {"payload", "digest"}
        or record_digest(plan["payload"]) != plan["digest"]
    ):
        raise ValueError("plan digest differs")
    payload = plan["payload"]
    if not isinstance(payload, dict):
        raise ValueError("invalid offline plan payload")
    if (
        payload.get("type") != "offline-release-plan"
        or payload.get("executable") is not False
        or payload.get("effects") != []
    ):
        raise ValueError("unsupported offline plan")
    if (
        make_plan(
            root, payload["profile"], payload["target_name"], payload["operation"]
        )
        != plan
    ):
        raise ValueError("approved inputs/target changed; plan differs")
