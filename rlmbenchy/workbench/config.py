"""Workbench config loading for benchmark and task-run flows."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rlmbenchy.lm_config import (
    DEFAULT_API_BASE,
    DEFAULT_MODEL,
    parse_lm_auth_config,
    parse_lm_config,
)
from rlmbenchy.rlm.runtime import normalize_adapter_mode
from rlmbenchy.runtime_config import (
    load_runtime_toml,
    resolve_named_lm_profile_path,
    resolve_path,
)
from rlmbenchy.runtime_paths import resolve_runtime_paths

_RUNTIME_PATHS = resolve_runtime_paths()

DEFAULT_LOG_DIR = _RUNTIME_PATHS.rlm_log_dir
DEFAULT_CONFIG_DIR = _RUNTIME_PATHS.lm_profiles_dir


@dataclass(frozen=True)
class LMProfile:
    api_base: str
    model: str
    request_kwargs: dict[str, Any]
    supported_parameter_mode: str
    ignore_unsupported_parameters: frozenset[str]
    api_key: str | None = None
    api_key_env: str | None = None
    lm_transport: str = "auto"


@dataclass(frozen=True)
class WorkloadSpec:
    name: str
    options: dict[str, Any]
    task_limit: int


@dataclass(frozen=True)
class ReplSpec:
    backend: str = "docker"
    docker_image: str = "python:3.14-slim"


@dataclass(frozen=True)
class BenchRunConfig:
    log_dir: Path
    workload: WorkloadSpec
    lm: LMProfile
    sub_lm: LMProfile | None = None
    adapter_mode: str = "auto"
    seed: int = 1
    max_iterations: int = 100
    max_llm_calls: int = 200
    repl: ReplSpec = field(default_factory=ReplSpec)


def resolve_lm_profile_path(raw: str | Path) -> Path:
    return resolve_named_lm_profile_path(raw)


def resolve_lm_profile_reference(
    raw: str | Path, *, base_dir: Path | None = None
) -> Path:
    text = str(raw).strip()
    if not text:
        raise ValueError("LM profile reference must be a non-empty string or path.")

    if base_dir is not None:
        candidate = Path(text).expanduser()
        if candidate.is_absolute() or text.startswith(".") or text.startswith("~"):
            return resolve_path(text, base_dir)
        if text.endswith(".toml"):
            local_candidate = resolve_path(text, base_dir)
            if local_candidate.exists():
                return local_candidate

    return resolve_lm_profile_path(text)


def _parse_lm_profile(raw: dict[str, Any]) -> LMProfile:
    (
        api_base,
        model,
        request_kwargs,
        supported_mode,
        ignore_unsupported,
        lm_transport,
    ) = parse_lm_config(
        raw,
        default_api_base=DEFAULT_API_BASE,
        default_model=DEFAULT_MODEL,
        default_temperature=1.0,
        default_max_tokens=None,
    )
    api_key, api_key_env = parse_lm_auth_config(raw)
    return LMProfile(
        api_base=api_base,
        model=model,
        request_kwargs=request_kwargs,
        supported_parameter_mode=supported_mode,
        ignore_unsupported_parameters=ignore_unsupported,
        api_key=api_key,
        api_key_env=api_key_env,
        lm_transport=lm_transport,
    )


def load_lm_profile(path: Path) -> LMProfile:
    resolved_path = Path(path).expanduser().resolve()
    raw = load_runtime_toml(resolved_path)
    return _parse_lm_profile(raw)


def _resolve_lm_from_toml(
    raw: dict[str, Any],
    *,
    ref_key: str,
    inline_key: str,
    base_dir: Path,
    required: bool,
) -> LMProfile | None:
    profile_ref = raw.get(ref_key)
    inline = raw.get(inline_key)

    if profile_ref is not None and inline is not None:
        raise ValueError(f"Cannot specify both {ref_key!r} and [{inline_key}] block.")

    if profile_ref is not None:
        if not isinstance(profile_ref, (str, Path)):
            raise ValueError(f"{ref_key} must be a string path or profile name.")
        profile_path = resolve_lm_profile_reference(profile_ref, base_dir=base_dir)
        return load_lm_profile(profile_path)

    if inline is not None:
        if not isinstance(inline, dict):
            raise ValueError(f"[{inline_key}] must be a table.")
        return _parse_lm_profile({"lm": inline})

    if required:
        raise ValueError(
            f'Main LM must be specified via {ref_key} = "..." '
            f"or a [{inline_key}] block."
        )
    return None


def _parse_workload_spec(raw: dict[str, Any], *, base_dir: Path) -> WorkloadSpec:
    workload_raw = raw.get("workload")
    if isinstance(workload_raw, dict):
        name = str(workload_raw.get("name", "")).strip()
        options_raw = workload_raw.get("options", {})
        task_limit = int(workload_raw.get("task_limit", raw.get("task_limit", 1)))
    elif isinstance(workload_raw, str):
        name = workload_raw.strip()
        options_raw = raw.get("workload_options", {})
        task_limit = int(raw.get("task_limit", 1))
    else:
        raise ValueError(
            "workload must be specified as a string or table with a 'name'."
        )

    if not name:
        raise ValueError("workload name is required and must be non-empty.")
    if task_limit < 0:
        raise ValueError("task_limit must be >= 0")

    options: dict[str, Any] = {}
    if isinstance(options_raw, dict):
        for key, value in options_raw.items():
            if isinstance(value, str) and (key.endswith("_path") or key == "path"):
                options[key] = str(resolve_path(value, base_dir))
            else:
                options[key] = value

    return WorkloadSpec(name=name, options=options, task_limit=task_limit)


def _parse_repl_spec(raw: dict[str, Any]) -> ReplSpec:
    repl_raw = raw.get("repl")
    if repl_raw is None:
        return ReplSpec()
    if not isinstance(repl_raw, dict):
        raise ValueError("[repl] must be a table.")
    return ReplSpec(
        backend=str(repl_raw.get("backend", "docker")),
        docker_image=str(repl_raw.get("docker_image", "python:3.14-slim")),
    )


def load_bench_run_config(path: Path) -> BenchRunConfig:
    resolved_path = Path(path).expanduser().resolve()
    raw = load_runtime_toml(resolved_path, path_fields=("log_dir",))
    base_dir = resolved_path.parent

    workload = _parse_workload_spec(raw, base_dir=base_dir)

    lm = _resolve_lm_from_toml(
        raw,
        ref_key="lm_profile",
        inline_key="lm",
        base_dir=base_dir,
        required=True,
    )
    assert lm is not None  # required=True guarantees this
    sub_lm = _resolve_lm_from_toml(
        raw,
        ref_key="sub_lm_profile",
        inline_key="sub_lm",
        base_dir=base_dir,
        required=False,
    )

    log_dir_raw = str(raw.get("log_dir", str(DEFAULT_LOG_DIR)))
    log_dir = resolve_path(log_dir_raw, base_dir)

    adapter_mode = normalize_adapter_mode(raw.get("adapter_mode"))
    seed = int(raw.get("seed", 1))
    max_iterations = int(raw.get("max_iterations", 100))
    max_llm_calls = int(raw.get("max_llm_calls", 200))

    return BenchRunConfig(
        log_dir=log_dir,
        workload=workload,
        lm=lm,
        sub_lm=sub_lm,
        adapter_mode=adapter_mode,
        seed=seed,
        max_iterations=max_iterations,
        max_llm_calls=max_llm_calls,
        repl=_parse_repl_spec(raw),
    )


__all__ = [
    "BenchRunConfig",
    "DEFAULT_CONFIG_DIR",
    "DEFAULT_LOG_DIR",
    "LMProfile",
    "ReplSpec",
    "WorkloadSpec",
    "load_bench_run_config",
    "load_lm_profile",
    "resolve_lm_profile_path",
    "resolve_lm_profile_reference",
]
