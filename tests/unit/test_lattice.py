# Author: gadwant
from __future__ import annotations

from pydanticforge.inference.infer import TypeInferer, infer_type
from pydanticforge.inference.lattice import join_types
from pydanticforge.inference.types import ObjectType


def test_join_commutative_for_objects() -> None:
    left = infer_type({"id": 1, "name": "a"})
    right = infer_type({"id": 2.5, "active": True})

    assert join_types(left, right) == join_types(right, left)


def test_join_associative_for_mixed_samples() -> None:
    a = infer_type({"id": 1})
    b = infer_type({"id": 2, "name": "x"})
    c = infer_type({"id": 3.1, "name": "y", "active": False})

    assert join_types(join_types(a, b), c) == join_types(a, join_types(b, c))


def test_optional_field_tracking() -> None:
    inferer = TypeInferer()
    inferer.observe({"id": 1, "name": "a"})
    inferer.observe({"id": 2})

    root = inferer.root
    assert isinstance(root, ObjectType)

    fields = root.as_mapping()
    assert fields["id"].required
    assert not fields["name"].required
