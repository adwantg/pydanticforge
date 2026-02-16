# Author: gadwant
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

try:
    import orjson
except ImportError:  # pragma: no cover - optional dependency at runtime
    orjson = None


def _loads(raw: bytes | str) -> Any:
    if orjson is not None:
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        return orjson.loads(raw)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


def read_json_file(path: Path) -> Any:
    return _loads(path.read_bytes())


def iter_json_files(directory: Path, *, recursive: bool = True) -> Iterable[Path]:
    pattern = "**/*.json" if recursive else "*.json"
    yield from sorted(p for p in directory.glob(pattern) if p.is_file())
