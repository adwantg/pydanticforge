# Author: gadwant
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
    type_sort_key,
)

_JSON_SCHEMA_URI = "https://json-schema.org/draft/2020-12/schema"


def _to_json_schema(node: TypeNode) -> dict[str, Any]:
    if node == ANY:
        return {}
    if node == NULL:
        return {"type": "null"}
    if node == BOOL:
        return {"type": "boolean"}
    if node == INT:
        return {"type": "integer"}
    if node == FLOAT:
        return {"type": "number"}
    if node == STR:
        return {"type": "string"}
    if node == DATETIME:
        return {"type": "string", "format": "date-time"}
    if isinstance(node, ArrayType):
        return {"type": "array", "items": _to_json_schema(node.item_type)}
    if isinstance(node, ObjectType):
        properties = {
            name: _to_json_schema(field.type_node)
            for name, field in node.fields
        }
        required = [name for name, field in node.fields if field.required]

        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
            "additionalProperties": True,
        }
        if required:
            schema["required"] = required
        return schema
    if isinstance(node, UnionType):
        return {"anyOf": [_to_json_schema(option) for option in node.options]}

    raise TypeError(f"Unsupported TypeNode: {type(node)}")


def to_json_schema(root: TypeNode, *, title: str = "PydanticforgeSchema") -> dict[str, Any]:
    schema = _to_json_schema(root)
    with_meta = {"$schema": _JSON_SCHEMA_URI, "title": title}
    with_meta.update(schema)
    return with_meta


def _dedupe_union(options: list[TypeNode]) -> TypeNode:
    if not options:
        return ANY

    deduped = set(options)
    if len(deduped) == 1:
        return next(iter(deduped))

    return UnionType(tuple(sorted(deduped, key=type_sort_key)))


def _from_json_schema(schema: dict[str, Any]) -> TypeNode:
    if not isinstance(schema, dict):
        return ANY

    if "anyOf" in schema:
        options = [
            _from_json_schema(option)
            for option in schema.get("anyOf", [])
            if isinstance(option, dict)
        ]
        return _dedupe_union(options)

    if "oneOf" in schema:
        options = [
            _from_json_schema(option)
            for option in schema.get("oneOf", [])
            if isinstance(option, dict)
        ]
        return _dedupe_union(options)

    schema_type = schema.get("type")

    if isinstance(schema_type, list):
        options = [_from_json_schema({**schema, "type": value}) for value in schema_type]
        return _dedupe_union(options)

    if schema_type == "null":
        return NULL
    if schema_type == "boolean":
        return BOOL
    if schema_type == "integer":
        return INT
    if schema_type == "number":
        return FLOAT
    if schema_type == "string":
        if schema.get("format") == "date-time":
            return DATETIME
        return STR
    if schema_type == "array":
        item_schema = schema.get("items", {})
        if not isinstance(item_schema, dict):
            item_schema = {}
        return ArrayType(_from_json_schema(item_schema))

    if schema_type == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            properties = {}

        required_names = schema.get("required", [])
        if isinstance(required_names, list):
            required_set = {str(name) for name in required_names}
        else:
            required_set = set()

        fields: dict[str, FieldInfo] = {}
        for name, field_schema in sorted(properties.items(), key=lambda entry: str(entry[0])):
            key = str(name)
            parsed_schema = field_schema if isinstance(field_schema, dict) else {}
            required = 1 if key in required_set else 0
            fields[key] = FieldInfo(
                type_node=_from_json_schema(parsed_schema),
                required_count=required,
                sample_count=1,
                examples=(),
            )

        return ObjectType.from_mapping(fields, sample_count=1)

    return ANY


def from_json_schema(schema: dict[str, Any]) -> TypeNode:
    return _from_json_schema(schema)


def save_json_schema(path: Path, root: TypeNode, *, title: str = "PydanticforgeSchema") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    schema = to_json_schema(root, title=title)
    path.write_text(json.dumps(schema, indent=2, sort_keys=True), encoding="utf-8")


def load_json_schema(path: Path) -> TypeNode:
    schema = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(schema, dict):
        raise ValueError("JSON Schema root must be an object")
    return from_json_schema(schema)
