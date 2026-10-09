"""Local Git identity and complete bound runtime inventories."""

import hashlib
import importlib.util
import marshal
import os
import re
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath

from .contracts import runtime_record
from .records import capture_bytes, inventory, open_directory, safe_path


def validate_derived_cache(root, name, files):
    """Compare cache bytes with trusted-source compilation, without loading them."""
    parts = PurePosixPath(name).parts
    if len(parts) < 2 or parts[-2] != "__pycache__" or "__pycache__" in parts[:-2]:
        raise ValueError("runtime contains source-less bytecode cache")
    match = re.fullmatch(
        r"(.+)\." + re.escape(sys.implementation.cache_tag) + r"(?:\.opt-([12]))?\.pyc",
        parts[-1],
    )
    if match is None:
        raise ValueError("runtime contains unsupported bytecode cache")
    source_name = str(PurePosixPath(*parts[:-2]) / (match[1] + ".py"))
    if source_name not in files:
        raise ValueError("runtime bytecode cache has no bound source")
    source_path = safe_path(root, source_name)
    source = capture_bytes(source_path)
    cache = capture_bytes(safe_path(root, name))
    for entry, data in ((source_name, source), (name, cache)):
        if hashlib.sha256(data).hexdigest() != files[entry]:
            raise ValueError("runtime cache/source changed during validation")
    if (
        len(cache) < 16
        or cache[:4] != importlib.util.MAGIC_NUMBER
        or int.from_bytes(cache[4:8], "little") not in (0, 1, 3)
    ):
        raise ValueError("runtime contains malformed bytecode cache")
    optimize = int(match[2] or 0)
    filename = str(source_path)
    try:
        compiled = compile(
            source, filename, "exec", dont_inherit=True, optimize=optimize
        )
        # CPython's cache writer retains the code in its caller and serializer.
        # Keep the same owned reference so marshal's reference marker is stable.
        owner = [compiled]
        expected = marshal.dumps(owner[0])
    except (SyntaxError, ValueError, TypeError, RecursionError) as error:
        raise ValueError("runtime source cannot derive a safe cache") from error
    if cache[16:] != expected:
        raise ValueError("runtime bytecode cache differs from bound source")


def git(root, *args):
    # Do not inherit credential helpers, fsmonitor hooks or personal Git config.
    env = {
        "PATH": os.defpath + os.pathsep + os.environ.get("PATH", ""),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_OPTIONAL_LOCKS": "0",
    }
    command = [
        "git",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=" + os.devnull,
        *args,
    ]
    # The child enters the descriptor already opened without following parents.
    # No runtime Path is reopened by Git after approval.
    with open_directory(root) as fd:
        result = subprocess.run(
            command,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            pass_fds=(fd,),
            preexec_fn=lambda: os.fchdir(fd),
        )
    if result.returncode:
        raise ValueError("runtime Git identity cannot be read")
    return result.stdout.strip()


def runtime_inventory(root):
    root = Path(root).absolute()
    with open_directory(root) as fd:
        names = os.listdir(fd)
        if any(name.endswith((".pyc", ".pyo")) for name in names):
            raise ValueError("runtime contains source-less root bytecode cache")
        paths = [
            name
            for name in names
            if Path(name).suffix in (".py", ".rb", ".sh")
            and stat.S_ISREG(os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode)
        ]
        paths += [
            name
            for name in (
                "app_store_assets",
                "app_store_assets_local",
                "lib",
                "schemas",
                "catalog",
                "__pycache__",
            )
            if name in names
        ]
    if "assets.py" not in paths:
        raise ValueError("runtime CLI is missing")
    result = inventory(root, paths)
    caches = [
        name
        for name in result
        if Path(name).suffix in (".pyc", ".pyo") or "__pycache__" in Path(name).parts
    ]
    for name in caches:
        validate_derived_cache(root, name, result)
    return {name: sha for name, sha in result.items() if name not in caches}


def runtime_identity(root, pin):
    runtime_record(pin, pin=True)
    root = Path(root).absolute()
    if git(root, "rev-parse", "HEAD") != pin["commit"]:
        raise ValueError("runtime commit differs from approval")
    if git(root, "remote", "get-url", "origin") != pin["url"]:
        raise ValueError("runtime source URL differs from approval")
    if git(root, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("runtime checkout is modified or contains untracked inputs")
    actual = runtime_inventory(root)
    if actual != pin["files"]:
        raise ValueError("runtime inventory/hash differs from approval")
    return {"url": pin["url"], "commit": pin["commit"], "files": actual}


def verify_executing_runtime(runtime):
    if runtime_inventory(Path(__file__).resolve().parents[1]) != runtime["files"]:
        raise ValueError("executing runtime differs from reviewed plan")
