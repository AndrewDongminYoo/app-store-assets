"""Local tools get no inherited authentication or personal home configuration."""

import os


def local_environment(home):
    return {
        "PATH": os.environ.get("PATH", os.defpath),
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "MAGICK_THREAD_LIMIT": "1",
        "OMP_NUM_THREADS": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
