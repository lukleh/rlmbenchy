"""CLI for running workloads, inspecting logs, and inspecting runtime paths."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import rlmbenchy.datahub.cli as datahub_cli
import rlmbenchy.workbench.cli as workbench_cli
from rlmbenchy.logger import (
    DEFAULT_LOG_DIR,
    build_show_payload,
    build_stats_payload,
    build_tree_payload,
    find_latest_log_file,
    format_show_text,
    format_stats_text,
    format_tree_text,
    resolve_log_file,
)
from rlmbenchy.runtime_paths import resolve_runtime_paths


def _add_log_source_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Specific .jsonl file to inspect. If omitted, latest in --log-dir is used.",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=DEFAULT_LOG_DIR,
        help=f"Directory containing .jsonl files (default: {DEFAULT_LOG_DIR}).",
    )


def _add_workload_option_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--option",
        "-o",
        action="append",
        default=[],
        help="key=value option passed through to the workload loader or validator.",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run workloads, inspect logs, and inspect runtime paths."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    paths_parser = subparsers.add_parser(
        "paths",
        help="Print the resolved runtime config/state/cache paths.",
    )
    paths_parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON."
    )

    run_parser = subparsers.add_parser(
        "run",
        help="Run a workload from a TOML run config.",
    )
    workbench_cli.add_run_arguments(run_parser)

    workloads_parser = subparsers.add_parser(
        "workloads",
        help="Inspect workloads and their tasks.",
    )
    workloads_parser.set_defaults(workloads_command="list", json=False)
    workloads_subparsers = workloads_parser.add_subparsers(dest="workloads_command")

    workloads_list_parser = workloads_subparsers.add_parser(
        "list",
        help="List available workloads.",
    )
    workloads_list_parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON."
    )

    workloads_tasks_parser = workloads_subparsers.add_parser(
        "tasks",
        help="List tasks from one workload.",
    )
    workloads_tasks_parser.add_argument("workload", help="Workload name.")
    workloads_tasks_parser.add_argument(
        "--limit", type=int, default=None, help="Max tasks to show."
    )
    workloads_tasks_parser.add_argument(
        "--task-id", default=None, help="Filter to a single task ID."
    )
    _add_workload_option_args(workloads_tasks_parser)
    workloads_tasks_parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON."
    )

    workloads_task_parser = workloads_subparsers.add_parser(
        "task",
        help="Show full details for one workload task.",
    )
    workloads_task_parser.add_argument("workload", help="Workload name.")
    workloads_task_parser.add_argument("task_id", help="Task ID.")
    _add_workload_option_args(workloads_task_parser)
    workloads_task_parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON."
    )

    logs_parser = subparsers.add_parser("logs", help="Inspect rlmbenchy JSONL logs.")
    logs_subparsers = logs_parser.add_subparsers(dest="logs_command", required=True)

    latest_log_parser = logs_subparsers.add_parser(
        "latest",
        help="Print the latest .jsonl log file in --log-dir.",
    )
    latest_log_parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    latest_log_parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON."
    )

    stats_parser = logs_subparsers.add_parser("stats", help="Show aggregate run stats.")
    _add_log_source_args(stats_parser)
    stats_parser.add_argument("--run-id", default=None, help="Filter to one run_id.")
    stats_parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON."
    )

    tree_parser = logs_subparsers.add_parser(
        "tree", help="Show run-by-run tree with per-iteration summaries."
    )
    _add_log_source_args(tree_parser)
    tree_parser.add_argument("--run-id", default=None, help="Filter to one run_id.")
    tree_parser.add_argument("--max-preview-chars", type=int, default=140)
    tree_parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON."
    )

    show_parser = logs_subparsers.add_parser(
        "show", help="Show raw-ish entries with optional failure filtering."
    )
    _add_log_source_args(show_parser)
    show_parser.add_argument("--run-id", default=None, help="Filter to one run_id.")
    show_parser.add_argument("--only-failures", action="store_true")
    show_parser.add_argument("--limit", type=int, default=80)
    show_parser.add_argument("--max-preview-chars", type=int, default=160)
    show_parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON."
    )

    return parser


def _handle_run(args: argparse.Namespace) -> None:
    workbench_cli.run_from_config_path(
        Path(str(args.run_config)),
        task_id=str(args.task_id) if args.task_id else None,
        seed=int(args.seed) if args.seed is not None else None,
        repl_backend=str(args.repl_backend) if args.repl_backend else None,
    )


def _handle_workloads(args: argparse.Namespace) -> None:
    command = str(getattr(args, "workloads_command", "list") or "list")
    if command == "list":
        datahub_cli.cmd_workloads(args)
        return
    if command == "tasks":
        datahub_cli.cmd_tasks(args)
        return
    if command == "task":
        datahub_cli.cmd_task(args)
        return
    raise SystemExit(f"Unknown workloads command: {command}")


def _handle_logs(args: argparse.Namespace) -> None:
    if args.logs_command == "latest":
        latest = find_latest_log_file(args.log_dir)
        if latest is None:
            raise SystemExit(f"No .jsonl log files found in: {args.log_dir}")
        if args.json:
            print(json.dumps({"log_file": str(latest)}, ensure_ascii=False, indent=2))
        else:
            print(latest)
        return

    try:
        log_path = resolve_log_file(log_file=args.log_file, log_dir=args.log_dir)
        if args.logs_command == "stats":
            payload = build_stats_payload(log_path, run_id=args.run_id)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(format_stats_text(payload))
            return
        if args.logs_command == "tree":
            payload = build_tree_payload(
                log_path,
                run_id=args.run_id,
                max_preview_chars=int(args.max_preview_chars),
            )
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(format_tree_text(payload))
            return
        if args.logs_command == "show":
            payload = build_show_payload(
                log_path,
                run_id=args.run_id,
                only_failures=bool(args.only_failures),
                limit=int(args.limit),
                max_preview_chars=int(args.max_preview_chars),
            )
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(format_show_text(payload))
            return
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc
    except KeyError as exc:
        message = str(exc.args[0]) if exc.args else str(exc)
        raise SystemExit(message) from exc

    raise SystemExit(f"Unknown logs command: {args.logs_command}")


def _handle_paths(args: argparse.Namespace) -> None:
    runtime_paths = resolve_runtime_paths()
    if args.json:
        print(json.dumps(runtime_paths.to_dict(), ensure_ascii=False, indent=2))
        return
    print(runtime_paths.render())


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)

    if args.command == "paths":
        _handle_paths(args)
        return
    if args.command == "run":
        _handle_run(args)
        return
    if args.command == "logs":
        _handle_logs(args)
        return
    if args.command == "workloads":
        _handle_workloads(args)
        return

    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
