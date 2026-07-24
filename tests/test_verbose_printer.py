from __future__ import annotations

from rich.console import Console

from rlmbenchy.logger.verbose import VerbosePrinter
from rlmbenchy.rlm.types import LoopRunResult, StopReason


def _answer_outputs(value: object) -> dict[str, object]:
    return {"answer": value}


def test_verbose_printer_summary_does_not_truncate_long_values() -> None:
    printer = VerbosePrinter(enabled=True)
    printer.console = Console(
        record=True, width=200, force_terminal=False, no_color=True
    )
    final_outputs = f"answer-start {'X' * 500} answer-end"
    error = f"error-start {'Y' * 500} error-end"

    printer.print_summary(
        LoopRunResult(
            stop_reason=StopReason.SUCCESS,
            iterations=3,
            final_outputs=_answer_outputs(final_outputs),
            error=error,
        )
    )

    rendered = printer.console.export_text()
    assert "answer-start" in rendered
    assert "answer-end" in rendered
    assert "error-start" in rendered
    assert "error-end" in rendered
    assert rendered.count("X") >= 500
    assert rendered.count("Y") >= 500
    assert "...[+" not in rendered


def test_verbose_printer_batch_summary_shows_price_tokens_and_throughput() -> None:
    printer = VerbosePrinter(enabled=True)
    printer.console = Console(
        record=True, width=160, force_terminal=False, no_color=True
    )

    printer.print_batch_summary(
        {
            "workload": "tasks_v0",
            "batch_id": "15869827",
            "summary": {
                "n_tasks": 2,
                "finalized_count": 1,
                "finalization_rate": 0.5,
                "tasks_with_exec_error": 1,
                "correctness_rate": None,
                "elapsed_s": 4.0,
            },
            "usage_summary": {
                "prompt_tokens": 1200,
                "generated_tokens": 300,
                "total_tokens": 1500,
                "coverage": {
                    "total_lm_responses": 2,
                    "token_usage_responses": 2,
                    "prompt_tokens_known_responses": 2,
                    "generated_tokens_known_responses": 2,
                    "complete_token_usage_responses": 2,
                    "prompt_tokens_complete": True,
                    "generated_tokens_complete": True,
                    "total_tokens_complete": True,
                },
            },
            "pricing_summary": {
                "total_cost_usd": 0.12345678,
            },
            "performance_summary": {
                "tokens_per_second": {
                    "total_tokens_per_s": 375.0,
                }
            },
            "batch_report": "/tmp/batch.json",
            "task_logs": ["/tmp/task1.jsonl"],
        }
    )

    rendered = printer.console.export_text()
    assert "Batch Summary" in rendered
    assert "price" in rendered
    assert "$0.12345678" in rendered
    assert "total_tokens" in rendered
    assert "1,500" in rendered
    assert "avg_tokens_per_s" in rendered
    assert "375.00" in rendered


def test_verbose_printer_batch_summary_marks_partial_token_telemetry() -> None:
    printer = VerbosePrinter(enabled=True)
    printer.console = Console(
        record=True, width=160, force_terminal=False, no_color=True
    )

    printer.print_batch_summary(
        {
            "workload": "tasks_v0",
            "batch_id": "15869827",
            "summary": {
                "n_tasks": 2,
                "finalized_count": 1,
                "finalization_rate": 0.5,
                "tasks_with_exec_error": 1,
                "correctness_rate": None,
                "elapsed_s": 4.0,
            },
            "usage_summary": {
                "prompt_tokens": 1200,
                "generated_tokens": 0,
                "total_tokens": 1200,
                "coverage": {
                    "total_lm_responses": 2,
                    "token_usage_responses": 2,
                    "prompt_tokens_known_responses": 2,
                    "generated_tokens_known_responses": 1,
                    "complete_token_usage_responses": 1,
                    "prompt_tokens_complete": True,
                    "generated_tokens_complete": False,
                    "total_tokens_complete": False,
                },
            },
            "pricing_summary": {
                "total_cost_usd": 0.12345678,
            },
            "performance_summary": {
                "tokens_per_second": {
                    "prompt_tokens_per_s": 300.0,
                    "generated_tokens_per_s": None,
                    "total_tokens_per_s": None,
                }
            },
            "batch_report": "/tmp/batch.json",
            "task_logs": ["/tmp/task1.jsonl"],
        }
    )

    rendered = printer.console.export_text()
    assert "avg_tokens_per_s" in rendered
    assert "n/a (partial telemetry)" in rendered
