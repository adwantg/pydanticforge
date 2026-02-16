# Author: gadwant
from __future__ import annotations

from pathlib import Path

import pytest

from pydanticforge.io.files import iter_json_files, read_json_file


def test_read_json_file_supports_standard_json(tmp_path: Path) -> None:
    path = tmp_path / "sample.json"
    path.write_text('{"id": 1, "name": "alice"}', encoding="utf-8")

    payload = read_json_file(path)

    assert payload == {"id": 1, "name": "alice"}


def test_read_json_file_supports_ndjson(tmp_path: Path) -> None:
    path = tmp_path / "sample.ndjson"
    path.write_text('{"id": 1}\n{"id": 2, "name": "alice"}\n', encoding="utf-8")

    payload = read_json_file(path)

    assert isinstance(payload, list)
    assert payload[0] == {"id": 1}
    assert payload[1] == {"id": 2, "name": "alice"}


def test_read_json_file_preserves_parse_error_for_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text('{"id":\n 1,\n', encoding="utf-8")

    with pytest.raises(ValueError):
        read_json_file(path)


def test_iter_json_files_includes_json_ndjson_and_jsonl(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text("{}", encoding="utf-8")
    (tmp_path / "b.ndjson").write_text("{}\n", encoding="utf-8")
    (tmp_path / "c.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("{}", encoding="utf-8")

    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "d.json").write_text("{}", encoding="utf-8")

    recursive_files = list(iter_json_files(tmp_path, recursive=True))
    non_recursive_files = list(iter_json_files(tmp_path, recursive=False))

    assert [path.name for path in recursive_files] == ["a.json", "b.ndjson", "c.jsonl", "d.json"]
    assert [path.name for path in non_recursive_files] == ["a.json", "b.ndjson", "c.jsonl"]
