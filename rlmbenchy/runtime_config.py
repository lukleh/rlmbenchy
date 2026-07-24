"""Helpers for merged runtime config, secrets, and XDG override lookup."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from dotenv import find_dotenv, load_dotenv

from rlmbenchy.resources import resource_path
from rlmbenchy.runtime_paths import resolve_runtime_paths

BUNDLED_LM_PROFILES_DIR = resource_path("rlmbenchy.resources", "lm_profiles")
_SECRET_ENV_PATHS: dict[str, tuple[str, ...]] = {
    "OPENROUTER_API_KEY": ("providers", "openrouter", "api_key"),
    "HF_TOKEN": ("providers", "huggingface", "token"),
}
_ENV_LOADED = False


def load_project_env() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path, override=False)
    _ENV_LOADED = True


def user_lm_profiles_dir() -> Path:
    return resolve_runtime_paths().lm_profiles_dir


def secrets_file_path() -> Path:
    return resolve_runtime_paths().secrets_file


def transcripts_config_file() -> Path:
    return resolve_runtime_paths().transcripts_config_file


def default_transcripts_root() -> Path:
    return resolve_runtime_paths().transcripts_root


def default_transcripts_tasks_path() -> Path:
    return resolve_runtime_paths().transcripts_tasks_path


def resolve_path(raw_path: str, base_dir: Path) -> Path:
    path = Path(os.path.expandvars(str(raw_path))).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def normalize_path_fields(
    raw: dict[str, Any],
    base_dir: Path,
    path_fields: tuple[str, ...],
) -> dict[str, Any]:
    normalized = dict(raw)
    for key in path_fields:
        value = normalized.get(key)
        if isinstance(value, str):
            normalized[key] = str(resolve_path(value, base_dir))
    return normalized


def load_raw_toml(
    path: Path,
    *,
    path_fields: tuple[str, ...] = (),
    allow_missing: bool = False,
) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve()
    try:
        raw_text = resolved.read_text(encoding="utf-8")
    except FileNotFoundError:
        if allow_missing:
            return {}
        raise
    try:
        raw = tomllib.loads(raw_text)
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeError(f"Invalid TOML in {resolved}") from exc

    if not isinstance(raw, dict):
        return {}

    return normalize_path_fields(raw, resolved.parent, path_fields)


def _relative_to(path: Path, root: Path) -> Path | None:
    try:
        return path.resolve().relative_to(root.resolve())
    except ValueError:
        return None


def _user_override_path(path: Path) -> Path | None:
    """Return the paired user override for an LM profile path, if any.

    Only LM profile files support local overrides. A file under
    ``BUNDLED_LM_PROFILES_DIR`` or the user profiles dir maps to its
    counterpart under the user profiles dir. Any other path has no
    override and is loaded as-is.
    """
    resolved = path.expanduser().resolve()
    user_root = user_lm_profiles_dir()
    for root in (BUNDLED_LM_PROFILES_DIR, user_root):
        rel = _relative_to(resolved, root)
        if rel is not None:
            return user_root / rel
    return None


def load_runtime_toml(
    path: Path,
    *,
    path_fields: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Load a runtime TOML with "user fully replaces bundled by name".

    If a user override exists at ``<user_lm_profiles_dir>/<name>``, load it
    and return its full contents. Otherwise load the given path. No
    partial/recursive merge: the user file wins entirely.
    """
    resolved = Path(path).expanduser().resolve()
    user_path = _user_override_path(resolved)
    if user_path is not None and user_path.exists() and user_path != resolved:
        return load_raw_toml(user_path, path_fields=path_fields)
    return load_raw_toml(resolved, path_fields=path_fields)


def resolve_named_lm_profile_path(raw: str | Path) -> Path:
    candidate = Path(raw).expanduser()
    if candidate.exists():
        return candidate.resolve()

    name = str(raw).strip()
    for root in (user_lm_profiles_dir(), BUNDLED_LM_PROFILES_DIR):
        config_candidate = root / name
        if config_candidate.exists():
            return config_candidate.resolve()
        if not config_candidate.name.endswith(".toml"):
            toml_candidate = config_candidate.with_name(f"{config_candidate.name}.toml")
            if toml_candidate.exists():
                return toml_candidate.resolve()

    return candidate.resolve()


def load_transcripts_config(path: Path | None = None) -> dict[str, Any]:
    return load_raw_toml(
        Path(path or transcripts_config_file()),
        path_fields=("root", "tasks_path"),
        allow_missing=True,
    )


def load_secrets_toml(path: Path | None = None) -> dict[str, Any]:
    load_project_env()
    resolved = Path(path or secrets_file_path()).expanduser().resolve()
    try:
        raw = tomllib.loads(resolved.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeError(f"Invalid TOML in secrets file: {resolved}") from exc
    if isinstance(raw, dict):
        return raw
    return {}


def _lookup_nested_secret(payload: dict[str, Any], path: tuple[str, ...]) -> str | None:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    value = str(current or "").strip()
    return value or None


def resolve_secret_for_env(env_name: str, *, explicit: str | None = None) -> str | None:
    load_project_env()

    explicit_value = str(explicit or "").strip()
    if explicit_value:
        return explicit_value

    env_value = str(os.getenv(env_name) or "").strip()
    if env_value:
        return env_value

    secret_path = _SECRET_ENV_PATHS.get(str(env_name).strip())
    if secret_path is None:
        return None
    return _lookup_nested_secret(load_secrets_toml(), secret_path)


def resolve_openrouter_api_key(api_key: str | None = None) -> str | None:
    return resolve_secret_for_env("OPENROUTER_API_KEY", explicit=api_key)


def resolve_huggingface_token(token: str | None = None) -> str | None:
    return resolve_secret_for_env("HF_TOKEN", explicit=token)


__all__ = [
    "BUNDLED_LM_PROFILES_DIR",
    "default_transcripts_root",
    "default_transcripts_tasks_path",
    "load_transcripts_config",
    "load_project_env",
    "load_raw_toml",
    "load_runtime_toml",
    "load_secrets_toml",
    "normalize_path_fields",
    "resolve_huggingface_token",
    "resolve_named_lm_profile_path",
    "resolve_openrouter_api_key",
    "resolve_path",
    "resolve_secret_for_env",
    "secrets_file_path",
    "transcripts_config_file",
    "user_lm_profiles_dir",
]
