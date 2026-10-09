"""Complete public build/asset records and supported snapshot record dispatch."""

import copy

from .contracts import (
    digest,
    exact_keys,
    hash_inventory,
    image_entry,
    public_path,
    public_text,
    target_identity,
    version,
)


def validate_build(record, target=None):
    required = {
        "schema_version",
        "type",
        "app_id",
        "platform",
        "flavor",
        "version",
        "sha256",
        "kind",
        "evidence",
    }
    exact_keys(
        record,
        required
        | {"native_guards", "source_inputs", "source_commit", "inspector", "adapter"},
        required,
    )
    if (
        type(record["schema_version"]) is not int
        or record["schema_version"] != 1
        or record["type"] != "build"
    ):
        raise ValueError("unsupported build schema/type")
    for key in ("app_id", "platform", "flavor"):
        public_text(record[key], "build " + key)
    version(record["version"])
    digest(record["sha256"])
    public_text(record["kind"], "artifact kind")
    public_text(record["evidence"], "build evidence")
    if (
        record["kind"] not in {"apk", "aab", "ipa"}
        or record["platform"]
        != {"apk": "android", "aab": "android", "ipa": "ios"}[record["kind"]]
    ):
        raise ValueError("artifact kind/platform differs")
    if record["evidence"] not in {"fixture", "inspected"}:
        raise ValueError("unsupported build evidence declaration")
    if "source_commit" in record:
        digest(record["source_commit"], 40)
    if "source_inputs" in record:
        hash_inventory(record["source_inputs"])
    if "native_guards" in record:
        guards = record["native_guards"]
        exact_keys(
            guards, {"app_id", "platform", "flavor", "version", "source", "signing"}
        )
        if not guards or any(type(v) is not bool for v in guards.values()):
            raise ValueError("invalid native guard declarations")
    if "inspector" in record:
        inspector = record["inspector"]
        if isinstance(inspector, str):
            public_text(inspector, "public inspector declaration")
        else:
            exact_keys(inspector, {"name", "version", "sha256"}, {"name"})
            public_text(inspector["name"], "public inspector name")
            if "version" in inspector:
                public_text(inspector["version"], "public inspector version")
            if "sha256" in inspector:
                digest(inspector["sha256"])
    if "adapter" in record:
        exact_keys(record["adapter"], {"inputs"}, {"inputs"})
        values = record["adapter"]["inputs"]
        if (
            not isinstance(values, list)
            or not values
            or any(not isinstance(v, str) for v in values)
            or len(set(values)) != len(values)
        ):
            raise ValueError("invalid source adapter inventory")
        for item in values:
            public_path(item)
    if target is not None:
        target_identity(target)
        if any(
            record[key] != target[key]
            for key in ("app_id", "platform", "flavor", "version")
        ):
            raise ValueError("artifact build identity differs")
    return copy.deepcopy(record)


def validate_assets(record, target=None):
    required = {"schema_version", "type", "target", "assets", "provenance"}
    exact_keys(
        record,
        required | {"inputs", "source_export", "catalog_sha256", "runtime"},
        required,
    )
    if (
        type(record["schema_version"]) is not int
        or record["schema_version"] != 1
        or record["type"] != "asset-manifest"
    ):
        raise ValueError("unsupported asset manifest schema/type")
    identity = target_identity(record["target"])
    if target is not None and identity != target_identity(target):
        raise ValueError("asset manifest target differs")
    exact_keys(record["provenance"], {"status"}, {"status"})
    public_text(record["provenance"]["status"], "asset provenance")
    if record["provenance"]["status"] not in {"widget-rendered", "unverified-import"}:
        raise ValueError("unsupported asset provenance declaration")
    if not isinstance(record["assets"], list) or not record["assets"]:
        raise ValueError("empty asset manifest inventory")
    names = set()
    for item in record["assets"]:
        image_entry(item, grouped=True, required_file=True)
        if "sha256" not in item or item["file"] in names:
            raise ValueError("duplicate or unbound asset entry")
        names.add(item["file"])
    if "inputs" in record:
        hash_inventory(record["inputs"])
    for key in ("source_export", "catalog_sha256"):
        if key in record:
            digest(record[key])
    if "runtime" in record:
        hash_inventory(record["runtime"])
    return copy.deepcopy(record)


def validate_record(record):
    from .metadata import validate_public_metadata

    if not isinstance(record, dict):
        raise ValueError("invalid snapshot public record")
    kind = record.get("type")
    public_text(kind, "public record type")
    if kind in {"metadata", "metadata-snapshot", "metadata-import"}:
        return validate_public_metadata(record, record.get("target"))
    if kind == "build":
        return validate_build(record)
    if kind == "asset-manifest":
        return validate_assets(record)
    raise ValueError("unsupported opaque snapshot record type")
