# Author: gadwant
from __future__ import annotations

import importlib
import json
from collections.abc import Iterable
from importlib.util import find_spec
from pathlib import Path
from typing import Any

orjson: Any | None = importlib.import_module("orjson") if find_spec("orjson") is not None else None

_JSON_FILE_SUFFIXES = (".json", ".ndjson", ".jsonl")


def _loads(raw: bytes | str) -> Any:
    if orjson is not None:
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        return orjson.loads(raw)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


def _parse_ndjson(raw: bytes) -> list[Any]:
    text = raw.decode("utf-8")
    samples: list[Any] = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        samples.append(_loads(stripped))

    return samples


def read_json_file(path: Path) -> Any:
    raw = path.read_bytes()
    try:
        return _loads(raw)
    except ValueError as primary_error:
        try:
            ndjson_samples = _parse_ndjson(raw)
        except (UnicodeDecodeError, ValueError):
            raise primary_error from None

        if not ndjson_samples:
            raise primary_error from None

        return ndjson_samples


def iter_json_files(directory: Path, *, recursive: bool = True) -> Iterable[Path]:
    files: set[Path] = set()
    for suffix in _JSON_FILE_SUFFIXES:
        pattern = f"**/*{suffix}" if recursive else f"*{suffix}"
        files.update(path for path in directory.glob(pattern) if path.is_file())

    yield from sorted(files)
