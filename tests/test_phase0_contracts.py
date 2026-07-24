"""Phase 0 contract validation tests.

These tests verify that the core contracts (stop-reason taxonomy, REPL
runtime protocol) are internally consistent and usable by downstream code.
"""

from __future__ import annotations

from typing import Any

from dspy.primitives.code_interpreter import CodeInterpreter

from rlmbenchy.rlm.types import StopReason


class TestStopReason:
    def test_all_values_are_strings(self):
        for sr in StopReason:
            assert isinstance(sr.value, str)
            assert sr.value

    def test_expected_members(self):
        expected = {
            "success",
            "parse_failure",
            "execution_error",
            "no_final",
        }
        actual = {sr.value for sr in StopReason}
        assert actual == expected

    def test_string_comparison(self):
        assert StopReason.SUCCESS == "success"
        assert StopReason.PARSE_FAILURE == "parse_failure"


# ---------------------------------------------------------------------------
# REPL runtime protocol
# ---------------------------------------------------------------------------


class TestCodeInterpreterProtocol:
    def test_protocol_is_runtime_checkable(self):
        """CodeInterpreter can be used with isinstance() checks."""
        assert hasattr(CodeInterpreter, "__protocol_attrs__") or hasattr(
            CodeInterpreter, "__abstractmethods__"
        )

    def test_conforming_class_is_recognized(self):
        class FakeRepl:
            @property
            def tools(self) -> dict:
                return {}

            def start(self):
                pass

            def execute(self, code: str, variables: dict[str, Any] | None = None):
                return None

            def shutdown(self):
                pass

        assert isinstance(FakeRepl(), CodeInterpreter)

    def test_non_conforming_class_is_rejected(self):
        class Incomplete:
            def execute(self, code):
                return None

        assert not isinstance(Incomplete(), CodeInterpreter)
