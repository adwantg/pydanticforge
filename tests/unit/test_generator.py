# Author: gadwant
from __future__ import annotations

from pydanticforge.inference.infer import TypeInferer
from pydanticforge.modelgen.emit import generate_models


def test_generate_models_with_nested_optional_fields() -> None:
    inferer = TypeInferer()
    inferer.observe({"id": 1, "meta": {"tag": "alpha"}})
    inferer.observe({"id": 2.0, "meta": {"tag": "beta", "score": 10}})

    root = inferer.root
    assert root is not None

    code = generate_models(root, root_name="Event")

    assert "class Event(BaseModel):" in code
    assert "id: float" in code
    assert "score: int | None = None" in code

    compile(code, "<generated>", "exec")
