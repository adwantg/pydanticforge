# Author: gadwant
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class AnyType:
    pass


@dataclass(frozen=True)
class NullType:
    pass


@dataclass(frozen=True)
class BoolType:
    pass


@dataclass(frozen=True)
class IntType:
    pass


@dataclass(frozen=True)
class FloatType:
    pass


@dataclass(frozen=True)
class StrType:
    pass


@dataclass(frozen=True)
class DateTimeType:
    pass


@dataclass(frozen=True)
class ArrayType:
    item_type: TypeNode


@dataclass(frozen=True)
class FieldInfo:
    type_node: TypeNode
    required_count: int
    sample_count: int
    examples: tuple[str, ...] = ()

    @property
    def required(self) -> bool:
        return self.required_count == self.sample_count


@dataclass(frozen=True)
class ObjectType:
    fields: tuple[tuple[str, FieldInfo], ...]
    sample_count: int

    @classmethod
    def from_mapping(cls, mapping: dict[str, FieldInfo], sample_count: int) -> ObjectType:
        return cls(tuple(sorted(mapping.items(), key=lambda item: item[0])), sample_count)

    def as_mapping(self) -> dict[str, FieldInfo]:
        return dict(self.fields)


@dataclass(frozen=True)
class UnionType:
    options: tuple[TypeNode, ...]


TypeNode = (
    AnyType
    | NullType
    | BoolType
    | IntType
    | FloatType
    | StrType
    | DateTimeType
    | ArrayType
    | ObjectType
    | UnionType
)


ANY = AnyType()
NULL = NullType()
BOOL = BoolType()
INT = IntType()
FLOAT = FloatType()
STR = StrType()
DATETIME = DateTimeType()


def type_sort_key(node: TypeNode) -> str:
    return type_name(node)


def type_name(node: TypeNode) -> str:
    if isinstance(node, AnyType):
        return "Any"
    if isinstance(node, NullType):
        return "None"
    if isinstance(node, BoolType):
        return "bool"
    if isinstance(node, IntType):
        return "int"
    if isinstance(node, FloatType):
        return "float"
    if isinstance(node, StrType):
        return "str"
    if isinstance(node, DateTimeType):
        return "datetime"
    if isinstance(node, ArrayType):
        return f"list[{type_name(node.item_type)}]"
    if isinstance(node, ObjectType):
        field_names = ",".join(name for name, _ in node.fields)
        return f"object<{field_names}>"
    if isinstance(node, UnionType):
        parts = sorted((type_name(option) for option in node.options))
        return " | ".join(parts)
    raise TypeError(f"Unsupported TypeNode: {type(node)}")


def flatten_union_options(nodes: Iterable[TypeNode]) -> list[TypeNode]:
    flat: list[TypeNode] = []
    for node in nodes:
        if isinstance(node, UnionType):
            flat.extend(flatten_union_options(node.options))
        else:
            flat.append(node)
    return flat
