# Author: gadwant
from __future__ import annotations

import re

_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def to_class_name(raw: str) -> str:
    parts = _WORD_RE.findall(raw)
    if not parts:
        return "Model"
    normalized = [part[:1].upper() + part[1:] for part in parts]
    name = "".join(normalized)
    if name and name[0].isdigit():
        name = f"Model{name}"
    return name


def ensure_unique_name(candidate: str, used: set[str]) -> str:
    if candidate not in used:
        used.add(candidate)
        return candidate

    i = 2
    while True:
        name = f"{candidate}{i}"
        if name not in used:
            used.add(name)
            return name
        i += 1
