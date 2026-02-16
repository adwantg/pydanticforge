# Author: gadwant
from __future__ import annotations

from pydanticforge.inference.types import (
    ANY,
    FLOAT,
    INT,
    AnyType,
    ArrayType,
    FieldInfo,
    FloatType,
    IntType,
    ObjectType,
    TypeNode,
    UnionType,
    flatten_union_options,
    type_sort_key,
)


def _merge_examples(
    left: tuple[str, ...],
    right: tuple[str, ...],
    limit: int = 3,
) -> tuple[str, ...]:
    merged = sorted(set(left) | set(right))
    return tuple(merged[:limit])


def simplify_union(nodes: list[TypeNode], *, strict_numbers: bool = False) -> TypeNode:
    options = flatten_union_options(nodes)

    if any(isinstance(option, AnyType) for option in options):
        return ANY

    deduped = set(options)

    if not strict_numbers and FLOAT in deduped and INT in deduped:
        deduped.remove(INT)

    if len(deduped) == 1:
        return next(iter(deduped))

    return UnionType(tuple(sorted(deduped, key=type_sort_key)))


def _join_object_fields(
    left: ObjectType,
    right: ObjectType,
    *,
    strict_numbers: bool,
) -> ObjectType:
    left_map = left.as_mapping()
    right_map = right.as_mapping()

    names = sorted(set(left_map) | set(right_map))
    total_samples = left.sample_count + right.sample_count

    merged: dict[str, FieldInfo] = {}

    for name in names:
        left_field = left_map.get(name)
        right_field = right_map.get(name)

        if left_field and right_field:
            field_type = join_types(
                left_field.type_node,
                right_field.type_node,
                strict_numbers=strict_numbers,
            )
            required_count = left_field.required_count + right_field.required_count
            examples = _merge_examples(left_field.examples, right_field.examples)
        elif left_field:
            field_type = left_field.type_node
            required_count = left_field.required_count
            examples = left_field.examples
        else:
            assert right_field is not None
            field_type = right_field.type_node
            required_count = right_field.required_count
            examples = right_field.examples

        merged[name] = FieldInfo(
            type_node=field_type,
            required_count=required_count,
            sample_count=total_samples,
            examples=examples,
        )

    return ObjectType.from_mapping(merged, sample_count=total_samples)


def join_types(left: TypeNode, right: TypeNode, *, strict_numbers: bool = False) -> TypeNode:
    if left == right:
        return left

    if isinstance(left, AnyType) or isinstance(right, AnyType):
        return ANY

    if isinstance(left, IntType) and isinstance(right, FloatType):
        return simplify_union([left, right], strict_numbers=strict_numbers)

    if isinstance(left, FloatType) and isinstance(right, IntType):
        return simplify_union([left, right], strict_numbers=strict_numbers)

    if isinstance(left, ArrayType) and isinstance(right, ArrayType):
        return ArrayType(join_types(left.item_type, right.item_type, strict_numbers=strict_numbers))

    if isinstance(left, ObjectType) and isinstance(right, ObjectType):
        return _join_object_fields(left, right, strict_numbers=strict_numbers)

    if isinstance(left, UnionType) or isinstance(right, UnionType):
        return simplify_union([left, right], strict_numbers=strict_numbers)

    return simplify_union([left, right], strict_numbers=strict_numbers)
