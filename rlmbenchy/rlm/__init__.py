"""Public RLM runtime API."""

from __future__ import annotations

from typing import Any

__all__ = [
    "ChatGPTResponsesLM",
    "DEFAULT_SIGNATURE_ID",
    "DockerReplRuntime",
    "LMLoggingCallback",
    "LocalProcessReplRuntime",
    "LoopRunResult",
    "RLM",
    "RLMRunConfig",
    "RLM_MAX_ITERATIONS",
    "RLM_MAX_LLM_CALLS",
    "ReplExecutionTimeoutError",
    "ReplRuntimeError",
    "SignatureFieldSpec",
    "StopReason",
    "TaskRunResult",
    "VALID_ADAPTER_MODES",
    "build_adapter",
    "build_lm",
    "build_task_signature",
    "extract_final_answer",
    "is_retryable_tool_error",
    "loop_result_summary",
    "normalize_adapter_mode",
    "resolve_model_api_key",
    "run_task",
]

_MODULE_BY_NAME = {
    "ChatGPTResponsesLM": "rlmbenchy.rlm.lm",
    "build_lm": "rlmbenchy.rlm.lm",
    "resolve_model_api_key": "rlmbenchy.rlm.lm",
    "DockerReplRuntime": "rlmbenchy.rlm.repl",
    "LocalProcessReplRuntime": "rlmbenchy.rlm.repl",
    "ReplExecutionTimeoutError": "rlmbenchy.rlm.repl",
    "ReplRuntimeError": "rlmbenchy.rlm.repl",
    "RLM": "rlmbenchy.rlm.rlm",
    "DEFAULT_SIGNATURE_ID": "rlmbenchy.rlm.runtime",
    "LMLoggingCallback": "rlmbenchy.rlm.runtime",
    "RLM_MAX_ITERATIONS": "rlmbenchy.rlm.runtime",
    "RLM_MAX_LLM_CALLS": "rlmbenchy.rlm.runtime",
    "VALID_ADAPTER_MODES": "rlmbenchy.rlm.runtime",
    "build_adapter": "rlmbenchy.rlm.runtime",
    "normalize_adapter_mode": "rlmbenchy.rlm.runtime",
    "run_task": "rlmbenchy.rlm.executor",
    "SignatureFieldSpec": "rlmbenchy.rlm.signatures",
    "build_task_signature": "rlmbenchy.rlm.signatures",
    "extract_final_answer": "rlmbenchy.rlm.results",
    "is_retryable_tool_error": "rlmbenchy.rlm.results",
    "loop_result_summary": "rlmbenchy.rlm.results",
    "LoopRunResult": "rlmbenchy.rlm.types",
    "RLMRunConfig": "rlmbenchy.rlm.types",
    "StopReason": "rlmbenchy.rlm.types",
    "TaskRunResult": "rlmbenchy.rlm.types",
}


def __getattr__(name: str) -> Any:
    module_name = _MODULE_BY_NAME.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module = __import__(module_name, fromlist=[name])
    value = getattr(module, name)
    globals()[name] = value
    return value
