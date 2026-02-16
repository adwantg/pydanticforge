# Author: gadwant
from __future__ import annotations

from dataclasses import dataclass

from pydanticforge.inference.types import (
    ANY,
    FLOAT,
    INT,
    ArrayType,
    AnyType,
    BoolType,
    DateTimeType,
    FloatType,
    IntType,
    NullType,
    ObjectType,
    StrType,
    TypeNode,
    UnionType,
    type_name,
)

BREAKING_DRIFT_KINDS = frozenset({"type_mismatch", "missing_required_field"})


@dataclass(frozen=True)
class DriftEvent:
    path: str
    expected: str
    observed: str
    kind: str


def drift_severity(event: DriftEvent) -> str:
    return "breaking" if event.kind in BREAKING_DRIFT_KINDS else "warning"


def _is_same_scalar_family(expected: TypeNode, observed: TypeNode) -> bool:
    scalar_pairs = (
        (BoolType, BoolType),
        (IntType, IntType),
        (FloatType, FloatType),
        (StrType, StrType),
        (DateTimeType, DateTimeType),
        (NullType, NullType),
    )
    return any(isinstance(expected, e) and isinstance(observed, o) for e, o in scalar_pairs)


def _is_compatible(expected: TypeNode, observed: TypeNode) -> bool:
    if expected == ANY:
        return True

    if expected == observed:
        return True

    if expected == FLOAT and observed == INT:
        return True

    if isinstance(expected, UnionType):
        return any(_is_compatible(option, observed) for option in expected.options)

    if isinstance(expected, ArrayType) and isinstance(observed, ArrayType):
        return _is_compatible(expected.item_type, observed.item_type)

    if isinstance(expected, ObjectType) and isinstance(observed, ObjectType):
        expected_fields = expected.as_mapping()
        observed_fields = observed.as_mapping()

        for name, field in expected_fields.items():
            seen = observed_fields.get(name)
            if seen is None and field.required:
                return False
            if seen is not None and not _is_compatible(field.type_node, seen.type_node):
                return False
        return True

    if _is_same_scalar_family(expected, observed):
        return True

    return False


def detect_drift(expected: TypeNode, observed: TypeNode, *, path: str = "$") -> list[DriftEvent]:
    if isinstance(expected, UnionType):
        if any(_is_compatible(option, observed) for option in expected.options):
            return []

    if not _is_compatible(expected, observed):
        if isinstance(expected, ObjectType) and isinstance(observed, ObjectType):
            return _detect_object_drift(expected, observed, path=path)

        if isinstance(expected, ArrayType) and isinstance(observed, ArrayType):
            return detect_drift(expected.item_type, observed.item_type, path=f"{path}[]")

        return [
            DriftEvent(
                path=path,
                expected=type_name(expected),
                observed=type_name(observed),
                kind="type_mismatch",
            )
        ]

    if isinstance(expected, ObjectType) and isinstance(observed, ObjectType):
        return _detect_object_drift(expected, observed, path=path)

    if isinstance(expected, ArrayType) and isinstance(observed, ArrayType):
        return detect_drift(expected.item_type, observed.item_type, path=f"{path}[]")

    return []


def _detect_object_drift(expected: ObjectType, observed: ObjectType, *, path: str) -> list[DriftEvent]:
    drifts: list[DriftEvent] = []
    expected_fields = expected.as_mapping()
    observed_fields = observed.as_mapping()

    for name, field in expected_fields.items():
        observed_field = observed_fields.get(name)
        child_path = f"{path}.{name}"

        if observed_field is None:
            if field.required:
                drifts.append(
                    DriftEvent(
                        path=child_path,
                        expected=type_name(field.type_node),
                        observed="<missing>",
                        kind="missing_required_field",
                    )
                )
            continue

        drifts.extend(detect_drift(field.type_node, observed_field.type_node, path=child_path))

    for name, observed_field in observed_fields.items():
        if name in expected_fields:
            continue
        drifts.append(
            DriftEvent(
                path=f"{path}.{name}",
                expected="<absent>",
                observed=type_name(observed_field.type_node),
                kind="new_field",
            )
        )

    return drifts
