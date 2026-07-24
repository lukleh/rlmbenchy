"""Workbench runner: resolves BenchRunConfig → RLM execution."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import dspy
from rlmbenchy.datahub.registry import load_workload
from rlmbenchy.datahub.scoring import score_answer
from rlmbenchy.datahub.types import WorkloadBundle, WorkloadTask
from rlmbenchy.datahub.workloads.support.active_task import active_task
from rlmbenchy.datahub.workloads.support.task_selection import normalize_task_id_filter

from rlmbenchy.lm_config import validate_supported_parameters_for_openrouter
from rlmbenchy.logger import RLMLogger, VerbosePrinter
from rlmbenchy.logger.live_display import LiveStepDisplay
from rlmbenchy.rlm import (
    LMLoggingCallback,
    RLMRunConfig,
    RLM,
    TaskRunResult,
    resolve_model_api_key,
    run_task,
)
from rlmbenchy.rlm.lm import build_lm as build_runtime_lm
from rlmbenchy.rlm.repl import (
    DockerReplRuntime,
    LocalProcessReplRuntime,
    normalize_repl_backend,
)
from rlmbenchy.workbench.config import (
    BenchRunConfig,
    LMProfile,
    ReplSpec,
)

ToolLike = dspy.Tool | Callable[..., Any]


def _compute_correctness(*, expected: Any, observed_final: Any) -> bool | None:
    if expected is None:
        return None
    if isinstance(expected, dict):
        _score, is_correct, _detail = score_answer(
            _stringify_answer_for_scoring(observed_final),
            expected,
        )
        return is_correct
    if observed_final is None:
        return False
    return str(expected).strip() == str(observed_final).strip()


def _observed_output_for_scoring(
    *,
    workload_bundle: WorkloadBundle,
    final_outputs: dict[str, Any] | None,
) -> Any:
    if final_outputs is None:
        return None
    output_names = list(workload_bundle.signature.output_fields.keys())
    if len(output_names) == 1:
        return final_outputs.get(output_names[0])
    return final_outputs


def _stringify_answer_for_scoring(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _validate_lm_profile(profile: LMProfile, request_params: dict[str, Any]) -> None:
    validate_supported_parameters_for_openrouter(
        api_base=profile.api_base,
        model=profile.model,
        supported_parameter_mode=profile.supported_parameter_mode,
        ignore_unsupported_parameters=profile.ignore_unsupported_parameters,
        request_params=request_params,
    )


def _build_rlm_run_config(
    lm: LMProfile,
    adapter_mode: str,
    *,
    seed: int,
) -> tuple[RLMRunConfig, str, dict[str, Any]]:
    request_params: dict[str, Any] = {**lm.request_kwargs, "seed": int(seed)}
    _validate_lm_profile(lm, request_params)
    api_key = resolve_model_api_key(
        api_base=lm.api_base,
        api_key=lm.api_key,
        api_key_env=lm.api_key_env,
        api_key_override=None,
    )
    run_config = RLMRunConfig(
        api_base=lm.api_base,
        model=lm.model,
        api_key=api_key,
        adapter_mode=adapter_mode,
        request_kwargs=request_params,
        lm_transport=lm.lm_transport,
    )
    return run_config, api_key, request_params


def _build_sub_lm(
    lm: LMProfile | None,
    *,
    seed: int,
) -> Any | None:
    # Sub-LM is a bare `dspy.LM` used for `llm_query(...)` sub-calls, not the
    # DSPy pipeline LM — the main config.adapter_mode does not apply here, so
    # this path does not thread adapter_mode through.
    if lm is None:
        return None
    request_params: dict[str, Any] = {**lm.request_kwargs, "seed": int(seed)}
    _validate_lm_profile(lm, request_params)
    api_key = resolve_model_api_key(
        api_base=lm.api_base,
        api_key=lm.api_key,
        api_key_env=lm.api_key_env,
        api_key_override=None,
    )
    kwargs: dict[str, Any] = {
        "api_base": lm.api_base,
        "model": lm.model,
        "api_key": api_key,
        "request_kwargs": request_params,
    }
    if lm.lm_transport != "auto":
        kwargs["lm_transport"] = lm.lm_transport
    return build_runtime_lm(**kwargs)


def _build_runtime(
    repl: ReplSpec,
) -> LocalProcessReplRuntime | DockerReplRuntime:
    backend = normalize_repl_backend(repl.backend)
    if backend == "local":
        return LocalProcessReplRuntime()
    return DockerReplRuntime(
        image=repl.docker_image,
    )


def _load_tasks(
    config: BenchRunConfig, *, task_id: str | None
) -> tuple[WorkloadBundle, list[WorkloadTask]]:
    selected_task_id = normalize_task_id_filter(task_id)
    # task_id is passed to load_workload so workload loaders can stop early
    # (e.g. avoid paging through a remote dataset); the post-load filter keeps
    # the runner tolerant of older or external loaders.
    bundle = load_workload(
        config.workload.name,
        task_limit=None if selected_task_id else config.workload.task_limit,
        task_id=selected_task_id,
        options=dict(config.workload.options),
    )
    if selected_task_id:
        tasks = [t for t in bundle.tasks if t.id == selected_task_id]
        if not tasks:
            raise SystemExit(f"Task id {selected_task_id!r} not found in workload.")
    else:
        tasks = list(bundle.tasks)[: max(0, config.workload.task_limit)]
    return bundle, tasks


def _build_run_metadata(
    config: BenchRunConfig,
    workload_bundle: WorkloadBundle,
    task: WorkloadTask,
    task_index: int,
    task_total: int,
    batch_id: str,
    *,
    run_config_name: str | None,
    lm_profile_name: str | None,
    sub_lm_profile_name: str | None,
) -> dict[str, Any]:
    return {
        "config": asdict(config),
        "run_config_name": run_config_name,
        "lm_profile_name": lm_profile_name,
        "sub_lm_profile_name": sub_lm_profile_name,
        "runner": "rlm",
        "workload": config.workload.name,
        "model_id": config.lm.model,
        "api_base": config.lm.api_base,
        "adapter_backend": config.adapter_mode,
        "sub_model_id": config.sub_lm.model if config.sub_lm else None,
        "sub_api_base": config.sub_lm.api_base if config.sub_lm else None,
        "task_id": task.id,
        "task_index": task_index,
        "task_total": task_total,
        "batch_id": batch_id,
    }


def _run_one_task(
    config: BenchRunConfig,
    bundle: WorkloadBundle,
    task: WorkloadTask,
    task_index: int,
    task_total: int,
    *,
    seed: int,
    repl: ReplSpec,
    sub_lm: Any | None,
    batch_id: str,
    run_config_name: str | None = None,
    lm_profile_name: str | None = None,
    sub_lm_profile_name: str | None = None,
) -> tuple[dict[str, Any], Path]:
    rlm_run_config, _, _ = _build_rlm_run_config(
        config.lm, config.adapter_mode, seed=seed
    )
    metadata = _build_run_metadata(
        config,
        bundle,
        task,
        task_index,
        task_total,
        batch_id,
        run_config_name=run_config_name,
        lm_profile_name=lm_profile_name,
        sub_lm_profile_name=sub_lm_profile_name,
    )

    live = LiveStepDisplay(max_iterations=config.max_iterations)
    logger = RLMLogger(
        log_dir=config.log_dir,
        file_name="rlm",
        on_event=live.handle_event,
    )
    printer = VerbosePrinter(enabled=True)
    printer.print_metadata(metadata)
    runtime = _build_runtime(repl)
    row_payload: dict[str, Any] | None = None
    task_inputs = dict(task.inputs)
    task_signature = task.signature or bundle.signature

    def _build_task_evaluation(task_run: TaskRunResult) -> dict[str, Any]:
        nonlocal row_payload
        observed_final = _observed_output_for_scoring(
            workload_bundle=bundle,
            final_outputs=task_run.final_outputs,
        )
        is_correct = _compute_correctness(
            expected=task.answer,
            observed_final=observed_final,
        )
        row_payload = {
            "task_id": task.id,
            "task_inputs": task_inputs,
            "expected_answer": task.answer,
            "is_correct": is_correct,
            "latency_s": round(task_run.latency_s, 3),
            "status": task_run.status,
            "stop_reason": task_run.stop_reason,
            "finalized": task_run.finalized,
            "final_outputs": task_run.final_outputs,
            "observed": task_run.observed,
            "code": task_run.code,
            "reasoning": task_run.reasoning,
            "exec_error": task_run.error,
        }
        return {"correctness": is_correct}

    with active_task(task.id):
        task_run, _ = run_task(
            signature=task_signature,
            run_config=rlm_run_config,
            task_inputs=task_inputs,
            task_id=task.id,
            logger=logger,
            tools=bundle.tools,
            runtime=runtime,
            expected_answer=task.answer,
            run_metadata=metadata,
            task_started_data={
                "workload": bundle.workload_name,
                **task_inputs,
            },
            task_evaluation_builder=_build_task_evaluation,
            build_lm_fn=build_runtime_lm,
            rlm_cls=RLM,
            callback_cls=LMLoggingCallback,
            configure_fn=dspy.configure,
            dspy_module=dspy,
            sub_lm=sub_lm,
            max_iterations=config.max_iterations,
            max_llm_calls=config.max_llm_calls,
        )

    if logger.log_file_path is None:
        raise RuntimeError("Logger did not create a JSONL log file path.")
    if row_payload is None:
        raise RuntimeError("Task evaluation payload was not produced.")
    printer.print_summary(task_run.loop_result)
    return row_payload, Path(logger.log_file_path)


def run_workload(
    config: BenchRunConfig,
    *,
    task_id: str | None = None,
    seed: int | None = None,
    repl_backend: str | None = None,
    run_config_name: str | None = None,
    lm_profile_name: str | None = None,
    sub_lm_profile_name: str | None = None,
) -> Path:
    effective_seed = seed if seed is not None else config.seed
    effective_repl = (
        replace(config.repl, backend=repl_backend)
        if repl_backend is not None
        else config.repl
    )

    bundle, tasks = _load_tasks(config, task_id=task_id)
    if not tasks:
        raise RuntimeError("No tasks were loaded for this run.")

    sub_lm_instance = _build_sub_lm(config.sub_lm, seed=effective_seed)

    batch_id = str(uuid.uuid4())[:8]
    task_total = len(tasks)
    last_log_path: Path | None = None

    for idx, task in enumerate(tasks, start=1):
        _row, log_path = _run_one_task(
            config,
            bundle,
            task,
            idx,
            task_total,
            seed=effective_seed,
            repl=effective_repl,
            sub_lm=sub_lm_instance,
            batch_id=batch_id,
            run_config_name=run_config_name,
            lm_profile_name=lm_profile_name,
            sub_lm_profile_name=sub_lm_profile_name,
        )
        last_log_path = log_path

    assert last_log_path is not None
    return last_log_path


__all__ = [
    "ToolLike",
    "run_workload",
]
