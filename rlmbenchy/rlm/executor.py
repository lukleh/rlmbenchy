"""Generic task executor for the reusable RLM runtime."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

import dspy

from rlmbenchy.logger import RLMLogger
from rlmbenchy.rlm.lm import build_lm
from rlmbenchy.rlm.repl import (
    DockerReplRuntime,
    LocalProcessReplRuntime,
    build_repl_runtime,
)
from rlmbenchy.rlm.rlm import RLM, RLMRunTelemetry
from rlmbenchy.rlm.runtime import (
    LMLoggingCallback,
    RLM_MAX_ITERATIONS,
    RLM_MAX_LLM_CALLS,
    build_adapter,
)
from rlmbenchy.rlm.types import LoopRunResult, RLMRunConfig, StopReason, TaskRunResult

ToolLike = dspy.Tool | Callable[..., Any]
TaskEvaluationBuilder = Callable[[TaskRunResult], Mapping[str, Any] | None]


@dataclass(frozen=True)
class TaskPredictionOutcome:
    result: dspy.Prediction
    elapsed_ms: int
    observed: str
    finalized: bool
    final_outputs: dict[str, Any] | None
    reasoning: str
    code: str
    stdout: str
    error: str | None
    latency_s: float
    status: str
    stop_reason: str
    loop_stop_reason: StopReason


def _stringify_final_outputs(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def _extract_prediction_outputs(
    result: dspy.Prediction,
    *,
    output_field_names: Sequence[str],
) -> dict[str, Any] | None:
    legacy_outputs = getattr(result, "final_outputs", None)
    if isinstance(legacy_outputs, dict):
        return legacy_outputs
    if not output_field_names:
        return {}
    values: dict[str, Any] = {}
    for name in output_field_names:
        if not hasattr(result, name):
            return None
        values[name] = getattr(result, name)
    return values


def _prediction_from_telemetry(
    telemetry: RLMRunTelemetry,
    *,
    dspy_module: Any,
) -> dspy.Prediction:
    payload = dict(telemetry.final_outputs or {})
    payload["trajectory"] = list(telemetry.trajectory)
    payload["final_reasoning"] = telemetry.reasoning
    return dspy_module.Prediction(**payload)


def _derive_last_step_fields(result: dspy.Prediction) -> tuple[str, str]:
    trajectory = getattr(result, "trajectory", None)
    if isinstance(trajectory, list) and trajectory:
        last_entry = trajectory[-1]
        if isinstance(last_entry, dict):
            reasoning = str(last_entry.get("reasoning") or "")
            code = str(last_entry.get("code") or "")
            return (reasoning, code)
    reasoning = str(getattr(result, "reasoning", "") or "")
    code = str(getattr(result, "code", "") or "")
    return (reasoning, code)


def _task_outcome(
    *,
    result: dspy.Prediction,
    elapsed_ms: int,
    output_field_names: Sequence[str],
    telemetry: RLMRunTelemetry | None = None,
) -> TaskPredictionOutcome:
    raw_stop_reason = (
        str(
            (
                telemetry.stop_reason
                if telemetry is not None
                else getattr(result, "stop_reason", "")
            )
            or ""
        )
        .strip()
        .lower()
    )
    final_outputs = (
        telemetry.final_outputs
        if telemetry is not None
        else _extract_prediction_outputs(result, output_field_names=output_field_names)
    )
    finalized = (
        telemetry.finalized if telemetry is not None else final_outputs is not None
    )
    error = (
        telemetry.error
        if telemetry is not None
        else str(getattr(result, "error", "") or "").strip() or None
    )
    has_error = bool(error)

    if raw_stop_reason == StopReason.SUCCESS.value:
        status = "success"
        stop_reason = StopReason.SUCCESS.value
        loop_stop_reason = StopReason.SUCCESS
    elif raw_stop_reason == StopReason.NO_FINAL.value:
        status = "partial"
        stop_reason = StopReason.NO_FINAL.value
        loop_stop_reason = StopReason.NO_FINAL
    elif raw_stop_reason:
        status = "error"
        stop_reason = raw_stop_reason
        loop_stop_reason = StopReason.EXECUTION_ERROR
    elif finalized:
        status = "success"
        stop_reason = StopReason.SUCCESS.value
        loop_stop_reason = StopReason.SUCCESS
    elif has_error:
        status = "error"
        stop_reason = StopReason.EXECUTION_ERROR.value
        loop_stop_reason = StopReason.EXECUTION_ERROR
    else:
        status = "partial"
        stop_reason = StopReason.NO_FINAL.value
        loop_stop_reason = StopReason.NO_FINAL

    default_reasoning, default_code = _derive_last_step_fields(result)
    final_reasoning = str(getattr(result, "final_reasoning", "") or "")
    reasoning = (
        telemetry.reasoning
        if telemetry is not None
        else default_reasoning or final_reasoning
    )
    code = telemetry.code if telemetry is not None else default_code
    stdout = (
        telemetry.stdout
        if telemetry is not None
        else str(getattr(result, "stdout", "") or "")
    )
    latency_s = (
        telemetry.latency_s
        if telemetry is not None
        else float(getattr(result, "latency_s", 0.0) or 0.0)
    )

    observed = stdout
    if final_outputs is not None:
        final_text = _stringify_final_outputs(final_outputs) or str(final_outputs)
        observed = final_text if not observed else f"{observed}\n{final_text}"

    return TaskPredictionOutcome(
        result=result,
        elapsed_ms=elapsed_ms,
        observed=observed,
        finalized=finalized,
        final_outputs=final_outputs,
        reasoning=reasoning,
        code=code,
        stdout=stdout,
        error=error,
        latency_s=latency_s,
        status=status,
        stop_reason=stop_reason,
        loop_stop_reason=loop_stop_reason,
    )


def _coerce_tool(name: str, raw: ToolLike) -> dspy.Tool:
    resolved_name = str(name).strip()
    if not resolved_name:
        raise ValueError("Tool names must be non-empty.")
    if isinstance(raw, dspy.Tool):
        if str(raw.name or "").strip() == resolved_name:
            return raw
        return dspy.Tool(
            raw.func,
            name=resolved_name,
            desc=getattr(raw, "desc", None),
            args=getattr(raw, "args", None),
        )
    if not callable(raw):
        raise TypeError(
            f"RLM tools must be callables or dspy.Tool instances. Tool {resolved_name!r} "
            f"was provided as {type(raw).__name__}."
        )
    return dspy.Tool(raw, name=resolved_name)


def _coerce_tools(
    tools: Mapping[str, ToolLike] | Sequence[ToolLike] | None,
) -> list[dspy.Tool]:
    if tools is None:
        return []
    if isinstance(tools, Mapping):
        return [
            _coerce_tool(str(name), cast(ToolLike, tool))
            for name, tool in sorted(tools.items(), key=lambda item: str(item[0]))
        ]

    resolved: list[dspy.Tool] = []
    for index, tool in enumerate(tools, start=1):
        if isinstance(tool, dspy.Tool):
            resolved.append(tool)
            continue
        if not callable(tool):
            raise TypeError(
                "RLM tools must be callables or dspy.Tool instances. "
                f"Item {index} was {type(tool).__name__}."
            )
        name = str(getattr(tool, "__name__", "") or f"tool_{index}").strip()
        resolved.append(dspy.Tool(tool, name=name))
    return resolved


def _logged_iterations(*, logger: RLMLogger, result: dspy.Prediction) -> int:
    iterations = getattr(logger, "iteration_count", 0)
    if not isinstance(iterations, int) or iterations < 0:
        iterations = 0
    if iterations == 0:
        trajectory = getattr(result, "trajectory", None)
        if isinstance(trajectory, list) and trajectory:
            iterations = len(trajectory)
        else:
            reasoning, code = _derive_last_step_fields(result)
            if reasoning.strip() or code.strip():
                iterations = 1
    return iterations


def execute_task_prediction(
    *,
    signature: type[dspy.Signature] | str,
    run_config: RLMRunConfig,
    task_inputs: Mapping[str, Any],
    task_id: str,
    logger: RLMLogger,
    tools: Mapping[str, ToolLike] | Sequence[ToolLike] | None,
    runtime: LocalProcessReplRuntime | DockerReplRuntime,
    build_lm_fn: Callable[..., Any] = build_lm,
    rlm_cls: type[RLM] | Callable[..., Any] = RLM,
    callback_cls: type[LMLoggingCallback] | Callable[..., Any] = LMLoggingCallback,
    configure_fn: Callable[..., Any] | None = None,
    dspy_module: Any = dspy,
    sub_lm: Any | None = None,
    max_iterations: int = RLM_MAX_ITERATIONS,
    max_llm_calls: int = RLM_MAX_LLM_CALLS,
) -> TaskPredictionOutcome:
    resolved_signature = dspy.ensure_signature(signature)
    if resolved_signature is None:
        raise TypeError("RLM task signature could not be resolved.")
    output_field_names = list(resolved_signature.output_fields.keys())
    resolved_tools = _coerce_tools(tools)
    build_lm_kwargs: dict[str, Any] = {
        "api_base": run_config.api_base,
        "model": run_config.model,
        "api_key": run_config.api_key,
        "request_kwargs": dict(run_config.request_kwargs),
        "num_retries": run_config.num_retries,
    }
    if run_config.lm_transport != "auto":
        build_lm_kwargs["lm_transport"] = run_config.lm_transport
    lm = build_lm_fn(**build_lm_kwargs)
    callback = callback_cls(logger=logger, task_id=task_id)
    rlm = rlm_cls(
        signature,
        max_iterations=max_iterations,
        max_llm_calls=max_llm_calls,
        tools=resolved_tools,
        interpreter=runtime,
        sub_lm=sub_lm,
        step_observer=callback,
    )
    adapter = build_adapter(run_config.adapter_mode)

    started = time.perf_counter()
    existing_callbacks = list(dspy_module.settings.get("callbacks", []) or [])
    context_kwargs: dict[str, Any] = {"callbacks": existing_callbacks + [callback]}
    if configure_fn is None:
        context_kwargs.update({"lm": lm, "adapter": adapter})
    else:
        configure_fn(lm=lm, adapter=adapter)
    telemetry: RLMRunTelemetry | None = None
    with dspy_module.context(**context_kwargs):
        try:
            result = rlm(**dict(task_inputs))
            telemetry = getattr(rlm, "last_run_telemetry", None)
        except Exception as exc:
            telemetry = getattr(rlm, "last_run_telemetry", None)
            if telemetry is not None:
                result = _prediction_from_telemetry(
                    telemetry,
                    dspy_module=dspy_module,
                )
            else:
                result = dspy_module.Prediction(
                    trajectory=[],
                    final_reasoning="",
                )
                telemetry = RLMRunTelemetry(
                    latency_s=time.perf_counter() - started,
                    stop_reason=StopReason.EXECUTION_ERROR.value,
                    finalized=False,
                    final_outputs=None,
                    reasoning="",
                    code="",
                    stdout="",
                    error=f"[RunnerError] {type(exc).__name__}: {exc}",
                    trajectory=[],
                )
        finally:
            if hasattr(runtime, "shutdown"):
                try:
                    runtime.shutdown()
                except Exception:
                    pass

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return _task_outcome(
        result=result,
        elapsed_ms=elapsed_ms,
        output_field_names=output_field_names,
        telemetry=telemetry,
    )


def run_task(
    *,
    signature: type[dspy.Signature] | str,
    run_config: RLMRunConfig,
    task_inputs: Mapping[str, Any],
    task_id: str = "task_1",
    logger: RLMLogger | None = None,
    log_dir: str | None = None,
    tools: Mapping[str, ToolLike] | Sequence[ToolLike] | None = None,
    runtime: LocalProcessReplRuntime | DockerReplRuntime | None = None,
    repl_backend: str | None = None,
    expected_answer: Any = None,
    run_metadata: Mapping[str, Any] | None = None,
    task_started_data: Mapping[str, Any] | None = None,
    task_evaluation_builder: TaskEvaluationBuilder | None = None,
    build_lm_fn: Callable[..., Any] = build_lm,
    rlm_cls: type[RLM] | Callable[..., Any] = RLM,
    callback_cls: type[LMLoggingCallback] | Callable[..., Any] = LMLoggingCallback,
    configure_fn: Callable[..., Any] | None = None,
    dspy_module: Any = dspy,
    sub_lm: Any | None = None,
    max_iterations: int = RLM_MAX_ITERATIONS,
    max_llm_calls: int = RLM_MAX_LLM_CALLS,
) -> tuple[TaskRunResult, RLMLogger]:
    active_logger = logger if logger is not None else RLMLogger(log_dir=log_dir)
    resolved_tools = _coerce_tools(tools)
    resolved_task_inputs = dict(task_inputs)

    metadata = {
        "api_base": run_config.api_base,
        "model_id": run_config.model,
        "adapter_backend": run_config.adapter_mode,
        "loop_config": {
            "max_iterations": max_iterations,
            "max_llm_calls": max_llm_calls,
        },
        "request_config": dict(run_config.request_kwargs),
        "tool_manifest": [tool.name for tool in resolved_tools],
    }
    if run_metadata is not None:
        metadata.update(dict(run_metadata))
    active_logger.log_metadata(metadata)

    started_payload = {
        "task_inputs": resolved_task_inputs,
        "expected_answer": expected_answer,
    }
    if task_started_data is not None:
        started_payload.update(dict(task_started_data))
    active_logger.log(
        {
            "event_type": "task.started",
            "task_id": task_id,
            "data": started_payload,
        }
    )

    resolved_runtime = runtime or build_repl_runtime(repl_backend)
    outcome = execute_task_prediction(
        signature=signature,
        run_config=run_config,
        task_inputs=resolved_task_inputs,
        task_id=task_id,
        logger=active_logger,
        tools=resolved_tools,
        runtime=resolved_runtime,
        build_lm_fn=build_lm_fn,
        rlm_cls=rlm_cls,
        callback_cls=callback_cls,
        configure_fn=configure_fn,
        dspy_module=dspy_module,
        sub_lm=sub_lm,
        max_iterations=max_iterations,
        max_llm_calls=max_llm_calls,
    )

    active_logger.log(
        {
            "event_type": "task.finished",
            "task_id": task_id,
            "data": {
                "status": outcome.status,
                "stop_reason": outcome.stop_reason,
                "final_outputs": outcome.final_outputs,
                "observed": outcome.observed,
                "exec_error": outcome.error,
                "finalized": outcome.finalized,
            },
            "stats": {"elapsed_ms": outcome.elapsed_ms},
        }
    )

    loop_result = LoopRunResult(
        stop_reason=outcome.loop_stop_reason,
        iterations=_logged_iterations(logger=active_logger, result=outcome.result),
        final_outputs=outcome.final_outputs,
        error=outcome.error,
    )
    task_run = TaskRunResult(
        task_id=task_id,
        status=outcome.status,
        stop_reason=outcome.stop_reason,
        elapsed_ms=outcome.elapsed_ms,
        latency_s=outcome.latency_s,
        observed=outcome.observed,
        finalized=outcome.finalized,
        final_outputs=outcome.final_outputs,
        reasoning=outcome.reasoning,
        code=outcome.code,
        error=outcome.error,
        loop_result=loop_result,
    )

    evaluation_payload = {
        "expected_answer": expected_answer,
        "correctness": None,
        "observed": outcome.observed,
    }
    if task_evaluation_builder is not None:
        extra_evaluation = task_evaluation_builder(task_run)
        if extra_evaluation is not None:
            evaluation_payload.update(dict(extra_evaluation))
    active_logger.log(
        {
            "event_type": "task.evaluated",
            "task_id": task_id,
            "data": evaluation_payload,
        }
    )

    active_logger.log_run_result(
        {
            "status": outcome.status,
            "stop_reason": outcome.stop_reason,
            "elapsed_ms": outcome.elapsed_ms,
            "final_outputs": outcome.final_outputs,
        }
    )
    return task_run, active_logger


__all__ = [
    "TaskEvaluationBuilder",
    "ToolLike",
    "execute_task_prediction",
    "run_task",
]
