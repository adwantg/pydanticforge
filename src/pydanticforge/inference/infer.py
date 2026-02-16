# Author: gadwant
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from pydanticforge.inference.lattice import join_types
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
)


def _is_datetime_string(value: str) -> bool:
    if len(value) < 10:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def infer_type(value: Any) -> TypeNode:
    if value is None:
        return NULL

    if isinstance(value, bool):
        return BOOL

    if isinstance(value, int):
        return INT

    if isinstance(value, float):
        return FLOAT

    if isinstance(value, str):
        if _is_datetime_string(value):
            return DATETIME
        return STR

    if isinstance(value, list):
        if not value:
            return ArrayType(ANY)

        item_type = infer_type(value[0])
        for item in value[1:]:
            item_type = join_types(item_type, infer_type(item))
        return ArrayType(item_type)

    if isinstance(value, dict):
        fields: dict[str, FieldInfo] = {}
        for raw_name, raw_val in value.items():
            name = str(raw_name)
            sample = repr(raw_val)
            if len(sample) > 80:
                sample = sample[:77] + "..."
            fields[name] = FieldInfo(
                type_node=infer_type(raw_val),
                required_count=1,
                sample_count=1,
                examples=(sample,),
            )
        return ObjectType.from_mapping(fields, sample_count=1)

    return ANY


class TypeInferer:
    def __init__(self, *, strict_numbers: bool = False) -> None:
        self.strict_numbers = strict_numbers
        self._root: TypeNode | None = None

    @property
    def root(self) -> TypeNode | None:
        return self._root

    def observe(self, value: Any) -> TypeNode:
        observed = infer_type(value)
        if self._root is None:
            self._root = observed
        else:
            self._root = join_types(self._root, observed, strict_numbers=self.strict_numbers)
        return self._root

    def observe_many(self, values: Iterable[Any]) -> TypeNode | None:
        for value in values:
            self.observe(value)
        return self._root
