# Author: gadwant
from __future__ import annotations

from pathlib import Path

from pydanticforge.diff.semantic import diff_models


def test_semantic_diff_classifies_breaking_and_non_breaking(tmp_path: Path) -> None:
    old_file = tmp_path / "old.py"
    new_file = tmp_path / "new.py"

    old_file.write_text(
        "\n".join(
            [
                "from pydantic import BaseModel",
                "",
                "class User(BaseModel):",
                "    id: int",
                "    nickname: str | None = None",
            ]
        ),
        encoding="utf-8",
    )

    new_file.write_text(
        "\n".join(
            [
                "from pydantic import BaseModel",
                "",
                "class User(BaseModel):",
                "    id: int | str",
                "    nickname: str",
                "    email: str | None = None",
            ]
        ),
        encoding="utf-8",
    )

    entries = diff_models(old_file, new_file)

    assert any(
        entry.severity == "non-breaking" and entry.field_name == "id" and "widened" in entry.message
        for entry in entries
    )
    assert any(
        entry.severity == "breaking"
        and entry.field_name == "nickname"
        and "optional to required" in entry.message
        for entry in entries
    )
    assert any(
        entry.severity == "non-breaking"
        and entry.field_name == "email"
        and "optional" in entry.message
        for entry in entries
    )
