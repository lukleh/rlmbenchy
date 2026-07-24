"""Tests for LiveStepDisplay — rich per-step console output."""

from __future__ import annotations

import re
from io import StringIO
from typing import Any

from rich.console import Console
from rlmbenchy.logger.live_display import LiveStepDisplay

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _make_event(
    event_type: str,
    *,
    step_index: int | None = None,
    data: dict[str, Any] | None = None,
    stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "event_type": event_type,
        "data": data or {},
        "stats": stats or {},
        "summary": {},
    }
    if step_index is not None:
        entry["step_index"] = step_index
    return entry


def _step_started(step_index: int) -> dict[str, Any]:
    return _make_event("step.started", step_index=step_index)


def _step_finished(step_index: int) -> dict[str, Any]:
    return _make_event("step.finished", step_index=step_index)


def _build_display() -> tuple[LiveStepDisplay, StringIO]:
    buf = StringIO()
    console = Console(file=buf, force_terminal=True, width=200)
    display = LiveStepDisplay(max_iterations=10, console=console)
    return display, buf


def _flush_output(display: LiveStepDisplay, buf: StringIO) -> str:
    # Trigger flush via step.finished then run.finished
    display.handle_event(_make_event("run.finished"))
    return _ANSI_RE.sub("", buf.getvalue())


class TestStepBoundary:
    def test_new_step_index_starts_new_step(self) -> None:
        display, buf = _build_display()
        display.handle_event(_step_started(1))
        display.handle_event(
            _make_event(
                "llm.response",
                step_index=1,
                stats={
                    "prompt_tokens": 100,
                    "generated_tokens": 50,
                    "cost_usd": 0.001,
                },
            )
        )
        display.handle_event(
            _make_event(
                "repl.request", step_index=1, data={"code": "print(1)\nprint(2)"}
            )
        )
        display.handle_event(
            _make_event("repl.response", step_index=1, data={"output": "hello"})
        )
        # Step 2 starts — step 1 should be flushed
        display.handle_event(_step_finished(1))
        display.handle_event(_step_started(2))
        display.handle_event(
            _make_event(
                "llm.response",
                step_index=2,
                stats={
                    "prompt_tokens": 200,
                    "generated_tokens": 80,
                    "cost_usd": 0.002,
                },
            )
        )
        output = buf.getvalue()
        assert "1/10" in output  # step 1 was flushed

    def test_run_finished_flushes_last_step(self) -> None:
        display, buf = _build_display()
        display.handle_event(_step_started(1))
        display.handle_event(
            _make_event(
                "llm.response",
                step_index=1,
                stats={
                    "prompt_tokens": 100,
                    "generated_tokens": 50,
                },
            )
        )
        output = _flush_output(display, buf)
        assert "1/10" in output


class TestTokenAccumulation:
    def test_step_tokens_accumulate(self) -> None:
        display, buf = _build_display()
        display.handle_event(_step_started(1))
        # Two LLM calls in the same step (subcall)
        display.handle_event(
            _make_event(
                "llm.response",
                step_index=1,
                stats={
                    "prompt_tokens": 100,
                    "generated_tokens": 50,
                    "cost_usd": 0.001,
                },
            )
        )
        display.handle_event(
            _make_event(
                "llm.response",
                step_index=1,
                stats={
                    "prompt_tokens": 200,
                    "generated_tokens": 80,
                    "cost_usd": 0.002,
                },
            )
        )
        output = _flush_output(display, buf)
        assert "300 prompt / 130 output / 430 total" in output
        assert "2 lm call(s)" in output

    def test_run_totals_accumulate_across_steps(self) -> None:
        display, buf = _build_display()
        display.handle_event(_step_started(1))
        display.handle_event(
            _make_event(
                "llm.response",
                step_index=1,
                stats={
                    "prompt_tokens": 100,
                    "generated_tokens": 50,
                    "cost_usd": 0.001,
                },
            )
        )
        display.handle_event(
            _make_event("repl.response", step_index=1, data={"output": "ok"})
        )
        # Step 2
        display.handle_event(_step_finished(1))
        display.handle_event(_step_started(2))
        display.handle_event(
            _make_event(
                "llm.response",
                step_index=2,
                stats={
                    "prompt_tokens": 200,
                    "generated_tokens": 80,
                    "cost_usd": 0.002,
                },
            )
        )
        output = _flush_output(display, buf)
        normalized = " ".join(output.split())
        assert "run 300 prompt /" in normalized
        assert "130 output / 430 total" in normalized


class TestOutcomeDisplay:
    def test_first_llm_request_prints_step_zero_beginning_before_step_output(
        self,
    ) -> None:
        display, buf = _build_display()
        display.handle_event(_step_started(1))
        display.handle_event(
            _make_event(
                "llm.request",
                step_index=1,
                data={
                    "request_index": 1,
                    "model": "openai/gpt-5.6-terra",
                    "messages": [
                        {"role": "system", "content": "Follow the contract exactly."},
                        {"role": "user", "content": "Solve the task from scratch."},
                    ],
                },
            )
        )
        display.handle_event(
            _make_event(
                "llm.response",
                step_index=1,
                data={
                    "response_text": "SUBMIT(answer='ok')",
                    "reasoning_text": "Need one short answer.",
                },
                stats={
                    "prompt_tokens": 100,
                    "generated_tokens": 50,
                },
            )
        )
        rendered = _flush_output(display, buf)
        assert "Step 0" in rendered
        assert "Beginning" in rendered
        assert "Initial Prompt" in rendered
        assert "Follow the contract exactly." in rendered
        assert "Solve the task from scratch." in rendered
        assert rendered.index("Step 0") < rendered.index("Step 1/10")

    def test_step_zero_is_printed_only_once(self) -> None:
        display, buf = _build_display()
        display.handle_event(_step_started(1))
        display.handle_event(
            _make_event(
                "llm.request",
                step_index=1,
                data={
                    "request_index": 1,
                    "messages": [{"role": "user", "content": "first prompt"}],
                },
            )
        )
        display.handle_event(
            _make_event(
                "llm.request",
                step_index=1,
                data={
                    "request_index": 2,
                    "messages": [{"role": "user", "content": "second prompt"}],
                },
            )
        )
        display.handle_event(
            _make_event(
                "llm.response",
                step_index=1,
                data={
                    "response_text": "SUBMIT(answer='ok')",
                },
                stats={
                    "prompt_tokens": 10,
                    "generated_tokens": 2,
                },
            )
        )

        rendered = _flush_output(display, buf)
        assert rendered.count("Step 0") == 1
        assert "first prompt" in rendered
        assert "second prompt" not in rendered

    def test_llm_reasoning_shows_reasoning_panel(self) -> None:
        display, buf = _build_display()
        display.handle_event(_step_started(1))
        display.handle_event(
            _make_event(
                "llm.response",
                step_index=1,
                data={
                    "response_text": "print(1 + 1)",
                    "reasoning_text": "Need to evaluate the expression before returning code.",
                },
                stats={
                    "prompt_tokens": 100,
                    "generated_tokens": 50,
                },
            )
        )
        output = _flush_output(display, buf)
        assert "Reasoning" in output
        assert "evaluate the expression" in output

    def test_repl_response_shows_result_panel(self) -> None:
        display, buf = _build_display()
        display.handle_event(_step_started(1))
        display.handle_event(
            _make_event(
                "llm.response",
                step_index=1,
                stats={
                    "prompt_tokens": 100,
                    "generated_tokens": 50,
                },
            )
        )
        display.handle_event(
            _make_event("repl.response", step_index=1, data={"output": "x" * 42})
        )
        output = _flush_output(display, buf)
        assert "Result (42 chars)" in output
        assert "xxxxxxxxxx" in output

    def test_repl_final_shows_value(self) -> None:
        display, buf = _build_display()
        display.handle_event(_step_started(1))
        display.handle_event(
            _make_event(
                "llm.response",
                step_index=1,
                stats={
                    "prompt_tokens": 100,
                    "generated_tokens": 50,
                },
            )
        )
        display.handle_event(
            _make_event(
                "repl.final",
                step_index=1,
                data={"final_outputs": {"answer": "answer42"}},
            )
        )
        output = _flush_output(display, buf)
        assert "Final Signal" in output
        assert "answer42" in output

    def test_error_shows_type(self) -> None:
        display, buf = _build_display()
        display.handle_event(_step_started(1))
        display.handle_event(
            _make_event(
                "llm.response",
                step_index=1,
                stats={
                    "prompt_tokens": 100,
                    "generated_tokens": 50,
                },
            )
        )
        display.handle_event(
            _make_event(
                "repl.error",
                step_index=1,
                data={
                    "error_type": "SyntaxError",
                    "error": "invalid syntax",
                },
            )
        )
        output = _flush_output(display, buf)
        assert "Error" in output
        assert "invalid syntax" in output

    def test_code_panel_shows_code(self) -> None:
        display, buf = _build_display()
        display.handle_event(_step_started(1))
        display.handle_event(
            _make_event(
                "llm.response",
                step_index=1,
                stats={
                    "prompt_tokens": 100,
                    "generated_tokens": 50,
                },
            )
        )
        display.handle_event(
            _make_event(
                "repl.request",
                step_index=1,
                data={
                    "code": "a = 1\nb = 2\nc = 3\n",
                },
            )
        )
        output = _flush_output(display, buf)
        assert "Python Code" in output
        assert "a = 1" in output
        assert "b = 2" in output

    def test_long_console_panels_are_not_truncated(self) -> None:
        display, buf = _build_display()
        reasoning = f"reasoning-start {'x' * 2600} reasoning-end"
        code = f"print('code-start')\n# {'c' * 2400}\nprint('code-end')"
        output_text = f"output-start {'y' * 2600} output-end"
        error = f"error-start {'z' * 2200} error-end"
        final_outputs = {"answer": f"final-start {'w' * 2200} final-end"}

        display.handle_event(_step_started(1))
        display.handle_event(
            _make_event(
                "llm.response",
                step_index=1,
                data={
                    "response_text": "print('hello')",
                    "reasoning_text": reasoning,
                },
                stats={
                    "prompt_tokens": 100,
                    "generated_tokens": 50,
                },
            )
        )
        display.handle_event(
            _make_event("repl.request", step_index=1, data={"code": code})
        )
        display.handle_event(
            _make_event("repl.response", step_index=1, data={"output": output_text})
        )
        display.handle_event(
            _make_event("repl.error", step_index=1, data={"error": error})
        )
        display.handle_event(
            _make_event(
                "repl.final", step_index=1, data={"final_outputs": final_outputs}
            )
        )

        rendered = _flush_output(display, buf)
        assert "reasoning-end" in rendered
        assert "code-end" in rendered
        assert "output-end" in rendered
        assert "error-end" in rendered
        assert "final-end" in rendered
        assert "chars truncated" not in rendered
        assert "...[+" not in rendered


class TestMissingData:
    def test_no_tokens(self) -> None:
        display, buf = _build_display()
        display.handle_event(_step_started(1))
        display.handle_event(_make_event("llm.response", step_index=1, stats={}))
        output = _flush_output(display, buf)
        assert "0 prompt / 0 output / 0 total" in output

    def test_no_cost_omitted(self) -> None:
        display, buf = _build_display()
        display.handle_event(_step_started(1))
        display.handle_event(
            _make_event(
                "llm.response",
                step_index=1,
                stats={
                    "prompt_tokens": 100,
                    "generated_tokens": 50,
                },
            )
        )
        output = _flush_output(display, buf)
        assert "$" not in output  # no cost shown

    def test_no_max_iterations(self) -> None:
        buf = StringIO()
        console = Console(file=buf, force_terminal=True, width=200)
        display = LiveStepDisplay(console=console)
        display.handle_event(_step_started(3))
        display.handle_event(
            _make_event(
                "llm.response",
                step_index=3,
                stats={
                    "prompt_tokens": 100,
                    "generated_tokens": 50,
                },
            )
        )
        display.handle_event(_make_event("run.finished"))
        output = buf.getvalue()
        assert "Step 3" in output
        assert "None" not in output


class TestNoOutputBeforeFirstStep:
    def test_run_started_produces_no_output(self) -> None:
        display, buf = _build_display()
        display.handle_event(_make_event("run.started"))
        assert buf.getvalue() == ""
