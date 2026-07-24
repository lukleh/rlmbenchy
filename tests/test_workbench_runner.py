from __future__ import annotations

import json
from pathlib import Path

import dspy

from rlmbenchy.datahub.types import WorkloadBundle, WorkloadTask
import rlmbenchy.workbench.runner as runner_module
from rlmbenchy.logger.otel import domain_events_from_otel_records
from rlmbenchy.rlm.repl import DockerReplRuntime, LocalProcessReplRuntime
from rlmbenchy.workbench.config import ReplSpec


class _TestSignature(dspy.Signature):
    """Test task."""

    task: str = dspy.InputField(desc="Task.")
    answer: str = dspy.OutputField(desc="Answer.")


class _TaskOverrideSignature(dspy.Signature):
    """Task override."""

    task: str = dspy.InputField(desc="Task.")
    answer: str = dspy.OutputField(desc="Answer.")


def test_run_workload_end_to_end_smoke(tmp_path, monkeypatch) -> None:
    from rlmbenchy.rlm.types import LoopRunResult, StopReason, TaskRunResult
    from rlmbenchy.workbench.config import (
        BenchRunConfig,
        LMProfile,
        WorkloadSpec,
    )

    lm = LMProfile(
        api_base="https://openrouter.ai/api/v1",
        model="openrouter/openai/gpt-oss-20b",
        request_kwargs={},
        supported_parameter_mode="off",
        ignore_unsupported_parameters=frozenset(),
    )
    config = BenchRunConfig(
        log_dir=tmp_path / "logs",
        workload=WorkloadSpec(name="tasks_v0", options={}, task_limit=1),
        lm=lm,
    )

    bundle = WorkloadBundle(
        workload_name="tasks_v0",
        tasks=[
            WorkloadTask(
                id="t_smoke",
                inputs={"task": "solve it"},
                answer="42",
            ),
        ],
        tools=[],
        signature=_TestSignature,
        metadata={},
    )
    monkeypatch.setattr(runner_module, "load_workload", lambda *_a, **_kw: bundle)
    captured_run_task_kwargs: dict[str, object] = {}

    def _fake_resolve_api_key(**_kwargs):
        return "test-key"

    monkeypatch.setattr(runner_module, "resolve_model_api_key", _fake_resolve_api_key)

    loop_result = LoopRunResult(
        stop_reason=StopReason.SUCCESS,
        iterations=2,
        final_outputs={"answer": "42"},
    )
    fake_task_run = TaskRunResult(
        task_id="t_smoke",
        status="success",
        stop_reason="success",
        elapsed_ms=120,
        latency_s=0.12,
        observed="42",
        finalized=True,
        final_outputs={"answer": "42"},
        reasoning="short",
        code="SUBMIT(answer='42')",
        error=None,
        loop_result=loop_result,
    )

    def _fake_run_task(**kwargs):
        captured_run_task_kwargs.update(kwargs)
        logger = kwargs["logger"]
        logger.log_metadata(dict(kwargs.get("run_metadata") or {}))
        logger.log_run_result({"status": "success", "stop_reason": "success"})
        builder = kwargs["task_evaluation_builder"]
        builder(fake_task_run)
        return fake_task_run, logger

    monkeypatch.setattr(runner_module, "run_task", _fake_run_task)

    class _DummyRuntime:
        def __init__(self) -> None:
            self.image = "stub"

    monkeypatch.setattr(runner_module, "_build_runtime", lambda _spec: _DummyRuntime())

    log_path = runner_module.run_workload(
        config,
        task_id="t_smoke",
        run_config_name="my_run",
    )

    assert log_path.exists()
    assert log_path.suffix == ".jsonl"
    assert log_path.is_relative_to(tmp_path / "logs")
    entries = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert entries, "smoke run produced no log entries"
    domain_events = domain_events_from_otel_records(entries)
    run_started = next(
        entry for entry in domain_events if entry.get("event_type") == "run.started"
    )
    assert run_started["data"]["run_config_name"] == "my_run"
    assert run_started["data"]["workload"] == "tasks_v0"
    assert run_started["data"]["model_id"] == "openrouter/openai/gpt-oss-20b"
    assert captured_run_task_kwargs["signature"] is _TestSignature


def test_run_workload_uses_task_signature_override(tmp_path, monkeypatch) -> None:
    from rlmbenchy.rlm.types import LoopRunResult, StopReason, TaskRunResult
    from rlmbenchy.workbench.config import BenchRunConfig, LMProfile, WorkloadSpec

    config = BenchRunConfig(
        log_dir=tmp_path / "logs",
        workload=WorkloadSpec(name="tasks_v0", options={}, task_limit=1),
        lm=LMProfile(
            api_base="https://openrouter.ai/api/v1",
            model="openrouter/openai/gpt-oss-20b",
            request_kwargs={},
            supported_parameter_mode="off",
            ignore_unsupported_parameters=frozenset(),
        ),
    )
    bundle = WorkloadBundle(
        workload_name="tasks_v0",
        tasks=[
            WorkloadTask(
                id="task_1",
                inputs={"task": "solve it"},
                answer="42",
                signature=_TaskOverrideSignature,
            ),
        ],
        tools=[],
        signature=_TestSignature,
        metadata={},
    )
    monkeypatch.setattr(runner_module, "load_workload", lambda *_a, **_kw: bundle)
    monkeypatch.setattr(
        runner_module, "resolve_model_api_key", lambda **_kwargs: "test-key"
    )
    monkeypatch.setattr(runner_module, "_build_runtime", lambda _spec: object())

    captured: dict[str, object] = {}
    fake_task_run = TaskRunResult(
        task_id="task_1",
        status="success",
        stop_reason="success",
        elapsed_ms=1,
        latency_s=0.001,
        observed="42",
        finalized=True,
        final_outputs={"answer": "42"},
        reasoning="",
        code="SUBMIT(answer='42')",
        error=None,
        loop_result=LoopRunResult(
            stop_reason=StopReason.SUCCESS,
            iterations=1,
            final_outputs={"answer": "42"},
        ),
    )

    def _fake_run_task(**kwargs):
        captured.update(kwargs)
        logger = kwargs["logger"]
        logger.log_metadata(dict(kwargs.get("run_metadata") or {}))
        logger.log_run_result({"status": "success", "stop_reason": "success"})
        kwargs["task_evaluation_builder"](fake_task_run)
        return fake_task_run, logger

    monkeypatch.setattr(runner_module, "run_task", _fake_run_task)

    runner_module.run_workload(config, task_id="task_1")

    assert captured["signature"] is _TaskOverrideSignature


def test_build_run_metadata_has_expected_shape() -> None:
    from rlmbenchy.workbench.config import (
        BenchRunConfig,
        LMProfile,
        WorkloadSpec,
    )

    main_lm = LMProfile(
        api_base="https://openrouter.ai/api/v1",
        model="openrouter/openai/gpt-oss-20b",
        request_kwargs={"temperature": 0.0},
        supported_parameter_mode="off",
        ignore_unsupported_parameters=frozenset({"temperature"}),
    )
    sub_lm = LMProfile(
        api_base="https://chatgpt.com/backend-api/codex",
        model="chatgpt/gpt-5.6-terra",
        request_kwargs={},
        supported_parameter_mode="off",
        ignore_unsupported_parameters=frozenset(),
    )
    config = BenchRunConfig(
        log_dir=Path("/tmp/rlm-logs"),
        workload=WorkloadSpec(name="tasks_v0", options={}, task_limit=3),
        lm=main_lm,
        sub_lm=sub_lm,
        adapter_mode="json",
    )
    bundle = WorkloadBundle(
        workload_name="tasks_v0",
        tasks=[],
        tools=[],
        signature=_TestSignature,
        metadata={},
    )
    task = WorkloadTask(id="task_1", inputs={"task": "solve it"}, answer="OK")

    metadata = runner_module._build_run_metadata(
        config,
        bundle,
        task,
        2,
        5,
        "batch_xyz",
        run_config_name="my_run",
        lm_profile_name="main_profile",
        sub_lm_profile_name="sub_profile",
    )

    assert metadata["config"]["workload"]["name"] == "tasks_v0"
    assert metadata["config"]["lm"]["model"] == "openrouter/openai/gpt-oss-20b"
    assert metadata["config"]["adapter_mode"] == "json"

    assert metadata["run_config_name"] == "my_run"
    assert metadata["lm_profile_name"] == "main_profile"
    assert metadata["sub_lm_profile_name"] == "sub_profile"

    assert metadata["runner"] == "rlm"
    assert metadata["workload"] == "tasks_v0"
    assert metadata["model_id"] == "openrouter/openai/gpt-oss-20b"
    assert metadata["api_base"] == "https://openrouter.ai/api/v1"
    assert metadata["adapter_backend"] == "json"
    assert metadata["sub_model_id"] == "chatgpt/gpt-5.6-terra"
    assert metadata["sub_api_base"] == "https://chatgpt.com/backend-api/codex"

    assert metadata["task_id"] == "task_1"
    assert metadata["task_index"] == 2
    assert metadata["task_total"] == 5
    assert metadata["batch_id"] == "batch_xyz"


def test_build_run_metadata_omits_sub_lm_fields_when_absent() -> None:
    from rlmbenchy.workbench.config import (
        BenchRunConfig,
        LMProfile,
        WorkloadSpec,
    )

    lm = LMProfile(
        api_base="https://openrouter.ai/api/v1",
        model="openrouter/openai/gpt-oss-20b",
        request_kwargs={},
        supported_parameter_mode="off",
        ignore_unsupported_parameters=frozenset(),
    )
    config = BenchRunConfig(
        log_dir=Path("/tmp/rlm-logs"),
        workload=WorkloadSpec(name="tasks_v0", options={}, task_limit=1),
        lm=lm,
    )
    bundle = WorkloadBundle(
        workload_name="tasks_v0",
        tasks=[],
        tools=[],
        signature=_TestSignature,
        metadata={},
    )
    task = WorkloadTask(id="task_1", inputs={"task": "x"}, answer=None)

    metadata = runner_module._build_run_metadata(
        config,
        bundle,
        task,
        1,
        1,
        "batch_abc",
        run_config_name=None,
        lm_profile_name=None,
        sub_lm_profile_name=None,
    )

    assert metadata["sub_model_id"] is None
    assert metadata["sub_api_base"] is None
    assert metadata["run_config_name"] is None


def test_load_tasks_passes_task_id_without_task_limit(monkeypatch) -> None:
    from rlmbenchy.workbench.config import (
        BenchRunConfig,
        LMProfile,
        WorkloadSpec,
    )

    lm = LMProfile(
        api_base="https://openrouter.ai/api/v1",
        model="openrouter/openai/gpt-oss-20b",
        request_kwargs={},
        supported_parameter_mode="off",
        ignore_unsupported_parameters=frozenset(),
    )
    config = BenchRunConfig(
        log_dir=Path("/tmp/rlm-logs"),
        workload=WorkloadSpec(
            name="tasks_v0",
            options={"source": "test"},
            task_limit=1,
        ),
        lm=lm,
    )
    bundle = WorkloadBundle(
        workload_name="tasks_v0",
        tasks=[
            WorkloadTask(id="other", inputs={"task": "skip"}, answer=None),
            WorkloadTask(id="target", inputs={"task": "run"}, answer="ok"),
        ],
        tools=[],
        signature=_TestSignature,
        metadata={},
    )
    captured: dict[str, object] = {}

    def _load_workload(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return bundle

    monkeypatch.setattr(runner_module, "load_workload", _load_workload)

    loaded_bundle, tasks = runner_module._load_tasks(config, task_id=" target ")

    assert loaded_bundle is bundle
    assert [task.id for task in tasks] == ["target"]
    assert captured["args"] == ("tasks_v0",)
    assert captured["kwargs"] == {
        "task_limit": None,
        "task_id": "target",
        "options": {"source": "test"},
    }


def test_build_runtime_propagates_docker_image() -> None:
    spec = ReplSpec(
        backend="docker",
        docker_image="python:3.12-slim",
    )

    runtime = runner_module._build_runtime(spec)

    assert isinstance(runtime, DockerReplRuntime)
    assert runtime.image == "python:3.12-slim"


def test_build_runtime_uses_local_backend() -> None:
    spec = ReplSpec(
        backend="local",
        docker_image="python:3.12-slim",
    )

    runtime = runner_module._build_runtime(spec)

    assert isinstance(runtime, LocalProcessReplRuntime)
