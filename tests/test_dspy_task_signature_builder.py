from __future__ import annotations

import pickle

import dspy
import pytest

from rlmbenchy.rlm.signatures import SignatureFieldSpec, build_task_signature


PickleRoundTripTaskSignature = build_task_signature(
    name="PickleRoundTripTaskSignature",
    instructions="Return the answer.",
    inputs=[SignatureFieldSpec("question", str, "Question.")],
    outputs=[SignatureFieldSpec("answer", str, "Answer.")],
)


def test_build_task_signature_creates_named_signature_with_expected_fields() -> None:
    signature = build_task_signature(
        name="SearchTaskSignature",
        instructions="Answer the question using the provided retrieval metadata.",
        inputs=[
            SignatureFieldSpec("question", str, "Question to answer."),
            SignatureFieldSpec("docs_total", int, "Number of available documents."),
        ],
        outputs=[
            SignatureFieldSpec("answer", str, "Final answer."),
            SignatureFieldSpec("confidence", float, "Confidence score."),
        ],
    )

    assert issubclass(signature, dspy.Signature)
    assert signature.__name__ == "SearchTaskSignature"
    assert signature.instructions == (
        "Answer the question using the provided retrieval metadata."
    )
    assert list(signature.input_fields) == ["question", "docs_total"]
    assert list(signature.output_fields) == ["answer", "confidence"]
    assert signature.fields["docs_total"].annotation is int
    assert signature.fields["confidence"].annotation is float
    assert (
        signature.fields["question"].json_schema_extra["desc"] == "Question to answer."
    )
    assert signature.fields["answer"].json_schema_extra["desc"] == "Final answer."


def test_build_task_signature_preserves_caller_module_for_pickling() -> None:
    assert PickleRoundTripTaskSignature.__module__ == __name__
    assert pickle.loads(pickle.dumps(PickleRoundTripTaskSignature)) is (
        PickleRoundTripTaskSignature
    )


def test_build_task_signature_rejects_duplicate_field_names() -> None:
    with pytest.raises(ValueError, match="Duplicate signature field name"):
        build_task_signature(
            name="DuplicateTaskSignature",
            instructions="Return the answer.",
            inputs=[SignatureFieldSpec("question", str, "Question.")],
            outputs=[SignatureFieldSpec("question", str, "Answer.")],
        )


def test_build_task_signature_requires_output_field() -> None:
    with pytest.raises(
        ValueError, match="Task signatures must declare at least one output field"
    ):
        build_task_signature(
            name="InputOnlySignature",
            instructions="Inspect the task.",
            inputs=[SignatureFieldSpec("question", str, "Question.")],
            outputs=[],
        )


@pytest.mark.parametrize("field_name", ["class", "from"])
def test_build_task_signature_rejects_python_keywords(field_name: str) -> None:
    with pytest.raises(ValueError, match="Python keywords are not allowed"):
        build_task_signature(
            name="KeywordTaskSignature",
            instructions="Return the answer.",
            inputs=[SignatureFieldSpec("question", str, "Question.")],
            outputs=[SignatureFieldSpec(field_name, str, "Answer.")],
        )


@pytest.mark.parametrize("field_name", ["trajectory", "final_reasoning"])
def test_build_task_signature_rejects_reserved_rlm_output_names(
    field_name: str,
) -> None:
    with pytest.raises(ValueError, match="reserved by RLM runtime metadata"):
        build_task_signature(
            name="ReservedOutputTaskSignature",
            instructions="Return the answer.",
            inputs=[SignatureFieldSpec("question", str, "Question.")],
            outputs=[SignatureFieldSpec(field_name, str, "Answer.")],
        )
