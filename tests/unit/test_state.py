# Author: gadwant
from __future__ import annotations

from pathlib import Path

from pydanticforge.inference.infer import TypeInferer
from pydanticforge.state import load_schema_state, save_schema_state


def test_state_round_trip(tmp_path: Path) -> None:
    inferer = TypeInferer()
    inferer.observe({"id": 1, "name": "a"})
    inferer.observe({"id": 2})

    root = inferer.root
    assert root is not None

    state_file = tmp_path / "state.json"
    save_schema_state(state_file, root)
    loaded = load_schema_state(state_file)

    assert loaded == root
