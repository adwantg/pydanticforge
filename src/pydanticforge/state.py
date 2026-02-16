# Author: gadwant
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydanticforge.inference.types import (
    ANY,
    BOOL,
    DATETIME,
    FLOAT,
    INT,
    NULL,
    STR,
    ArrayType,
    FieldInfo,
    ObjectType,
    TypeNode,
    UnionType,
)


def _type_to_data(node: TypeNode) -> dict:
    if node == ANY:
        return {"kind": "any"}
    if node == NULL:
        return {"kind": "null"}
    if node == BOOL:
        return {"kind": "bool"}
    if node == INT:
        return {"kind": "int"}
    if node == FLOAT:
        return {"kind": "float"}
    if node == STR:
        return {"kind": "str"}
    if node == DATETIME:
        return {"kind": "datetime"}
    if isinstance(node, ArrayType):
        return {"kind": "array", "item_type": _type_to_data(node.item_type)}
    if isinstance(node, ObjectType):
        return {
            "kind": "object",
            "sample_count": node.sample_count,
            "fields": [
                {
                    "name": name,
                    "type": _type_to_data(field.type_node),
                    "required_count": field.required_count,
                    "sample_count": field.sample_count,
                    "examples": list(field.examples),
                }
                for name, field in node.fields
            ],
        }
    if isinstance(node, UnionType):
        return {
            "kind": "union",
            "options": [_type_to_data(option) for option in node.options],
        }
    raise TypeError(f"Unsupported type node: {type(node)}")


def _type_from_data(data: dict) -> TypeNode:
    kind = data["kind"]

    if kind == "any":
        return ANY
    if kind == "null":
        return NULL
    if kind == "bool":
        return BOOL
    if kind == "int":
        return INT
    if kind == "float":
        return FLOAT
    if kind == "str":
        return STR
    if kind == "datetime":
        return DATETIME
    if kind == "array":
        return ArrayType(_type_from_data(data["item_type"]))
    if kind == "object":
        fields: dict[str, FieldInfo] = {}
        for entry in data["fields"]:
            fields[entry["name"]] = FieldInfo(
                type_node=_type_from_data(entry["type"]),
                required_count=int(entry["required_count"]),
                sample_count=int(entry["sample_count"]),
                examples=tuple(entry.get("examples", [])),
            )
        return ObjectType.from_mapping(fields, sample_count=int(data["sample_count"]))
    if kind == "union":
        return UnionType(tuple(_type_from_data(option) for option in data["options"]))

    raise ValueError(f"Unknown type kind: {kind}")


def schema_state_payload(root: TypeNode) -> dict:
    return {"schema_version": 1, "root": _type_to_data(root)}


def root_from_schema_state_payload(payload: dict) -> TypeNode:
    version = int(payload.get("schema_version", 1))
    if version != 1:
        raise ValueError(f"Unsupported schema state version: {version}")
    return _type_from_data(payload["root"])


def schema_state_hash(root: TypeNode) -> str:
    payload = schema_state_payload(root)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def save_schema_state(path: Path, root: TypeNode) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = schema_state_payload(root)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_schema_state(path: Path) -> TypeNode:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return root_from_schema_state_payload(payload)
