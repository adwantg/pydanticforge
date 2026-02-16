# Author: gadwant
from __future__ import annotations

from dataclasses import dataclass

from pydanticforge.inference.types import (
    ANY,
    NULL,
    ArrayType,
    AnyType,
    BoolType,
    DateTimeType,
    FieldInfo,
    FloatType,
    IntType,
    NullType,
    ObjectType,
    StrType,
    TypeNode,
    UnionType,
)
from pydanticforge.modelgen.naming import ensure_unique_name, to_class_name


@dataclass(frozen=True)
class ModelDef:
    name: str
    node: ObjectType


class ModelRegistry:
    def __init__(self) -> None:
        self._by_node: dict[ObjectType, str] = {}
        self._defs: list[ModelDef] = []
        self._used_names: set[str] = set()

    @property
    def definitions(self) -> list[ModelDef]:
        return list(self._defs)

    def ensure_model(self, node: ObjectType, suggested_name: str) -> str:
        if node in self._by_node:
            return self._by_node[node]

        model_name = ensure_unique_name(to_class_name(suggested_name), self._used_names)
        self._by_node[node] = model_name
        self._defs.append(ModelDef(model_name, node))

        for field_name, field in node.fields:
            self._walk(field.type_node, f"{model_name}{to_class_name(field_name)}")

        return model_name

    def _walk(self, node: TypeNode, suggested_name: str) -> None:
        if isinstance(node, ObjectType):
            self.ensure_model(node, suggested_name)
            return
        if isinstance(node, ArrayType):
            self._walk(node.item_type, f"{suggested_name}Item")
            return
        if isinstance(node, UnionType):
            for option in node.options:
                self._walk(option, suggested_name)


def _annotation(node: TypeNode, registry: ModelRegistry, context_name: str) -> str:
    if isinstance(node, AnyType):
        return "Any"
    if isinstance(node, NullType):
        return "None"
    if isinstance(node, BoolType):
        return "bool"
    if isinstance(node, IntType):
        return "int"
    if isinstance(node, FloatType):
        return "float"
    if isinstance(node, StrType):
        return "str"
    if isinstance(node, DateTimeType):
        return "datetime"
    if isinstance(node, ArrayType):
        return f"list[{_annotation(node.item_type, registry, context_name)}]"
    if isinstance(node, ObjectType):
        return registry.ensure_model(node, context_name)
    if isinstance(node, UnionType):
        option_annotations = sorted(
            {_annotation(option, registry, context_name) for option in node.options}
        )
        if "None" in option_annotations:
            option_annotations = [
                *(part for part in option_annotations if part != "None"),
                "None",
            ]
        return " | ".join(option_annotations)
    raise TypeError(f"Unsupported type node: {type(node)}")


def _field_line(name: str, info: FieldInfo, registry: ModelRegistry, owner_name: str) -> str:
    annotation = _annotation(info.type_node, registry, f"{owner_name}{to_class_name(name)}")
    optional = info.required_count < info.sample_count

    if optional and "None" not in annotation.split(" | "):
        annotation = f"{annotation} | None"

    default = " = None" if optional else ""
    return f"    {name}: {annotation}{default}"


def _render_class(defn: ModelDef, registry: ModelRegistry) -> str:
    lines = [f"class {defn.name}(BaseModel):"]
    lines.append(
        f'    """Inferred from {defn.node.sample_count} sample(s); extra fields are allowed."""'
    )
    lines.append('    model_config = ConfigDict(extra="allow")')

    if not defn.node.fields:
        lines.append("    pass")
        return "\n".join(lines)

    for field_name, info in defn.node.fields:
        lines.append(_field_line(field_name, info, registry, defn.name))

    return "\n".join(lines)


def generate_models(root: TypeNode, *, root_name: str = "PydanticforgeModel") -> str:
    imports = [
        "from __future__ import annotations",
        "",
        "from datetime import datetime",
        "from typing import Any",
        "",
        "from pydantic import BaseModel, ConfigDict, RootModel",
        "",
    ]

    registry = ModelRegistry()

    if isinstance(root, ObjectType):
        registry.ensure_model(root, root_name)
        blocks = [_render_class(defn, registry) for defn in registry.definitions]
        return "\n".join(imports + ["\n\n".join(blocks), ""])

    root_annotation = _annotation(root, registry, root_name)
    block = f"class {to_class_name(root_name)}(RootModel[{root_annotation}]):\n    pass"
    return "\n".join(imports + [block, ""])
