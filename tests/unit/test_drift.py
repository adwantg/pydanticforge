# Author: gadwant
from __future__ import annotations

from pydanticforge.inference.infer import infer_type
from pydanticforge.monitor.drift import detect_drift


def test_detects_type_mismatch_and_new_field() -> None:
    expected = infer_type({"id": 1, "name": "alice"})
    observed = infer_type({"id": "1", "name": "alice", "extra": 99})

    drifts = detect_drift(expected, observed)

    assert any(event.kind == "type_mismatch" and event.path == "$.id" for event in drifts)
    assert any(event.kind == "new_field" and event.path == "$.extra" for event in drifts)
