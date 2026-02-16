# Author: gadwant
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, cast

from pydanticforge.diff.semantic import DiffEntry, diff_models, format_diff
from pydanticforge.inference.infer import TypeInferer
from pydanticforge.inference.types import (
    ANY,
    BOOL,
    DATETIME,
    FLOAT,
    INT,
    NULL,
    STR,
    ArrayType,
    ObjectType,
    TypeNode,
    UnionType,
    type_name,
)
from pydanticforge.io.files import iter_json_files, read_json_file
from pydanticforge.io.stream import iter_json_from_stream
from pydanticforge.json_schema import load_json_schema, save_json_schema
from pydanticforge.modelgen.emit import generate_models
from pydanticforge.monitor.drift import drift_severity
from pydanticforge.monitor.watcher import MonitorReport, monitor_directory_once
from pydanticforge.state import load_schema_state, save_schema_state, schema_state_hash

EXIT_OK = 0
EXIT_MONITOR_WARNING = 20
EXIT_MONITOR_BREAKING = 21


def _iter_samples(payload: object) -> Iterable[object]:
    if isinstance(payload, list):
        yield from payload
    else:
        yield payload


def _infer_from_paths(paths: list[Path], *, strict_numbers: bool = False) -> TypeNode | None:
    inferer = TypeInferer(strict_numbers=strict_numbers)

    for path in paths:
        files = iter_json_files(path, recursive=True) if path.is_dir() else [path]

        for file_path in files:
            payload = read_json_file(file_path)
            inferer.observe_many(_iter_samples(payload))

    return inferer.root


def _emit_output(code: str, *, output: Path | None) -> None:
    if output is None:
        print(code)
        return

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(code, encoding="utf-8")
    print(f"Wrote models to {output}")


def _write_text_output(text: str, *, output: Path | None) -> None:
    if output is None:
        print(text)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text + "\n", encoding="utf-8")
    print(f"Wrote report to {output}")


def _diff_payload(entries: list[DiffEntry]) -> dict[str, Any]:
    breaking = sum(1 for entry in entries if entry.severity == "breaking")
    non_breaking = sum(1 for entry in entries if entry.severity != "breaking")
    return {
        "summary": {
            "total_changes": len(entries),
            "breaking_changes": breaking,
            "non_breaking_changes": non_breaking,
        },
        "changes": [
            {
                "severity": entry.severity,
                "class_name": entry.class_name,
                "field_name": entry.field_name,
                "message": entry.message,
            }
            for entry in entries
        ],
    }


def _monitor_report_payload(report: MonitorReport) -> dict[str, Any]:
    warning_events = 0
    breaking_events = 0
    files: list[dict[str, Any]] = []

    for file_drift in report.drifts:
        events_payload: list[dict[str, Any]] = []
        for event in file_drift.events:
            severity = drift_severity(event)
            if severity == "breaking":
                breaking_events += 1
            else:
                warning_events += 1

            events_payload.append(
                {
                    "path": event.path,
                    "expected": event.expected,
                    "observed": event.observed,
                    "kind": event.kind,
                    "severity": severity,
                }
            )

        files.append({"path": str(file_drift.path), "events": events_payload})

    total_events = warning_events + breaking_events
    return {
        "summary": {
            "files_scanned": report.files_scanned,
            "files_with_drift": report.files_with_drift,
            "total_events": total_events,
            "breaking_events": breaking_events,
            "warning_events": warning_events,
        },
        "files": files,
    }


def _monitor_payload_text(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [f"Scanned {summary['files_scanned']} file(s)"]

    if summary["total_events"] == 0:
        lines.append("No schema drift detected.")
        return "\n".join(lines)

    lines.append(
        "Detected "
        f"{summary['total_events']} drift event(s) in "
        f"{summary['files_with_drift']} file(s)."
    )
    lines.append(f"Breaking: {summary['breaking_events']} | Warning: {summary['warning_events']}")

    for file_payload in payload["files"]:
        lines.append(f"- {file_payload['path']}")
        for event in file_payload["events"]:
            lines.append(
                "  "
                f"[{event['severity']}/{event['kind']}] {event['path']}: "
                f"expected {event['expected']}, observed {event['observed']}"
            )

    return "\n".join(lines)


def _monitor_exit_code(fail_on: str, payload: dict[str, Any]) -> int:
    summary = payload["summary"]

    if fail_on == "none":
        return EXIT_OK

    if fail_on == "breaking":
        if summary["breaking_events"] > 0:
            return EXIT_MONITOR_BREAKING
        return EXIT_OK

    if fail_on == "any":
        if summary["breaking_events"] > 0:
            return EXIT_MONITOR_BREAKING
        if summary["warning_events"] > 0:
            return EXIT_MONITOR_WARNING
        return EXIT_OK

    raise ValueError(f"Unsupported --fail-on value: {fail_on}")


def _schema_summary(root: TypeNode) -> dict[str, Any]:
    counts: dict[str, int] = {
        "any": 0,
        "null": 0,
        "bool": 0,
        "int": 0,
        "float": 0,
        "str": 0,
        "datetime": 0,
        "array": 0,
        "object": 0,
        "union": 0,
        "field_total": 0,
        "field_required": 0,
        "field_optional": 0,
    }

    def walk(node: TypeNode) -> None:
        if node == ANY:
            counts["any"] += 1
            return
        if node == NULL:
            counts["null"] += 1
            return
        if node == BOOL:
            counts["bool"] += 1
            return
        if node == INT:
            counts["int"] += 1
            return
        if node == FLOAT:
            counts["float"] += 1
            return
        if node == STR:
            counts["str"] += 1
            return
        if node == DATETIME:
            counts["datetime"] += 1
            return
        if isinstance(node, ArrayType):
            counts["array"] += 1
            walk(node.item_type)
            return
        if isinstance(node, ObjectType):
            counts["object"] += 1
            counts["field_total"] += len(node.fields)
            for _, field in node.fields:
                if field.required:
                    counts["field_required"] += 1
                else:
                    counts["field_optional"] += 1
                walk(field.type_node)
            return
        if isinstance(node, UnionType):
            counts["union"] += 1
            for option in node.options:
                walk(option)
            return
        raise TypeError(f"Unsupported TypeNode: {type(node)}")

    walk(root)

    return {
        "root_type": type_name(root),
        "counts": counts,
    }


def _status_payload(root: TypeNode, *, state_path: Path) -> dict[str, Any]:
    return {
        "state_path": str(state_path),
        "state_hash": schema_state_hash(root),
        "schema": _schema_summary(root),
    }


def _status_text(payload: dict[str, Any]) -> str:
    lines = [
        f"State: {payload['state_path']}",
        f"State hash: {payload['state_hash']}",
        f"Root type: {payload['schema']['root_type']}",
    ]

    counts = payload["schema"]["counts"]
    scalar_count = (
        counts["bool"]
        + counts["int"]
        + counts["float"]
        + counts["str"]
        + counts["datetime"]
        + counts["null"]
        + counts["any"]
    )
    lines.append(
        "Type counts: "
        f"object={counts['object']}, array={counts['array']}, union={counts['union']}, "
        f"scalars={scalar_count}"
    )
    lines.append(
        "Fields: "
        f"total={counts['field_total']}, "
        f"required={counts['field_required']}, "
        f"optional={counts['field_optional']}"
    )

    drift_payload = payload.get("drift")
    if drift_payload:
        summary = drift_payload["summary"]
        lines.append("Drift snapshot:")
        lines.append(
            "  scanned="
            f"{summary['files_scanned']}, "
            f"files_with_drift={summary['files_with_drift']}, "
            f"events={summary['total_events']} "
            f"(breaking={summary['breaking_events']}, warning={summary['warning_events']})"
        )

    return "\n".join(lines)


def _cmd_watch(args: argparse.Namespace) -> int:
    if args.input != "stdin":
        raise ValueError("Only --input stdin is currently supported.")

    inferer = TypeInferer(strict_numbers=args.strict_numbers)

    for sample_count, payload in enumerate(iter_json_from_stream(sys.stdin), start=1):
        inferer.observe(payload)

        if args.every and sample_count % args.every == 0 and inferer.root is not None:
            code = generate_models(inferer.root, root_name=args.root_name)
            _emit_output(code, output=args.output)

    if inferer.root is None:
        raise ValueError("No JSON payloads found on stdin.")

    code = generate_models(inferer.root, root_name=args.root_name)
    _emit_output(code, output=args.output)

    save_schema_state(args.state, inferer.root)
    print(f"Saved state to {args.state}")

    if args.export_json_schema is not None:
        save_json_schema(args.export_json_schema, inferer.root, title=args.json_schema_title)
        print(f"Wrote JSON Schema to {args.export_json_schema}")

    return EXIT_OK


def _cmd_generate(args: argparse.Namespace) -> int:
    if args.from_state is not None and args.from_json_schema is not None:
        raise ValueError("Use only one of --from-state or --from-json-schema.")

    root: TypeNode | None = None

    if args.from_state is not None:
        root = load_schema_state(args.from_state)
    elif args.from_json_schema is not None:
        root = load_json_schema(args.from_json_schema)
    elif args.input:
        root = _infer_from_paths(args.input, strict_numbers=args.strict_numbers)
    else:
        inferer = TypeInferer(strict_numbers=args.strict_numbers)
        inferer.observe_many(iter_json_from_stream(sys.stdin))
        root = inferer.root

    if root is None:
        raise ValueError("No schema could be inferred from inputs.")

    code = generate_models(root, root_name=args.root_name)
    _emit_output(code, output=args.output)

    if args.save_state is not None:
        save_schema_state(args.save_state, root)
        print(f"Saved state to {args.save_state}")

    if args.export_json_schema is not None:
        save_json_schema(args.export_json_schema, root, title=args.json_schema_title)
        print(f"Wrote JSON Schema to {args.export_json_schema}")

    return EXIT_OK


def _cmd_monitor(args: argparse.Namespace) -> int:
    expected: TypeNode | None = None
    if args.state.exists():
        expected = load_schema_state(args.state)

    new_root, report = monitor_directory_once(
        args.directory,
        expected_root=expected,
        recursive=args.recursive,
        autopatch=args.autopatch,
        strict_numbers=args.strict_numbers,
    )

    payload = _monitor_report_payload(report)

    actions: dict[str, str] = {}
    if new_root is not None:
        save_schema_state(args.state, new_root)
        actions["saved_state"] = str(args.state)

        if args.autopatch and args.model_output is not None:
            code = generate_models(new_root, root_name=args.root_name)
            args.model_output.parent.mkdir(parents=True, exist_ok=True)
            args.model_output.write_text(code, encoding="utf-8")
            actions["saved_model"] = str(args.model_output)

        if args.autopatch and args.export_json_schema is not None:
            save_json_schema(args.export_json_schema, new_root, title=args.json_schema_title)
            actions["saved_json_schema"] = str(args.export_json_schema)

    if args.format == "json":
        if actions:
            payload["actions"] = actions
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_monitor_payload_text(payload))
        for label, path in actions.items():
            print(f"{label}: {path}")

    return _monitor_exit_code(args.fail_on, payload)


def _cmd_diff(args: argparse.Namespace) -> int:
    entries = diff_models(args.old_model, args.new_model)

    if args.format == "json":
        payload = _diff_payload(entries)
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(format_diff(entries))

    if args.fail_on_breaking and any(entry.severity == "breaking" for entry in entries):
        return 1

    return EXIT_OK


def _cmd_status(args: argparse.Namespace) -> int:
    if not args.state.exists():
        raise ValueError(f"State file does not exist: {args.state}")

    root = load_schema_state(args.state)
    payload = _status_payload(root, state_path=args.state)

    if args.directory is not None:
        _, monitor_report = monitor_directory_once(
            args.directory,
            expected_root=root,
            recursive=args.recursive,
            autopatch=False,
            strict_numbers=args.strict_numbers,
        )
        payload["drift"] = _monitor_report_payload(monitor_report)

    if args.format == "json":
        text = json.dumps(payload, indent=2, sort_keys=True)
    else:
        text = _status_text(payload)

    _write_text_output(text, output=args.output)
    return EXIT_OK


def _cmd_schema(args: argparse.Namespace) -> int:
    if (args.from_state is None) == (args.from_json_schema is None):
        raise ValueError("Specify exactly one input: --from-state or --from-json-schema.")

    if args.to_state is None and args.to_json_schema is None:
        raise ValueError("Specify at least one output: --to-state and/or --to-json-schema.")

    if args.from_state is not None:
        root = load_schema_state(args.from_state)
    else:
        root = load_json_schema(args.from_json_schema)

    if args.to_state is not None:
        save_schema_state(args.to_state, root)
        print(f"Wrote state to {args.to_state}")

    if args.to_json_schema is not None:
        save_json_schema(args.to_json_schema, root, title=args.json_schema_title)
        print(f"Wrote JSON Schema to {args.to_json_schema}")

    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pydanticforge",
        description="Infer and maintain Pydantic models from messy, evolving JSON.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    watch = subparsers.add_parser("watch", help="Infer schema incrementally from a JSON stream.")
    watch.add_argument("--input", default="stdin", help="Input source; only 'stdin' is supported.")
    watch.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write generated models to this file.",
    )
    watch.add_argument("--state", type=Path, default=Path(".pydanticforge/state.json"))
    watch.add_argument("--root-name", default="PydanticforgeModel")
    watch.add_argument("--every", type=int, default=0)
    watch.add_argument("--strict-numbers", action="store_true")
    watch.add_argument("--export-json-schema", type=Path, default=None)
    watch.add_argument("--json-schema-title", default="PydanticforgeSchema")
    watch.set_defaults(_handler=_cmd_watch)

    generate = subparsers.add_parser(
        "generate",
        help="Generate Pydantic models from inferred schema.",
    )
    generate.add_argument(
        "--input",
        type=Path,
        action="append",
        default=[],
        help="Input JSON file/directory. Repeat for multiple sources.",
    )
    generate.add_argument("--output", type=Path, default=None)
    generate.add_argument("--from-state", type=Path, default=None)
    generate.add_argument("--from-json-schema", type=Path, default=None)
    generate.add_argument("--save-state", type=Path, default=None)
    generate.add_argument("--export-json-schema", type=Path, default=None)
    generate.add_argument("--json-schema-title", default="PydanticforgeSchema")
    generate.add_argument("--root-name", default="PydanticforgeModel")
    generate.add_argument("--strict-numbers", action="store_true")
    generate.set_defaults(_handler=_cmd_generate)

    monitor = subparsers.add_parser("monitor", help="Scan JSON files for schema drift.")
    monitor.add_argument("directory", type=Path)
    monitor.add_argument("--state", type=Path, default=Path(".pydanticforge/state.json"))
    monitor.add_argument("--model-output", type=Path, default=None)
    monitor.add_argument("--export-json-schema", type=Path, default=None)
    monitor.add_argument("--json-schema-title", default="PydanticforgeSchema")
    monitor.add_argument("--root-name", default="PydanticforgeModel")
    monitor.add_argument("--recursive", action=argparse.BooleanOptionalAction, default=True)
    monitor.add_argument("--autopatch", action="store_true")
    monitor.add_argument("--strict-numbers", action="store_true")
    monitor.add_argument("--format", choices=("text", "json"), default="text")
    monitor.add_argument("--fail-on", choices=("none", "breaking", "any"), default="none")
    monitor.set_defaults(_handler=_cmd_monitor)

    diff = subparsers.add_parser("diff", help="Show semantic diff between model files.")
    diff.add_argument("old_model", type=Path)
    diff.add_argument("new_model", type=Path)
    diff.add_argument("--format", choices=("text", "json"), default="text")
    diff.add_argument("--fail-on-breaking", action="store_true")
    diff.set_defaults(_handler=_cmd_diff)

    status = subparsers.add_parser(
        "status",
        help="Emit deterministic schema/drift status for CI snapshots.",
    )
    status.add_argument("directory", type=Path, nargs="?", default=None)
    status.add_argument("--state", type=Path, default=Path(".pydanticforge/state.json"))
    status.add_argument("--recursive", action=argparse.BooleanOptionalAction, default=True)
    status.add_argument("--strict-numbers", action="store_true")
    status.add_argument("--format", choices=("text", "json"), default="text")
    status.add_argument("--output", type=Path, default=None)
    status.set_defaults(_handler=_cmd_status)

    schema = subparsers.add_parser(
        "schema",
        help="Convert between pydanticforge state and JSON Schema.",
    )
    schema.add_argument("--from-state", type=Path, default=None)
    schema.add_argument("--from-json-schema", type=Path, default=None)
    schema.add_argument("--to-state", type=Path, default=None)
    schema.add_argument("--to-json-schema", type=Path, default=None)
    schema.add_argument("--json-schema-title", default="PydanticforgeSchema")
    schema.set_defaults(_handler=_cmd_schema)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = args._handler
    if not callable(handler):
        raise TypeError("Invalid command handler")
    typed_handler = handler
    return cast(Callable[[argparse.Namespace], int], typed_handler)(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
