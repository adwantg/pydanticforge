# Author: gadwant
from __future__ import annotations

from pathlib import Path

from pydanticforge.inference.infer import TypeInferer
from pydanticforge.inference.types import ObjectType
from pydanticforge.json_schema import load_json_schema, save_json_schema


def test_json_schema_export_and_import_preserves_field_shape(tmp_path: Path) -> None:
    inferer = TypeInferer()
    inferer.observe({"id": 1, "name": "alice"})
    inferer.observe({"id": 2, "name": "bob", "meta": {"score": 10}})

    root = inferer.root
    assert isinstance(root, ObjectType)

    schema_file = tmp_path / "schema.json"
    save_json_schema(schema_file, root, title="Example")

    loaded = load_json_schema(schema_file)
    assert isinstance(loaded, ObjectType)

    original_fields = root.as_mapping()
    loaded_fields = loaded.as_mapping()

    assert set(original_fields) == set(loaded_fields)
    assert loaded_fields["id"].required
    assert loaded_fields["meta"].required_count == 0
    assert loaded_fields["name"].required
