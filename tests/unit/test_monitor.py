# Author: gadwant
from __future__ import annotations

from pathlib import Path

from pydanticforge.inference.infer import infer_type
from pydanticforge.inference.types import ObjectType, UnionType
from pydanticforge.monitor.watcher import monitor_directory_once


def test_monitor_once_detects_drift_and_autopatches(tmp_path: Path) -> None:
    baseline = tmp_path / "a.json"
    drifted = tmp_path / "b.json"

    baseline.write_text('{"id": 1}\n', encoding="utf-8")
    drifted.write_text('{"id": "x"}\n', encoding="utf-8")

    root, report = monitor_directory_once(
        tmp_path,
        expected_root=infer_type({"id": 1}),
        autopatch=True,
    )

    assert report.files_scanned == 2
    assert report.files_with_drift == 1
    assert root is not None
    assert isinstance(root, ObjectType)

    id_node = root.as_mapping()["id"].type_node
    assert isinstance(id_node, UnionType)
