# Author: gadwant
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from pydanticforge.inference.infer import infer_type
from pydanticforge.inference.lattice import join_types
from pydanticforge.inference.types import TypeNode
from pydanticforge.io.files import iter_json_files, read_json_file
from pydanticforge.monitor.drift import DriftEvent, detect_drift


@dataclass(frozen=True)
class FileDrift:
    path: Path
    events: tuple[DriftEvent, ...]


@dataclass(frozen=True)
class MonitorReport:
    files_scanned: int
    files_with_drift: int
    drifts: tuple[FileDrift, ...]


def _iter_samples(payload: object) -> Iterable[object]:
    if isinstance(payload, list):
        yield from payload
    else:
        yield payload


def monitor_directory_once(
    directory: Path,
    *,
    expected_root: TypeNode | None,
    recursive: bool = True,
    autopatch: bool = False,
    strict_numbers: bool = False,
) -> tuple[TypeNode | None, MonitorReport]:
    drifts: list[FileDrift] = []
    files_scanned = 0

    for file_path in iter_json_files(directory, recursive=recursive):
        files_scanned += 1
        payload = read_json_file(file_path)
        file_events: list[DriftEvent] = []

        for sample in _iter_samples(payload):
            observed = infer_type(sample)

            if expected_root is None:
                expected_root = observed
                continue

            file_events.extend(detect_drift(expected_root, observed, path="$"))
            if autopatch and file_events:
                expected_root = join_types(
                    expected_root,
                    observed,
                    strict_numbers=strict_numbers,
                )

        if file_events:
            drifts.append(FileDrift(path=file_path, events=tuple(file_events)))

    report = MonitorReport(
        files_scanned=files_scanned,
        files_with_drift=len(drifts),
        drifts=tuple(drifts),
    )
    return expected_root, report
