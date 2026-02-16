# Author: gadwant
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from pydanticforge.cli import (
    EXIT_MONITOR_WARNING,
    main,
)


def _run_with_stdin(argv: list[str], data: str) -> int:
    old_stdin = sys.stdin
    sys.stdin = io.StringIO(data)
    try:
        return main(argv)
    finally:
        sys.stdin = old_stdin


def test_generate_command_from_stdin(tmp_path: Path) -> None:
    output = tmp_path / "models.py"

    exit_code = _run_with_stdin(
        ["generate", "--output", str(output)],
        '{"id": 1}\n{"id": 2, "name": "alice"}\n',
    )

    assert exit_code == 0
    assert output.exists()
    text = output.read_text(encoding="utf-8")
    assert "class PydanticforgeModel(BaseModel):" in text
    assert "name: str | None = None" in text


def test_generate_from_json_schema(tmp_path: Path) -> None:
    schema_file = tmp_path / "schema.json"
    schema_file.write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "title": "User",
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                },
                "required": ["id"],
            }
        ),
        encoding="utf-8",
    )

    output = tmp_path / "models.py"
    exit_code = main(
        [
            "generate",
            "--from-json-schema",
            str(schema_file),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    text = output.read_text(encoding="utf-8")
    assert "id: int" in text
    assert "name: str | None = None" in text


def test_diff_command_reports_breaking_change(tmp_path: Path, capsys: object) -> None:
    old_model = tmp_path / "old.py"
    new_model = tmp_path / "new.py"

    old_model.write_text(
        "\n".join(
            [
                "from pydantic import BaseModel",
                "class X(BaseModel):",
                "    value: int",
            ]
        ),
        encoding="utf-8",
    )
    new_model.write_text(
        "\n".join(
            [
                "from pydantic import BaseModel",
                "class X(BaseModel):",
                "    value: str",
            ]
        ),
        encoding="utf-8",
    )

    exit_code = main(["diff", str(old_model), str(new_model)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "[breaking] X.value" in captured.out


def test_diff_command_json_format(tmp_path: Path, capsys: object) -> None:
    old_model = tmp_path / "old.py"
    new_model = tmp_path / "new.py"

    old_model.write_text(
        "\n".join(
            [
                "from pydantic import BaseModel",
                "class X(BaseModel):",
                "    value: int",
            ]
        ),
        encoding="utf-8",
    )
    new_model.write_text(
        "\n".join(
            [
                "from pydantic import BaseModel",
                "class X(BaseModel):",
                "    value: int | str",
            ]
        ),
        encoding="utf-8",
    )

    exit_code = main(["diff", str(old_model), str(new_model), "--format", "json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["summary"]["total_changes"] >= 1
    assert any(change["field_name"] == "value" for change in payload["changes"])


def test_monitor_json_format_and_fail_on_any(tmp_path: Path, capsys: object) -> None:
    state_file = tmp_path / "state.json"
    _run_with_stdin(
        ["generate", "--save-state", str(state_file)],
        '{"id": 1, "name": "a"}\n',
    )
    capsys.readouterr()

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "sample.json").write_text('{"id": 2, "name": "b", "extra": true}', encoding="utf-8")

    exit_code = main(
        [
            "monitor",
            str(logs_dir),
            "--state",
            str(state_file),
            "--format",
            "json",
            "--fail-on",
            "any",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_MONITOR_WARNING
    payload = json.loads(captured.out)
    assert payload["summary"]["warning_events"] >= 1
    assert payload["summary"]["breaking_events"] == 0


def test_status_json_snapshot(tmp_path: Path, capsys: object) -> None:
    state_file = tmp_path / "state.json"
    _run_with_stdin(
        ["generate", "--save-state", str(state_file)],
        '{"id": 1}\n{"id": 2, "name": "x"}\n',
    )
    capsys.readouterr()

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "sample.json").write_text('{"id": 3, "name": "ok"}', encoding="utf-8")

    exit_code = main(["status", str(logs_dir), "--state", str(state_file), "--format", "json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["state_path"] == str(state_file)
    assert "state_hash" in payload
    assert "drift" in payload


def test_schema_command_state_to_json_schema_and_back(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    schema_file = tmp_path / "schema.json"
    rebuilt_state = tmp_path / "rebuilt_state.json"

    _run_with_stdin(
        ["generate", "--save-state", str(state_file)],
        '{"id": 1, "name": "alice"}\n',
    )

    exit_code = main(
        [
            "schema",
            "--from-state",
            str(state_file),
            "--to-json-schema",
            str(schema_file),
        ]
    )
    assert exit_code == 0
    assert schema_file.exists()

    exit_code = main(
        [
            "schema",
            "--from-json-schema",
            str(schema_file),
            "--to-state",
            str(rebuilt_state),
        ]
    )
    assert exit_code == 0
    assert rebuilt_state.exists()


def test_monitor_breaking_exit_code(tmp_path: Path, capsys: object) -> None:
    state_file = tmp_path / "state.json"
    _run_with_stdin(
        ["generate", "--save-state", str(state_file)],
        '{"id": 1}\n',
    )
    capsys.readouterr()

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "sample.json").write_text('{"id": "oops"}', encoding="utf-8")

    exit_code = main(
        [
            "monitor",
            str(logs_dir),
            "--state",
            str(state_file),
            "--format",
            "json",
            "--fail-on",
            "breaking",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 21
    payload = json.loads(captured.out)
    assert payload["summary"]["breaking_events"] >= 1
