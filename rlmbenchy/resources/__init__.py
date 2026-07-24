"""Access filesystem paths for bundled rlmbenchy resources."""

from __future__ import annotations

import atexit
from contextlib import ExitStack
from importlib.resources import as_file, files
from pathlib import Path

_RESOURCE_STACK = ExitStack()
atexit.register(_RESOURCE_STACK.close)


def resource_path(package: str, *parts: str) -> Path:
    """Return a process-lifetime path for one packaged file or directory."""

    resource = files(package).joinpath(*parts)
    return _RESOURCE_STACK.enter_context(as_file(resource))


__all__ = ["resource_path"]
