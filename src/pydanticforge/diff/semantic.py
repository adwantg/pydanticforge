# Author: gadwant
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelField:
    annotation: str
    required: bool


@dataclass(frozen=True)
class ModelSchema:
    classes: dict[str, dict[str, ModelField]]


@dataclass(frozen=True)
class DiffEntry:
    severity: str
    class_name: str
    field_name: str | None
    message: str


def _normalize_annotation(annotation: str) -> str:
    return annotation.replace("typing.", "").replace(" ", "")


def _split_top_level_union(annotation: str) -> set[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0

    for ch in annotation:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1

        if ch == "|" and depth == 0:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)

    if buf:
        parts.append("".join(buf))

    return {part for part in parts if part}


def _classify_type_change(old: str, new: str) -> str:
    old_set = _split_top_level_union(old)
    new_set = _split_top_level_union(new)

    if old_set == new_set:
        return "same"

    if old_set.issubset(new_set):
        return "widened"

    if new_set.issubset(old_set):
        return "narrowed"

    return "changed"


def _is_basemodel_subclass(class_node: ast.ClassDef) -> bool:
    for base in class_node.bases:
        if isinstance(base, ast.Name) and base.id == "BaseModel":
            return True
        if isinstance(base, ast.Attribute) and base.attr == "BaseModel":
            return True
    return False


def _is_field_required(statement: ast.AnnAssign) -> bool:
    if statement.value is None:
        return True

    if isinstance(statement.value, ast.Call):
        fn = statement.value.func
        if isinstance(fn, ast.Name) and fn.id == "Field":
            if statement.value.args and isinstance(statement.value.args[0], ast.Constant):
                return statement.value.args[0].value is ...
            return False

    return False


def parse_pydantic_models(path: Path) -> ModelSchema:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    classes: dict[str, dict[str, ModelField]] = {}

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if not _is_basemodel_subclass(node):
            continue

        fields: dict[str, ModelField] = {}
        for statement in node.body:
            if not isinstance(statement, ast.AnnAssign):
                continue
            if not isinstance(statement.target, ast.Name):
                continue

            name = statement.target.id
            annotation = _normalize_annotation(ast.unparse(statement.annotation))
            required = _is_field_required(statement)
            fields[name] = ModelField(annotation=annotation, required=required)

        classes[node.name] = fields

    return ModelSchema(classes=classes)


def semantic_diff(old: ModelSchema, new: ModelSchema) -> list[DiffEntry]:
    entries: list[DiffEntry] = []

    old_classes = set(old.classes)
    new_classes = set(new.classes)

    for class_name in sorted(old_classes - new_classes):
        entries.append(
            DiffEntry(
                severity="breaking",
                class_name=class_name,
                field_name=None,
                message="Model removed",
            )
        )

    for class_name in sorted(new_classes - old_classes):
        entries.append(
            DiffEntry(
                severity="non-breaking",
                class_name=class_name,
                field_name=None,
                message="Model added",
            )
        )

    for class_name in sorted(old_classes & new_classes):
        old_fields = old.classes[class_name]
        new_fields = new.classes[class_name]

        old_names = set(old_fields)
        new_names = set(new_fields)

        for field_name in sorted(old_names - new_names):
            entries.append(
                DiffEntry(
                    severity="breaking",
                    class_name=class_name,
                    field_name=field_name,
                    message="Field removed",
                )
            )

        for field_name in sorted(new_names - old_names):
            severity = "breaking" if new_fields[field_name].required else "non-breaking"
            change_type = "required" if new_fields[field_name].required else "optional"
            entries.append(
                DiffEntry(
                    severity=severity,
                    class_name=class_name,
                    field_name=field_name,
                    message=f"New {change_type} field",
                )
            )

        for field_name in sorted(old_names & new_names):
            old_field = old_fields[field_name]
            new_field = new_fields[field_name]

            if old_field.required and not new_field.required:
                entries.append(
                    DiffEntry(
                        severity="non-breaking",
                        class_name=class_name,
                        field_name=field_name,
                        message="Field changed from required to optional",
                    )
                )
            elif not old_field.required and new_field.required:
                entries.append(
                    DiffEntry(
                        severity="breaking",
                        class_name=class_name,
                        field_name=field_name,
                        message="Field changed from optional to required",
                    )
                )

            kind = _classify_type_change(old_field.annotation, new_field.annotation)
            if kind == "same":
                continue

            severity = "non-breaking" if kind == "widened" else "breaking"

            entries.append(
                DiffEntry(
                    severity=severity,
                    class_name=class_name,
                    field_name=field_name,
                    message=f"Type {kind}: {old_field.annotation} -> {new_field.annotation}",
                )
            )

    return entries


def diff_models(old_path: Path, new_path: Path) -> list[DiffEntry]:
    old_schema = parse_pydantic_models(old_path)
    new_schema = parse_pydantic_models(new_path)
    return semantic_diff(old_schema, new_schema)


def format_diff(entries: list[DiffEntry]) -> str:
    if not entries:
        return "No semantic changes detected."

    lines = []
    for entry in entries:
        target = (
            f"{entry.class_name}.{entry.field_name}"
            if entry.field_name is not None
            else entry.class_name
        )
        lines.append(f"[{entry.severity}] {target}: {entry.message}")
    return "\n".join(lines)
