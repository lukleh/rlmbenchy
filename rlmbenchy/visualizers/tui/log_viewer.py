"""Terminal UI log viewer for ``rlmbenchy`` RLM runs.

Usage:
    uv run python -m rlmbenchy.visualizers.tui

Keys:
    Up/Down: select step
    [/]: previous/next run
    j/k: scroll narrative up/down
    R: reload the current run
    q: quit
"""

from __future__ import annotations

import argparse
import curses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rlmbenchy.logger.api import build_run_index, load_run
from rlmbenchy.runtime_paths import resolve_runtime_paths

DEFAULT_LOG_DIR = resolve_runtime_paths().rlm_log_dir


def wrap_lines(text: Any, width: int) -> list[str]:
    content = str(text or "")
    if width <= 1:
        return [content]
    lines: list[str] = []
    for raw in content.splitlines() or [""]:
        if not raw:
            lines.append("")
            continue
        start = 0
        while start < len(raw):
            lines.append(raw[start : start + width])
            start += width
    return lines or [""]


def _format_count(value: Any) -> str:
    if isinstance(value, bool):
        return "n/a"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{int(value):,}"
    return "n/a"


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def load_runs(
    log_dir: Path,
    limit: int = 50,
) -> list[dict[str, Any]]:
    return build_run_index(log_dir=log_dir, limit=limit)


def load_run_payload(
    log_dir: Path,
    run_row: dict[str, Any],
) -> dict[str, Any]:
    log_name = str(run_row.get("log_file") or "").strip()
    log_path = (log_dir / log_name).resolve()
    return load_run(log_path)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass
class ViewerState:
    runs: list[dict[str, Any]]
    run_index: int = 0
    run_cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    current: dict[str, Any] | None = None
    step_index: int = 0
    step_list_scroll: int = 0
    narrative_scroll: int = 0

    def tasks(self) -> list[dict[str, Any]]:
        if self.current is None:
            return []
        items = self.current.get("tasks", [])
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
        return []

    def steps(self) -> list[dict[str, Any]]:
        if self.current is None:
            return []
        items = self.current.get("all_steps", [])
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
        return []

    def selected_step(self) -> dict[str, Any] | None:
        steps = self.steps()
        if not steps:
            return None
        idx = max(0, min(self.step_index, len(steps) - 1))
        return steps[idx]


def activate_run(state: ViewerState, log_dir: Path, index: int) -> None:
    if not state.runs:
        state.current = None
        return
    state.run_index = max(0, min(index, len(state.runs) - 1))
    run_row = state.runs[state.run_index]
    key = str(run_row.get("log_file") or "")
    if key not in state.run_cache:
        state.run_cache[key] = load_run_payload(log_dir, run_row)
    state.current = state.run_cache[key]
    state.step_index = 0
    state.step_list_scroll = 0
    state.narrative_scroll = 0


def refresh_current_run(state: ViewerState, log_dir: Path) -> None:
    if not state.runs:
        state.current = None
        return
    state.run_index = max(0, min(state.run_index, len(state.runs) - 1))
    run_row = state.runs[state.run_index]
    key = str(run_row.get("log_file") or "")
    state.run_cache[key] = load_run_payload(log_dir, run_row)
    state.current = state.run_cache[key]
    steps = state.steps()
    if not steps:
        state.step_index = 0
        state.step_list_scroll = 0
        state.narrative_scroll = 0
        return
    state.step_index = max(0, min(state.step_index, len(steps) - 1))


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------


def _draw_border_box(win: Any, title: str) -> None:
    win.box()
    if title:
        max_x = win.getmaxyx()[1] - 2
        label = f" {title} "
        if len(label) > max_x:
            label = label[:max_x]
        try:
            win.addstr(0, 2, label)
        except curses.error:
            pass


def _draw_text_lines(
    win: Any,
    lines: list[str],
    *,
    start_line: int,
    color: int,
    pad_left: int = 1,
) -> None:
    h, w = win.getmaxyx()
    visible_h = max(0, h - 2)
    width = max(1, w - (pad_left + 1))
    end = min(len(lines), start_line + visible_h)
    row = 1
    for line in lines[start_line:end]:
        try:
            win.addstr(row, pad_left, line[:width], color)
        except curses.error:
            pass
        row += 1


_STATUS_COLOR_PAIR = {"error": 3, "final": 2}
_STATUS_LABEL = {"error": "ERR", "final": "FIN"}


def _status_color(step: dict[str, Any]) -> int:
    return _STATUS_COLOR_PAIR.get(str(step.get("status") or ""), 1)


def _step_status_label(step: dict[str, Any]) -> str:
    return _STATUS_LABEL.get(str(step.get("status") or ""), " - ")


_SECTION_COLOR_PAIR = {
    "text": 1,
    "error": 3,
    "final": 2,
    "call_summary": 4,
}


def _summary_lines(state: ViewerState) -> list[str]:
    run = state.current or {}
    summary = run.get("summary", {}) if isinstance(run, dict) else {}
    if not isinstance(summary, dict):
        summary = {}
    usage = summary.get("usage_summary", {})
    if not isinstance(usage, dict):
        usage = {}
    activity = summary.get("activity_summary", {})
    if not isinstance(activity, dict):
        activity = {}

    n_steps = len(state.steps())
    line1 = (
        f"run {state.run_index + 1}/{len(state.runs)} "
        f"[{run.get('log_file', '-')}]  "
        f"status={summary.get('status', '-')}"
    )
    elapsed_s = float(summary.get("elapsed_ms", 0) or 0) / 1000.0
    line2 = (
        f"final={summary.get('finalized_count', 0)}/{summary.get('n_tasks', 0)} "
        f"steps={n_steps} "
        f"llm={int(activity.get('llm_calls') or 0)} "
        f"tools={int(activity.get('tool_calls') or 0)} "
        f"sub={int(activity.get('subllm_calls') or 0)} "
        f"tokens={_format_count(usage.get('total_tokens', 0))} "
        f"elapsed={elapsed_s:.1f}s"
    )
    return [line1, line2]


def _draw_summary(
    stdscr: Any, state: ViewerState, top: int, left: int, width: int
) -> None:
    max_w = max(1, width - 2)
    for idx, text in enumerate(_summary_lines(state)):
        try:
            stdscr.addstr(top + idx, left, text[:max_w], curses.color_pair(4))
        except curses.error:
            pass


def _draw_step_list(
    stdscr: Any,
    state: ViewerState,
    top: int,
    left: int,
    width: int,
    height: int,
) -> None:
    win = stdscr.derwin(height, width, top, left)
    _draw_border_box(win, "Steps")

    steps = state.steps()
    if not steps:
        _draw_text_lines(
            win,
            ["No steps in this run."],
            start_line=0,
            color=curses.color_pair(4),
        )
        return

    visible = max(1, height - 2)
    if state.step_index < state.step_list_scroll:
        state.step_list_scroll = state.step_index
    if state.step_index >= state.step_list_scroll + visible:
        state.step_list_scroll = state.step_index - visible + 1

    inner_w = max(1, width - 2)
    start = state.step_list_scroll
    end = min(len(steps), start + visible)

    for row_idx, idx in enumerate(range(start, end), start=1):
        step = steps[idx]
        marker = ">" if idx == state.step_index else " "
        si = step.get("step_index")
        si_label = f"{int(si)}" if isinstance(si, int) else "?"
        status = _step_status_label(step)
        ms = int(step.get("latency_ms") or 0)
        ms_text = f"{ms}ms" if ms > 0 else ""
        text = f"{marker}{si_label:>2} {status} {ms_text}"

        color = curses.color_pair(_status_color(step))
        if idx == state.step_index:
            color |= curses.A_REVERSE
        try:
            win.addstr(row_idx, 1, text[:inner_w], color)
        except curses.error:
            pass


def _narrative_lines(step: dict[str, Any], width: int) -> list[tuple[str, int]]:
    """Flatten narrative sections into (line, color_pair) tuples."""
    sections = step.get("narrative_sections")
    if not isinstance(sections, list) or not sections:
        return [("(no step data)", 4)]
    out: list[tuple[str, int]] = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        label = str(section.get("label") or "").strip()
        kind = str(section.get("kind") or "text")
        content = str(section.get("content") or "")
        color = _SECTION_COLOR_PAIR.get(kind, 1)
        if kind == "call_summary":
            out.append((f"[{label}: {content}]", color))
            out.append(("", 1))
            continue
        if label:
            out.append((f"── {label} ──", 4))
        for wrapped in wrap_lines(content, width):
            out.append((wrapped, color))
        out.append(("", 1))
    return out


def _draw_narrative(
    stdscr: Any,
    state: ViewerState,
    top: int,
    left: int,
    width: int,
    height: int,
) -> None:
    win = stdscr.derwin(height, width, top, left)
    step = state.selected_step()
    if step is None:
        _draw_border_box(win, "Narrative")
        _draw_text_lines(
            win,
            ["Select a step to view its details."],
            start_line=0,
            color=curses.color_pair(4),
        )
        return

    si = step.get("step_index")
    si_label = f"Step {int(si)}" if isinstance(si, int) else "Task"
    inner_w = max(1, width - 2)
    lines = _narrative_lines(step, inner_w)
    scroll_pos = f"{state.narrative_scroll + 1}/{len(lines)}" if lines else ""
    title = f"{si_label}  {scroll_pos}"

    _draw_border_box(win, title)

    h, _ = win.getmaxyx()
    visible_h = max(0, h - 2)
    start = state.narrative_scroll
    end = min(len(lines), start + visible_h)
    for row_idx, (line, pair) in enumerate(lines[start:end], start=1):
        try:
            win.addstr(row_idx, 1, line[:inner_w], curses.color_pair(pair))
        except curses.error:
            pass

    remaining = max(0, len(lines) - state.narrative_scroll - visible_h)
    if remaining > 0:
        footer = f" +{remaining} lines (j/k) "
        w = win.getmaxyx()[1]
        try:
            win.addstr(
                h - 1,
                max(2, w - len(footer) - 2),
                footer[: w - 3],
                curses.color_pair(4),
            )
        except curses.error:
            pass


def _draw_footer(stdscr: Any, y: int, width: int) -> None:
    help_text = "Up/Down:step  [/]:run  j/k:scroll narrative  R:reload  q:quit"
    try:
        stdscr.addstr(y, 1, help_text[: max(1, width - 2)], curses.color_pair(4))
    except curses.error:
        pass


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def _run_loop(
    stdscr: Any,
    state: ViewerState,
    log_dir: Path,
) -> None:
    curses.curs_set(0)
    stdscr.nodelay(False)
    stdscr.keypad(True)

    if curses.has_colors():
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_WHITE, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_RED, -1)
        curses.init_pair(4, curses.COLOR_CYAN, -1)

    while True:
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        if height < 12 or width < 60:
            msg = "Terminal too small. Need at least 60x12."
            stdscr.addstr(0, 0, msg[: max(1, width - 1)])
            stdscr.refresh()
            key = stdscr.getch()
            if key in (ord("q"), 3):
                break
            continue

        left_w = min(22, max(14, width // 5))
        right_w = width - left_w
        summary_h = len(_summary_lines(state))
        main_h = height - summary_h - 1

        _draw_summary(stdscr, state, 0, 1, width - 2)
        _draw_step_list(stdscr, state, summary_h, 0, left_w, main_h)
        _draw_narrative(stdscr, state, summary_h, left_w, right_w, main_h)
        _draw_footer(stdscr, height - 1, width)
        stdscr.refresh()

        key = stdscr.getch()
        if key in (ord("q"), 3):
            break

        steps = state.steps()

        if key == curses.KEY_UP and steps:
            state.step_index = max(0, state.step_index - 1)
            state.narrative_scroll = 0
        elif key == curses.KEY_DOWN and steps:
            state.step_index = min(len(steps) - 1, state.step_index + 1)
            state.narrative_scroll = 0
        elif key == ord("[") and state.runs:
            activate_run(state, log_dir, state.run_index - 1)
        elif key == ord("]") and state.runs:
            activate_run(state, log_dir, state.run_index + 1)
        elif key == ord("R"):
            refresh_current_run(state, log_dir)
        elif key == ord("j"):
            state.narrative_scroll += 2
        elif key == ord("k"):
            state.narrative_scroll = max(0, state.narrative_scroll - 2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="TUI log viewer for rlmbenchy RLM runs.",
    )
    parser.add_argument(
        "--log-file",
        default="",
        help="Specific log file name or path. Default: latest file in log-dir.",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=DEFAULT_LOG_DIR,
        help=f"Directory with JSONL logs. Default: {DEFAULT_LOG_DIR}",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Number of recent runs to include in run switching list.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    log_dir = args.log_dir.expanduser().resolve()
    runs = load_runs(log_dir, limit=max(1, int(args.limit)))
    if not runs:
        print(f"No runs found in log directory: {log_dir}")
        return

    state = ViewerState(runs=runs)

    if args.log_file:
        raw_log = Path(args.log_file)
        target_name = raw_log.name if raw_log.suffix else str(args.log_file)
        for idx, row in enumerate(runs):
            if str(row.get("log_file") or "") == target_name:
                state.run_index = idx
                break

    activate_run(state, log_dir, state.run_index)
    curses.wrapper(_run_loop, state, log_dir)


if __name__ == "__main__":
    main()
