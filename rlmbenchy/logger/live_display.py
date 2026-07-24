"""Rich per-step console output driven by RLMLogger telemetry events."""

from __future__ import annotations

import time
from typing import Any

from rich.console import Console

from rlmbenchy.logger.otel import domain_events_from_otel_records, is_otel_record
from rlmbenchy.logger.verbose import VerbosePrinter


class LiveStepDisplay:
    """Observes structured telemetry events and prints rich per-step panels."""

    def __init__(
        self,
        *,
        max_iterations: int | None = None,
        console: Console | None = None,
    ) -> None:
        self._max_iter = max_iterations
        self._console = console or Console()
        self._printer = VerbosePrinter(enabled=True, console=self._console)

        self._current_step: int | None = None
        self._step_start: float | None = None

        # Per-step accumulators
        self._step_prompt_tok = 0
        self._step_gen_tok = 0
        self._step_cost = 0.0
        self._step_llm_calls = 0
        self._step_duration_ms: int | None = None
        self._step_reasoning: str = ""
        self._step_code: str = ""
        self._step_output: str = ""
        self._step_error: str = ""
        self._step_raw_response: str = ""
        self._step_final_outputs: Any = None

        # Run accumulators
        self._run_prompt_tok = 0
        self._run_gen_tok = 0
        self._run_cost = 0.0
        self._printed_initial_prompt = False

    # ------------------------------------------------------------------
    # Public entry point — set as logger.on_event
    # ------------------------------------------------------------------

    def handle_event(self, entry: dict[str, Any]) -> None:
        if is_otel_record(entry):
            if entry.get("record_type") != "log":
                return
            for domain_event in domain_events_from_otel_records([entry]):
                self.handle_event(domain_event)
            return
        if "event_type" not in entry:
            return

        event_type = str(entry.get("event_type") or "")

        if event_type == "step.started":
            # Explicit step boundary from the RLM loop.
            if self._current_step is not None:
                self._flush()
            self._current_step = entry.get("step_index")
            self._step_start = time.monotonic()
            self._step_prompt_tok = 0
            self._step_gen_tok = 0
            self._step_cost = 0.0
            self._step_llm_calls = 0
            self._step_duration_ms = None
            self._step_reasoning = ""
            self._step_code = ""
            self._step_output = ""
            self._step_error = ""
            self._step_raw_response = ""
            self._step_final_outputs = None
            return

        if event_type == "step.finished":
            stats = entry.get("stats") or {}
            elapsed_ms = stats.get("elapsed_ms")
            if isinstance(elapsed_ms, (int, float)):
                self._step_duration_ms = int(elapsed_ms)
            self._flush()
            return

        if event_type == "llm.request":
            self._on_llm_request(entry)
        elif event_type in ("llm.response", "subllm.response"):
            self._on_llm_response(entry)
        elif event_type == "repl.request":
            self._on_repl_request(entry)
        elif event_type == "repl.response":
            self._on_repl_response(entry)
        elif event_type == "repl.final":
            self._on_repl_final(entry)
        elif event_type in ("repl.error", "llm.error", "subllm.error"):
            self._on_error(entry)
        elif event_type == "run.finished":
            # Flush any trailing step that didn't get a step.finished.
            self._flush()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_llm_request(self, entry: dict[str, Any]) -> None:
        if self._printed_initial_prompt:
            return
        data = entry.get("data") or {}
        request_index = data.get("request_index")
        if request_index not in (1, "1"):
            return
        messages = data.get("messages")
        safe_messages = messages if isinstance(messages, list) else None
        self._printer.print_initial_prompt(
            prompt=str(data.get("prompt") or "").strip() or None,
            messages=safe_messages,
            model=str(data.get("model") or "").strip() or None,
        )
        self._printed_initial_prompt = True

    def _on_llm_response(self, entry: dict[str, Any]) -> None:
        data = entry.get("data") or {}
        stats = entry.get("stats") or {}
        pt = stats.get("prompt_tokens")
        gt = stats.get("generated_tokens")
        cost = stats.get("cost_usd")
        self._step_llm_calls += 1
        response_text = str(data.get("response_text") or "").strip()
        if response_text:
            self._step_raw_response = response_text
        reasoning_text = str(data.get("reasoning_text") or "").strip()
        if not reasoning_text:
            response_message = data.get("response_message")
            if isinstance(response_message, dict):
                reasoning_text = str(
                    response_message.get("reasoning_content")
                    or response_message.get("reasoning")
                    or response_message.get("reasoning_text")
                    or ""
                ).strip()
        if reasoning_text:
            self._step_reasoning = reasoning_text
        if isinstance(pt, (int, float)):
            self._step_prompt_tok += int(pt)
            self._run_prompt_tok += int(pt)
        if isinstance(gt, (int, float)):
            self._step_gen_tok += int(gt)
            self._run_gen_tok += int(gt)
        if isinstance(cost, (int, float)):
            self._step_cost += float(cost)
            self._run_cost += float(cost)

    def _on_repl_request(self, entry: dict[str, Any]) -> None:
        code = str((entry.get("data") or {}).get("code") or "")
        self._step_code = code.strip()

    def _on_repl_response(self, entry: dict[str, Any]) -> None:
        self._step_output = str((entry.get("data") or {}).get("output") or "").strip()

    def _on_repl_final(self, entry: dict[str, Any]) -> None:
        self._step_final_outputs = (entry.get("data") or {}).get("final_outputs")

    def _on_error(self, entry: dict[str, Any]) -> None:
        data = entry.get("data") or {}
        self._step_error = str(
            data.get("error")
            or data.get("error_message")
            or data.get("error_type")
            or "error"
        ).strip()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _flush(self) -> None:
        if self._current_step is None:
            return

        duration_ms = self._step_duration_ms
        if duration_ms is None and self._step_start is not None:
            duration_ms = int((time.monotonic() - self._step_start) * 1000)

        iteration = str(self._current_step)
        if self._max_iter:
            iteration = f"{self._current_step}/{self._max_iter}"

        self._printer.print_live_step(
            {
                "iteration": iteration,
                "duration_ms": duration_ms or 0,
                "llm_calls": self._step_llm_calls,
                "prompt_tokens": self._step_prompt_tok,
                "generated_tokens": self._step_gen_tok,
                "total_tokens": self._step_prompt_tok + self._step_gen_tok,
                "run_prompt_tokens": self._run_prompt_tok,
                "run_generated_tokens": self._run_gen_tok,
                "run_total_tokens": self._run_prompt_tok + self._run_gen_tok,
                "step_cost_usd": self._step_cost,
                "run_cost_usd": self._run_cost,
                "raw_response": self._step_raw_response,
                "reasoning": self._step_reasoning,
                "code": self._step_code,
                "output": self._step_output,
                "error": self._step_error,
                "final_outputs": self._step_final_outputs,
            }
        )

        # Reset step (keep run accumulators)
        self._current_step = None
        self._step_start = None
