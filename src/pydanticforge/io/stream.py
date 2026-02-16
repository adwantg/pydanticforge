# Author: gadwant
from __future__ import annotations

import importlib
import json
from collections.abc import Iterable
from importlib.util import find_spec
from typing import Any, TextIO

orjson: Any | None = importlib.import_module("orjson") if find_spec("orjson") is not None else None


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
            yield from item
        else:
            yield item
