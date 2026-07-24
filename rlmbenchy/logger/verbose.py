"""Rich verbose console printer for minimal RLM."""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.style import Style
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from rlmbenchy.rlm.types import LoopRunResult, StopReason

COLORS = {
    "primary": "#7AA2F7",
    "secondary": "#BB9AF7",
    "success": "#9ECE6A",
    "warning": "#E0AF68",
    "error": "#F7768E",
    "text": "#A9B1D6",
    "muted": "#565F89",
    "accent": "#7DCFFF",
    "border": "#3B4261",
}


STYLE_PRIMARY = Style(color=COLORS["primary"], bold=True)
STYLE_SECONDARY = Style(color=COLORS["secondary"])
STYLE_SUCCESS = Style(color=COLORS["success"])
STYLE_WARNING = Style(color=COLORS["warning"])
STYLE_ERROR = Style(color=COLORS["error"])
STYLE_TEXT = Style(color=COLORS["text"])
STYLE_MUTED = Style(color=COLORS["muted"])
STYLE_ACCENT = Style(color=COLORS["accent"], bold=True)


def _snippet(text: Any) -> str:
    return str(text or "").strip()


def _preview_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(value)


def _format_integer(value: Any) -> str:
    if isinstance(value, bool):
        return "n/a"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{int(value):,}"
    return "n/a"


def _format_rate(value: Any) -> str:
    if isinstance(value, bool):
        return "n/a"
    if isinstance(value, (int, float)):
        return f"{float(value):,.2f}"
    return "n/a"


def _format_usd(value: Any) -> str:
    if isinstance(value, bool):
        return "n/a"
    if not isinstance(value, (int, float)):
        return "n/a"
    formatted = f"{float(value):,.8f}".rstrip("0").rstrip(".")
    return f"${formatted}"


def _render_message_content(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    parts.append(text)
                continue
            if not isinstance(item, dict):
                try:
                    parts.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
                except Exception:
                    parts.append(str(item))
                continue
            item_type = str(item.get("type") or "").strip()
            for key in ("text", "content", "input_text", "output_text"):
                text_value = item.get(key)
                if isinstance(text_value, str) and text_value.strip():
                    parts.append(text_value.strip())
                    break
            else:
                try:
                    rendered = json.dumps(item, ensure_ascii=False, sort_keys=True)
                except Exception:
                    rendered = str(item)
                if item_type:
                    parts.append(f"[{item_type}] {rendered}")
                else:
                    parts.append(rendered)
        return "\n".join(part for part in parts if part)
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception:
        return str(value)


class VerbosePrinter:
    """Rich console output for RLM metadata and iteration traces."""

    def __init__(
        self,
        enabled: bool = True,
        *,
        console: Console | None = None,
    ) -> None:
        self.enabled = enabled
        self.console = (console or Console()) if enabled else None

    def print_metadata(self, metadata: dict[str, Any]) -> None:
        console = self.console
        if console is None:
            return

        title = Text()
        title.append("◆ ", style=STYLE_ACCENT)
        title.append("RLMBenchy Run", style=STYLE_PRIMARY)

        table = Table(show_header=False, show_edge=False, box=None, padding=(0, 2))
        table.add_column("key", style=STYLE_MUTED, width=18, overflow="fold")
        table.add_column("value", style=STYLE_TEXT, overflow="fold")

        nested_config = metadata.get("config") or {}
        repl_config = nested_config.get("repl") or {}
        rows = [
            ("workload", metadata.get("workload")),
            ("task_id", metadata.get("task_id")),
            (
                "task",
                (
                    f"{metadata.get('task_index')}/{metadata.get('task_total')}"
                    if metadata.get("task_index") and metadata.get("task_total")
                    else None
                ),
            ),
            ("batch_id", metadata.get("batch_id")),
            ("run_config", metadata.get("run_config_name")),
            ("lm_profile", metadata.get("lm_profile_name")),
            ("sub_lm_profile", metadata.get("sub_lm_profile_name")),
            ("model", metadata.get("model_id")),
            ("sub_model", metadata.get("sub_model_id")),
            ("api_base", metadata.get("api_base")),
            ("sub_api_base", metadata.get("sub_api_base")),
            ("seed", nested_config.get("seed")),
            ("repl_backend", repl_config.get("backend")),
            ("max_iterations", nested_config.get("max_iterations")),
            ("max_llm_calls", nested_config.get("max_llm_calls")),
        ]
        for key, value in rows:
            if value is None:
                continue
            table.add_row(str(key), str(value))

        panel = Panel(
            table,
            title=title,
            title_align="left",
            border_style=COLORS["border"],
            padding=(1, 2),
        )
        console.print()
        console.print(panel)
        console.print()

    def print_initial_prompt(
        self,
        *,
        prompt: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        model: str | None = None,
    ) -> None:
        console = self.console
        if console is None:
            return

        header = Text()
        header.append("Step 0", style=STYLE_PRIMARY)
        header.append("  ", style=STYLE_TEXT)
        header.append("Beginning", style=STYLE_SECONDARY)
        if model:
            header.append("  ", style=STYLE_TEXT)
            header.append(str(model), style=STYLE_MUTED)
        console.print(Rule(header, style=COLORS["border"], characters="─"))

        body_lines: list[Text] = []
        prompt_text = str(prompt or "").strip()
        if prompt_text:
            body_lines.append(Text(prompt_text, style=STYLE_TEXT))
        elif isinstance(messages, list):
            for index, message in enumerate(messages, start=1):
                if not isinstance(message, dict):
                    continue
                role = (
                    str(message.get("role") or f"message_{index}").strip()
                    or f"message_{index}"
                )
                content_text = _render_message_content(message.get("content"))
                if not content_text:
                    continue
                if body_lines:
                    body_lines.append(Text(""))
                body_lines.append(Text(f"{role}", style=STYLE_MUTED))
                body_lines.append(Text(content_text, style=STYLE_TEXT))

        if not body_lines:
            body_lines.append(Text("(prompt unavailable)", style=STYLE_MUTED))

        console.print(
            Panel(
                Group(*body_lines),
                title=Text("Initial Prompt", style=STYLE_MUTED),
                title_align="left",
                border_style=COLORS["accent"],
                padding=(0, 1),
            )
        )
        console.print()

    def print_live_step(self, step: dict[str, Any]) -> None:
        console = self.console
        if console is None:
            return

        iteration = str(step.get("iteration") or 0)
        task_index = step.get("task_index")
        task_total = step.get("task_total")
        duration_ms = int(step.get("duration_ms") or 0)
        llm_calls = int(step.get("llm_calls") or 0)
        subcalls = list(step.get("subcalls") or [])
        prompt_tokens = int(step.get("prompt_tokens") or 0)
        generated_tokens = int(step.get("generated_tokens") or 0)
        total_tokens = int(
            step.get("total_tokens") or (prompt_tokens + generated_tokens)
        )
        run_prompt_tokens = int(step.get("run_prompt_tokens") or 0)
        run_generated_tokens = int(step.get("run_generated_tokens") or 0)
        run_total_tokens = int(
            step.get("run_total_tokens") or (run_prompt_tokens + run_generated_tokens)
        )
        step_cost_usd = step.get("step_cost_usd")
        run_cost_usd = step.get("run_cost_usd")
        raw_response = str(step.get("raw_response") or "").strip()

        header = Text()
        if task_index and task_total:
            header.append(f"Task {task_index}/{task_total}", style=STYLE_SECONDARY)
            header.append("  ", style=STYLE_TEXT)
        header.append(f"Step {iteration}", style=STYLE_PRIMARY)
        if duration_ms > 0:
            header.append("  ", style=STYLE_TEXT)
            header.append(f"{duration_ms / 1000:.1f}s", style=STYLE_MUTED)
        if llm_calls > 0:
            header.append("  ", style=STYLE_TEXT)
            header.append(f"{llm_calls} lm call(s)", style=STYLE_ACCENT)
        if subcalls:
            header.append("  ", style=STYLE_TEXT)
            header.append(f"{len(subcalls)} subcall(s)", style=STYLE_WARNING)

        console.print(Rule(header, style=COLORS["border"], characters="─"))

        reasoning = str(step.get("reasoning") or "").strip()
        if reasoning:
            console.print(
                Panel(
                    Text(_snippet(reasoning), style=STYLE_TEXT),
                    title=Text("Reasoning", style=STYLE_MUTED),
                    title_align="left",
                    border_style=COLORS["secondary"],
                    padding=(0, 1),
                )
            )

        code = str(step.get("code") or "").strip()
        if code:
            console.print(
                Panel(
                    Syntax(
                        _snippet(code),
                        "python",
                        theme="monokai",
                        line_numbers=True,
                    ),
                    title=Text("Python Code", style=STYLE_MUTED),
                    title_align="left",
                    border_style=COLORS["primary"],
                    padding=(0, 1),
                )
            )
        elif raw_response:
            console.print(
                Panel(
                    Text(_snippet(raw_response), style=STYLE_TEXT),
                    title=Text("Model Response", style=STYLE_MUTED),
                    title_align="left",
                    border_style=COLORS["muted"],
                    padding=(0, 1),
                )
            )

        output = str(step.get("output") or "").strip()
        if output:
            console.print(
                Panel(
                    Text(_snippet(output), style=STYLE_TEXT),
                    title=Text(f"Result ({len(output):,} chars)", style=STYLE_MUTED),
                    title_align="left",
                    border_style=COLORS["success"],
                    padding=(0, 1),
                )
            )

        error = str(step.get("error") or "").strip()
        if error:
            console.print(
                Panel(
                    Text(_snippet(error), style=STYLE_ERROR),
                    title=Text("Error", style=STYLE_MUTED),
                    title_align="left",
                    border_style=COLORS["error"],
                    padding=(0, 1),
                )
            )

        final_outputs = step.get("final_outputs")
        if final_outputs is not None:
            console.print(
                Panel(
                    Text(_preview_value(final_outputs), style=STYLE_WARNING),
                    title=Text("Final Signal", style=STYLE_MUTED),
                    title_align="left",
                    border_style=COLORS["warning"],
                    padding=(0, 1),
                )
            )

        if subcalls:
            subcall_lines: list[Text] = []
            for item in subcalls:
                kind = str(item.get("kind") or "tool")
                name = str(item.get("name") or "<unknown>")
                duration = item.get("duration_ms")
                success = bool(item.get("success"))
                prefix = "↳ llm_query" if kind == "llm_query" else f"↳ {name}"
                line = Text(
                    prefix,
                    style=STYLE_SECONDARY if kind == "llm_query" else STYLE_ACCENT,
                )
                if duration is not None:
                    line.append(f"  {duration}ms", style=STYLE_MUTED)
                if not success:
                    line.append("  error", style=STYLE_ERROR)
                subcall_lines.append(line)
                request_preview = str(item.get("request_preview") or "").strip()
                if request_preview:
                    subcall_lines.append(
                        Text(f"  prompt: {_snippet(request_preview)}", style=STYLE_TEXT)
                    )
                response_preview = str(item.get("response_preview") or "").strip()
                if response_preview:
                    preview_style = STYLE_WARNING if not success else STYLE_TEXT
                    subcall_lines.append(
                        Text(
                            f"  result: {_snippet(response_preview)}",
                            style=preview_style,
                        )
                    )
            console.print(
                Panel(
                    Group(*subcall_lines),
                    title=Text("Subcalls", style=STYLE_MUTED),
                    title_align="left",
                    border_style=COLORS["secondary"],
                    padding=(0, 1),
                )
            )

        usage = Text(style=STYLE_TEXT)
        usage.append("step  ", style=STYLE_MUTED)
        usage.append(
            f"{prompt_tokens:,} prompt / {generated_tokens:,} output / {total_tokens:,} total",
            style=STYLE_ACCENT,
        )
        if isinstance(step_cost_usd, (int, float)) and float(step_cost_usd) > 0:
            usage.append("  |  ", style=STYLE_MUTED)
            usage.append(_format_usd(step_cost_usd), style=STYLE_TEXT)
        usage.append("  |  ", style=STYLE_MUTED)
        usage.append("run  ", style=STYLE_MUTED)
        usage.append(
            f"{run_prompt_tokens:,} prompt / {run_generated_tokens:,} output / {run_total_tokens:,} total",
            style=STYLE_TEXT,
        )
        if isinstance(run_cost_usd, (int, float)) and float(run_cost_usd) > 0:
            usage.append("  |  ", style=STYLE_MUTED)
            usage.append(_format_usd(run_cost_usd), style=STYLE_TEXT)
        console.print(
            Panel(
                usage,
                title=Text("Usage", style=STYLE_MUTED),
                title_align="left",
                border_style=COLORS["accent"],
                padding=(0, 1),
            )
        )
        console.print()

    def print_batch_summary(self, payload: dict[str, Any]) -> None:
        console = self.console
        if console is None:
            return

        summary = dict(payload.get("summary") or {})
        usage_summary = dict(payload.get("usage_summary") or {})
        usage_coverage = dict(usage_summary.get("coverage") or {})
        pricing_summary = dict(payload.get("pricing_summary") or {})
        performance_summary = dict(payload.get("performance_summary") or {})
        throughput = dict(performance_summary.get("tokens_per_second") or {})
        avg_tokens_per_s = _format_rate(throughput.get("total_tokens_per_s"))
        if (
            throughput.get("total_tokens_per_s") is None
            and usage_coverage
            and usage_coverage.get("total_tokens_complete") is False
        ):
            avg_tokens_per_s = "n/a (partial telemetry)"
        table = Table(show_header=False, show_edge=False, box=None, padding=(0, 2))
        table.add_column("key", style=STYLE_MUTED, overflow="fold")
        table.add_column("value", style=STYLE_TEXT, overflow="fold")

        rows = [
            ("workload", payload.get("workload")),
            ("batch_id", payload.get("batch_id")),
            ("tasks", summary.get("n_tasks")),
            (
                "finalization",
                (
                    f"{summary.get('finalized_count', 0)}/{summary.get('n_tasks', 0)} "
                    f"({float(summary.get('finalization_rate', 0.0)):.1%})"
                    if summary.get("n_tasks") is not None
                    else None
                ),
            ),
            ("exec_errors", summary.get("tasks_with_exec_error")),
            (
                "correctness",
                (
                    "not_scored"
                    if summary.get("correctness_rate") is None
                    else (
                        f"{summary.get('correct_count', 0)}/{summary.get('scored_count', 0)} "
                        f"({float(summary.get('correctness_rate', 0.0)):.1%})"
                    )
                ),
            ),
            ("price", _format_usd(pricing_summary.get("total_cost_usd"))),
            ("total_tokens", _format_integer(usage_summary.get("total_tokens"))),
            ("avg_tokens_per_s", avg_tokens_per_s),
            ("elapsed_s", summary.get("elapsed_s")),
            ("batch_report", payload.get("batch_report")),
        ]
        for key, value in rows:
            if value is None:
                continue
            table.add_row(str(key), str(value))

        log_paths = list(payload.get("task_logs") or [])
        if log_paths:
            preview_paths = log_paths[:5]
            for index, path in enumerate(preview_paths, start=1):
                table.add_row(f"task_log_{index}", str(path))
            if len(log_paths) > len(preview_paths):
                table.add_row(
                    "more_logs", f"+{len(log_paths) - len(preview_paths)} more"
                )

        title = Text()
        title.append("◆ ", style=STYLE_ACCENT)
        title.append("Batch Summary", style=STYLE_PRIMARY)

        console.print()
        console.print(
            Panel(
                table,
                title=title,
                title_align="left",
                border_style=COLORS["border"],
                padding=(1, 2),
            )
        )
        console.print()

    def print_summary(self, result: LoopRunResult) -> None:
        console = self.console
        if console is None:
            return

        reason = result.stop_reason
        style = STYLE_SUCCESS if reason == StopReason.SUCCESS else STYLE_WARNING

        table = Table(show_header=False, show_edge=False, box=None, padding=(0, 2))
        table.add_column("key", style=STYLE_MUTED, overflow="fold")
        table.add_column("value", style=STYLE_TEXT, overflow="fold")
        table.add_row("stop_reason", Text(reason.value, style=style))
        table.add_row("iterations", str(result.iterations))
        table.add_row("final_outputs", _snippet(str(result.final_outputs or "")))
        if result.error:
            table.add_row("error", _snippet(result.error))

        console.print()
        console.print(Rule(style=COLORS["border"], characters="═"))
        console.print(table, justify="center")
        console.print(Rule(style=COLORS["border"], characters="═"))
        console.print()
