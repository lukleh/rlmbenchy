"""DataHub CLI — inspect workloads and their tasks."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from rlmbenchy.datahub.registry import AVAILABLE_WORKLOADS, load_workload
from rlmbenchy.datahub.types import WorkloadTask
from rlmbenchy.datahub.workloads.support.options import parse_option_args
from rlmbenchy.datahub.workloads.support.task_selection import normalize_task_id_filter


def _truncate(text: str, max_chars: int = 80) -> str:
    cleaned = (text or "").strip().replace("\n", " ")
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[:max_chars]}..."


def _stringify_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def _task_prompt_preview(task: WorkloadTask) -> str:
    for key in ("task", "query", "question", "prompt", "instruction", "input"):
        value = task.inputs.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if len(task.inputs) == 1:
        return _stringify_value(next(iter(task.inputs.values())))
    return _stringify_value(task.inputs)


def _load_bundle_or_exit(
    workload: str,
    *,
    option_args: list[str],
    task_limit: int | None = None,
    task_id: str | None = None,
):
    selected_task_id = normalize_task_id_filter(task_id)
    try:
        return load_workload(
            workload,
            task_limit=None if selected_task_id else task_limit,
            task_id=selected_task_id,
            options=parse_option_args(option_args),
        )
    except Exception as exc:
        print(f"Error loading workload {workload!r}: {exc}", file=sys.stderr)
        sys.exit(1)


def _task_row(
    task: WorkloadTask,
    *,
    include_answer: bool,
    include_metadata: bool,
    omit_empty: bool,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": task.id,
        "inputs": task.inputs,
        "prompt_preview": _task_prompt_preview(task),
    }
    if include_answer and (not omit_empty or task.answer is not None):
        row["answer"] = task.answer
    if include_metadata and (not omit_empty or task.metadata):
        row["metadata"] = task.metadata
    return row


def cmd_workloads(args: argparse.Namespace) -> list[dict[str, str]]:
    rows = [{"name": name} for name in AVAILABLE_WORKLOADS]
    if args.json:
        print(json.dumps(rows, indent=2))
        return rows

    for row in rows:
        print(row["name"])
    print(f"\n{len(rows)} workloads available")
    return rows


def cmd_tasks(args: argparse.Namespace) -> None:
    bundle = _load_bundle_or_exit(
        args.workload,
        task_limit=args.limit,
        task_id=args.task_id,
        option_args=args.option,
    )

    if args.json:
        rows = [
            _task_row(
                task,
                include_answer=True,
                include_metadata=True,
                omit_empty=True,
            )
            for task in bundle.tasks
        ]
        print(
            json.dumps(
                {
                    "workload": bundle.workload_name,
                    "task_count": len(rows),
                    "tasks": rows,
                },
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        )
        return

    print(f"Workload: {bundle.workload_name}")
    print(f"Tasks: {len(bundle.tasks)}  Tools: {len(bundle.tools)}")
    if bundle.metadata:
        source = bundle.metadata.get("source", "")
        if source:
            print(f"Source: {source}")
    print()

    if not bundle.tasks:
        print("(no tasks)")
        return

    max_id = max(len(t.id) for t in bundle.tasks)
    col_id = max(max_id, 6)
    query_width = max(40, 100 - col_id)

    for task in bundle.tasks:
        query_preview = _truncate(_task_prompt_preview(task), query_width)
        answer_hint = ""
        if task.answer is not None:
            ans_str = str(task.answer)
            if len(ans_str) <= 30:
                answer_hint = f"  [ans: {ans_str}]"
            else:
                answer_hint = f"  [ans: {ans_str[:27]}...]"
        print(f"  {task.id:<{col_id}}  {query_preview}{answer_hint}")


def cmd_task(args: argparse.Namespace) -> None:
    bundle = _load_bundle_or_exit(
        args.workload,
        task_id=args.task_id,
        option_args=args.option,
    )

    if not bundle.tasks:
        print(
            f"No task found with id={args.task_id!r} in workload {args.workload!r}",
            file=sys.stderr,
        )
        sys.exit(1)

    task = bundle.tasks[0]

    if args.json:
        row = _task_row(
            task,
            include_answer=True,
            include_metadata=True,
            omit_empty=False,
        )
        print(json.dumps(row, indent=2, ensure_ascii=False, default=str))
        return

    print(f"Task: {task.id}")
    print(f"Workload: {bundle.workload_name}")
    print()
    print("Inputs:")
    print(json.dumps(task.inputs, indent=2, ensure_ascii=False, default=str))
    if task.answer is not None:
        print(f"\nAnswer: {task.answer}")
    if task.metadata:
        print(f"\nMetadata: {json.dumps(task.metadata, indent=2, default=str)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="datahub",
        description="Inspect DataHub workload tasks.",
    )
    sub = parser.add_subparsers(dest="command")

    p_wl = sub.add_parser("workloads", help="List available workloads.")
    p_wl.add_argument("--json", action="store_true", help="JSON output.")

    p_tasks = sub.add_parser("tasks", help="List tasks in a workload.")
    p_tasks.add_argument("workload", help="Workload name.")
    p_tasks.add_argument("--limit", type=int, default=None, help="Max tasks to show.")
    p_tasks.add_argument("--task-id", default=None, help="Filter to a single task ID.")
    p_tasks.add_argument(
        "--option",
        "-o",
        action="append",
        default=[],
        help="key=value option for the loader.",
    )
    p_tasks.add_argument("--json", action="store_true", help="JSON output.")

    p_task = sub.add_parser("task", help="Show full details for one task.")
    p_task.add_argument("workload", help="Workload name.")
    p_task.add_argument("task_id", help="Task ID.")
    p_task.add_argument(
        "--option",
        "-o",
        action="append",
        default=[],
        help="key=value option for the loader.",
    )
    p_task.add_argument("--json", action="store_true", help="JSON output.")

    args = parser.parse_args()
    if args.command == "workloads":
        cmd_workloads(args)
    elif args.command == "tasks":
        cmd_tasks(args)
    elif args.command == "task":
        cmd_task(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
