"""Helpers for constructing DSPy task signatures programmatically."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import keyword
import sys
from typing import Any

import dspy


RESERVED_RLM_PREDICTION_FIELDS = frozenset({"trajectory", "final_reasoning"})


@dataclass(frozen=True)
class SignatureFieldSpec:
    """Declarative description of one DSPy signature field."""

    name: str
    type_: Any = str
    desc: str = ""


def _append_fields(
    signature: type[dspy.Signature],
    fields: Sequence[SignatureFieldSpec],
    *,
    output: bool,
    seen_names: set[str],
) -> type[dspy.Signature]:
    for spec in fields:
        field_name = str(spec.name).strip()
        if not field_name:
            raise ValueError("Signature field names must be non-empty.")
        if not field_name.isidentifier():
            raise ValueError(
                f"Invalid signature field name {field_name!r}: must be a valid Python identifier."
            )
        if keyword.iskeyword(field_name):
            raise ValueError(
                f"Invalid signature field name {field_name!r}: Python keywords are not allowed."
            )
        if output and field_name in RESERVED_RLM_PREDICTION_FIELDS:
            raise ValueError(
                f"Invalid signature field name {field_name!r}: reserved by RLM runtime metadata."
            )
        if field_name in seen_names:
            raise ValueError(f"Duplicate signature field name: {field_name!r}")
        seen_names.add(field_name)
        field = (
            dspy.OutputField(desc=str(spec.desc).strip())
            if output
            else dspy.InputField(desc=str(spec.desc).strip())
        )
        signature = signature.append(field_name, field, type_=spec.type_)
    return signature


def _resolve_caller_module_name() -> str:
    caller_frame = sys._getframe(2)
    return str(caller_frame.f_globals.get("__name__", __name__))


def build_task_signature(
    *,
    name: str,
    instructions: str,
    inputs: Sequence[SignatureFieldSpec],
    outputs: Sequence[SignatureFieldSpec],
    module: str | None = None,
) -> type[dspy.Signature]:
    """Build a named DSPy signature from declarative field specs."""

    resolved_name = str(name).strip() or "DynamicTaskSignature"
    resolved_module = str(module).strip() if module is not None else ""
    if not resolved_module:
        resolved_module = _resolve_caller_module_name()
    if not outputs:
        raise ValueError("Task signatures must declare at least one output field.")

    signature = dspy.make_signature({}, str(instructions).strip())
    seen_names: set[str] = set()
    signature = _append_fields(signature, inputs, output=False, seen_names=seen_names)
    signature = _append_fields(signature, outputs, output=True, seen_names=seen_names)
    signature.__name__ = resolved_name
    signature.__qualname__ = resolved_name
    signature.__module__ = resolved_module
    signature.__doc__ = str(instructions).strip()
    module_obj = sys.modules.get(resolved_module)
    if module_obj is not None:
        setattr(module_obj, resolved_name, signature)
    return signature


__all__ = [
    "RESERVED_RLM_PREDICTION_FIELDS",
    "SignatureFieldSpec",
    "build_task_signature",
]
