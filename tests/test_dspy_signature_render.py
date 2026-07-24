from __future__ import annotations

import dspy
import pytest

from rlmbenchy.rlm.rlm import RLM


class _DummyInterpreter:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}
        self._tools_registered = True
        self.process = None


class _CompareTask(dspy.Signature):
    task: str = dspy.InputField(desc="Task prompt")
    answer: str = dspy.OutputField(desc="Final answer")


def _dataset_lookup(text: str) -> str:
    return text


def _render_signature(label: str, signature: type[dspy.Signature]) -> str:
    lines = [
        f"## {label}",
        "",
        "Instructions:",
        signature.instructions.strip(),
        "",
        "Fields:",
    ]
    for field_name, field in signature.fields.items():
        role = "input" if field_name in signature.input_fields else "output"
        extra = getattr(field, "json_schema_extra", None) or {}
        desc = str(extra.get("desc") or "").strip()
        lines.append(f"- {role}:{field_name}: {desc}")
    return "\n".join(lines)


def test_render_dspy_and_repo_rlm_signature_outputs() -> None:
    # DSPy's built-in RLM reserves llm_query/llm_query_batched names and rejects user
    # tools with those names. We assert that behavior, then render DSPy's default
    # action signature (which already includes built-in llm_query docs).
    with pytest.raises(ValueError, match="conflicts with built-in sandbox function"):
        dspy.RLM(_CompareTask, tools=[dspy.Tool(_dataset_lookup, name="llm_query")])

    dspy_rlm = dspy.RLM(_CompareTask)
    repo_rlm = RLM(
        _CompareTask,
        interpreter=_DummyInterpreter(),  # type: ignore[arg-type]
        tools=[dspy.Tool(_dataset_lookup, name="dataset_lookup")],
    )

    dspy_rendered = _render_signature(
        "dspy.RLM.generate_action.signature",
        dspy_rlm.generate_action.signature,
    )
    repo_rendered = _render_signature(
        "RLM.generate_action.signature",
        repo_rlm.generate_action.signature,
    )

    print("\n=== DSPy RLM Signature ===\n")
    print(dspy_rendered)
    print("\n=== Repo RLM Signature ===\n")
    print(repo_rendered)

    # Keep lightweight assertions so this remains a stable compare harness.
    assert "llm_query" in dspy_rendered
    assert "llm_query" in repo_rendered
    assert "repl_history" in dspy_rendered
    assert "repl_history" in repo_rendered
    assert "input:variables_info" in repo_rendered
