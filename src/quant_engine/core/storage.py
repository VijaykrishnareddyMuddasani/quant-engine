"""Crash-safe JSON files.

A process can die between any two instructions, including halfway through writing its state file.
``atomic_write_json`` writes to a temporary file in the same folder, flushes it to disk and then
swaps it into place with ``os.replace``, which is atomic: a reader sees the old file or the new
one, never half of either.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_json(path: str | Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def read_json(path: str | Path, default: Any = None) -> Any:
    """The file's contents, or ``default`` if it does not exist. A corrupt file is an error."""
    path = Path(path)
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)
