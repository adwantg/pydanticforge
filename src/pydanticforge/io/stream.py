# Author: gadwant
from __future__ import annotations

import json
from typing import Any, Iterable, TextIO

try:
    import orjson
except ImportError:  # pragma: no cover - optional dependency at runtime
    orjson = None


def _loads(raw: str) -> Any:
    if orjson is not None:
        return orjson.loads(raw)
    return json.loads(raw)


def iter_json_from_stream(stream: TextIO) -> Iterable[Any]:
    for line in stream:
        stripped = line.strip()
        if not stripped:
            continue

        item = _loads(stripped)
        if isinstance(item, list):
            for value in item:
                yield value
        else:
            yield item
