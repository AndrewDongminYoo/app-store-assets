"""Local Git identity and complete bound runtime inventories."""

import os
import stat
import subprocess
from pathlib import Path

from .contracts import runtime_record
from .records import inventory, open_directory


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
        if "__pycache__" in names or any(name.endswith(".pyc") for name in names):
            raise ValueError("runtime contains unbound root bytecode cache")
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
            )
            if name in names
        ]
    if "assets.py" not in paths:
        raise ValueError("runtime CLI is missing")
    result = inventory(root, paths)
    if any(
        Path(name).suffix == ".pyc" or "__pycache__" in Path(name).parts
        for name in result
    ):
        raise ValueError("runtime contains unbound bytecode cache")
    return result


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
