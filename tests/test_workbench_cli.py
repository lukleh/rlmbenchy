from __future__ import annotations

from types import SimpleNamespace

import pytest

import rlmbenchy.workbench.cli as run_benchmark_module


def _answer_outputs(value: object) -> dict[str, object]:
    return {"answer": value}


def test_main_routes_task_id_runs_to_run_workload(tmp_path, monkeypatch) -> None:
    from rlmbenchy.workbench.config import BenchRunConfig, LMProfile, WorkloadSpec

    config_path = tmp_path / "config.toml"
    config_path.write_text("", encoding="utf-8")
    lm = LMProfile(
        api_base="https://openrouter.ai/api/v1",
        model="openrouter/openai/gpt-oss-20b",
        request_kwargs={},
        supported_parameter_mode="off",
        ignore_unsupported_parameters=frozenset(),
    )
    config = BenchRunConfig(
        log_dir=tmp_path / "logs",
        workload=WorkloadSpec(name="tasks_v0", options={}, task_limit=5),
        lm=lm,
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        run_benchmark_module,
        "parse_args",
        lambda: SimpleNamespace(
            run_config=str(config_path),
            task_id="t1",
            seed=None,
            repl_backend=None,
        ),
    )
    monkeypatch.setattr(
        run_benchmark_module,
        "load_bench_run_config",
        lambda _path: config,
    )

    def _fake_run_workload(cfg, **kwargs):
        captured["config"] = cfg
        captured["task_id"] = kwargs.get("task_id")
        return tmp_path / "task_log.jsonl"

    monkeypatch.setattr(run_benchmark_module, "run_workload", _fake_run_workload)
    monkeypatch.setattr(
        run_benchmark_module,
        "_print_single_task_completion",
        lambda _log_path: None,
    )

    run_benchmark_module.main()

    assert captured["config"] is config
    assert captured["task_id"] == "t1"


def test_format_single_task_completion_includes_log_path_and_summary(
    tmp_path,
    monkeypatch,
) -> None:
    log_path = tmp_path / "task_log.jsonl"
    log_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        run_benchmark_module,
        "load_run",
        lambda _path: {
            "summary": {
                "status": "success",
                "stop_reason": "success",
                "elapsed_ms": 1234,
                "final_outputs": _answer_outputs("final value"),
                "error": "",
                "usage_summary": {"total_tokens": 1234},
                "activity_summary": {"llm_calls": 3, "tool_calls": 1},
            },
            "tasks": [{"task_id": "prefix_t1"}],
        },
    )

    lines = run_benchmark_module._format_single_task_completion(log_path)

    assert lines == [
        f"log_path={log_path.resolve()}",
        (
            "summary=task_id=prefix_t1 status=success stop_reason=success "
            "elapsed=1.234s total_tokens=1,234 llm_calls=3 tool_calls=1"
        ),
        "final_outputs={'answer': 'final value'}",
    ]


def test_format_single_task_completion_does_not_truncate_footer_values(
    tmp_path,
    monkeypatch,
) -> None:
    log_path = tmp_path / "task_log.jsonl"
    log_path.write_text("", encoding="utf-8")
    final_outputs = f"answer-start {'a' * 400} answer-end"
    error = f"error-start {'e' * 400} error-end"

    monkeypatch.setattr(
        run_benchmark_module,
        "load_run",
        lambda _path: {
            "summary": {
                "status": "error",
                "stop_reason": "execution_error",
                "elapsed_ms": 1234,
                "final_outputs": _answer_outputs(final_outputs),
                "error": error,
                "usage_summary": {"total_tokens": 1234},
                "activity_summary": {"llm_calls": 3, "tool_calls": 1},
            },
            "tasks": [{"task_id": "prefix_t1"}],
        },
    )

    lines = run_benchmark_module._format_single_task_completion(log_path)

    assert lines[2] == f"final_outputs={_answer_outputs(final_outputs)}"
    assert lines[3] == f"error={error}"
    assert "...[+" not in "".join(lines)


def test_main_requires_config_flag() -> None:
    # argparse enforces --config as required; missing it must SystemExit.
    with pytest.raises(SystemExit):
        run_benchmark_module.main([])


def test_main_prints_single_task_completion_footer(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    from rlmbenchy.workbench.config import BenchRunConfig, LMProfile, WorkloadSpec

    config_path = tmp_path / "config.toml"
    config_path.write_text("", encoding="utf-8")
    task_log_path = tmp_path / "task_log.jsonl"
    lm = LMProfile(
        api_base="https://openrouter.ai/api/v1",
        model="openrouter/openai/gpt-oss-20b",
        request_kwargs={},
        supported_parameter_mode="off",
        ignore_unsupported_parameters=frozenset(),
    )
    config = BenchRunConfig(
        log_dir=tmp_path / "logs",
        workload=WorkloadSpec(name="tasks_v0", options={}, task_limit=5),
        lm=lm,
    )

    monkeypatch.setattr(
        run_benchmark_module,
        "parse_args",
        lambda: SimpleNamespace(
            run_config=str(config_path),
            task_id="t1",
            seed=None,
            repl_backend=None,
        ),
    )
    monkeypatch.setattr(
        run_benchmark_module,
        "load_bench_run_config",
        lambda _path: config,
    )
    monkeypatch.setattr(
        run_benchmark_module,
        "run_workload",
        lambda _config, **_kwargs: task_log_path,
    )
    monkeypatch.setattr(
        run_benchmark_module,
        "_format_single_task_completion",
        lambda _path: [
            f"log_path={task_log_path}",
            "summary=status=success stop_reason=success elapsed=1.234s total_tokens=321 llm_calls=2 tool_calls=0",
        ],
    )

    run_benchmark_module.main()
    out = capsys.readouterr().out

    assert f"config={config_path.resolve()}" in out
    assert f"log_path={task_log_path}" in out
    assert (
        "summary=status=success stop_reason=success elapsed=1.234s "
        "total_tokens=321 llm_calls=2 tool_calls=0"
    ) in out
