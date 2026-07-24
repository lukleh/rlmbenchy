from __future__ import annotations

import os
from pathlib import Path

import pytest

from rlmbenchy.runtime_config import BUNDLED_LM_PROFILES_DIR, load_runtime_toml
from rlmbenchy.workbench.config import (
    BenchRunConfig,
    LMProfile,
    ReplSpec,
    WorkloadSpec,
    load_bench_run_config,
    load_lm_profile,
    resolve_lm_profile_path,
)


def test_load_project_env_discovers_dotenv_from_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from rlmbenchy import runtime_config

    (tmp_path / ".env").write_text(
        "RLMBENCHY_TEST_DOTENV=loaded-from-cwd\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RLMBENCHY_TEST_DOTENV", raising=False)
    monkeypatch.setattr(runtime_config, "_ENV_LOADED", False)

    runtime_config.load_project_env()

    assert os.environ["RLMBENCHY_TEST_DOTENV"] == "loaded-from-cwd"


def test_load_lm_profile_returns_lm_profile(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(
        (
            "[lm]\n"
            'api_base = "https://openrouter.ai/api/v1"\n'
            'model = "openrouter/openai/gpt-oss-20b"\n'
            "\n"
            "[lm.request]\n"
            "temperature = 0.3\n"
        ),
        encoding="utf-8",
    )

    profile = load_lm_profile(profile_path)

    assert isinstance(profile, LMProfile)
    assert profile.api_base == "https://openrouter.ai/api/v1"
    assert profile.model == "openrouter/openai/gpt-oss-20b"
    assert profile.request_kwargs["temperature"] == 0.3


def test_load_bench_run_config_with_inline_lm(tmp_path: Path) -> None:
    config_path = tmp_path / "run.toml"
    config_path.write_text(
        (
            'log_dir = "./logs"\n'
            "\n"
            "[workload]\n"
            'name = "tasks_v0"\n'
            "task_limit = 5\n"
            "\n"
            "[lm]\n"
            'api_base = "https://openrouter.ai/api/v1"\n'
            'model = "openrouter/openai/gpt-oss-20b"\n'
            "\n"
            "[lm.request]\n"
            "temperature = 0.0\n"
        ),
        encoding="utf-8",
    )

    config = load_bench_run_config(config_path)

    assert isinstance(config, BenchRunConfig)
    assert config.workload.name == "tasks_v0"
    assert config.workload.task_limit == 5
    assert config.workload.options == {}
    assert config.lm.model == "openrouter/openai/gpt-oss-20b"
    assert config.sub_lm is None
    assert config.log_dir == (tmp_path / "logs").resolve()


def test_load_bench_run_config_with_referenced_lm_profile(tmp_path: Path) -> None:
    profile_path = tmp_path / "main.toml"
    profile_path.write_text(
        (
            "[lm]\n"
            'api_base = "https://openrouter.ai/api/v1"\n'
            'model = "openrouter/openai/gpt-oss-20b"\n'
        ),
        encoding="utf-8",
    )
    sub_profile_path = tmp_path / "sub.toml"
    sub_profile_path.write_text(
        (
            "[lm]\n"
            'api_base = "https://chatgpt.com/backend-api/codex"\n'
            'model = "chatgpt/gpt-5.6-terra"\n'
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "run.toml"
    config_path.write_text(
        (
            'workload = "tasks_v0"\n'
            "task_limit = 2\n"
            'lm_profile = "./main.toml"\n'
            'sub_lm_profile = "./sub.toml"\n'
            "\n"
            "[repl]\n"
            'backend = "local"\n'
        ),
        encoding="utf-8",
    )

    config = load_bench_run_config(config_path)

    assert config.workload.name == "tasks_v0"
    assert config.workload.task_limit == 2
    assert config.lm.model == "openrouter/openai/gpt-oss-20b"
    assert config.sub_lm is not None
    assert config.sub_lm.model == "chatgpt/gpt-5.6-terra"
    assert config.repl.backend == "local"


def test_load_bench_run_config_rejects_both_inline_and_reference(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "main.toml"
    profile_path.write_text(
        '[lm]\napi_base = "x"\nmodel = "y"\n',
        encoding="utf-8",
    )
    config_path = tmp_path / "run.toml"
    config_path.write_text(
        (
            'workload = "tasks_v0"\n'
            'lm_profile = "./main.toml"\n'
            "\n"
            "[lm]\n"
            'api_base = "x"\n'
            'model = "y"\n'
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Cannot specify both"):
        load_bench_run_config(config_path)


def test_load_bench_run_config_with_inline_main_and_inline_sub(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "run.toml"
    config_path.write_text(
        (
            'workload = "tasks_v0"\n'
            "\n"
            "[lm]\n"
            'api_base = "https://openrouter.ai/api/v1"\n'
            'model = "openrouter/openai/gpt-oss-20b"\n'
            "\n"
            "[sub_lm]\n"
            'api_base = "https://chatgpt.com/backend-api/codex"\n'
            'model = "chatgpt/gpt-5.6-terra"\n'
        ),
        encoding="utf-8",
    )

    config = load_bench_run_config(config_path)

    assert config.lm.model == "openrouter/openai/gpt-oss-20b"
    assert config.sub_lm is not None
    assert config.sub_lm.model == "chatgpt/gpt-5.6-terra"


def test_load_bench_run_config_with_inline_main_and_reference_sub(
    tmp_path: Path,
) -> None:
    sub_profile_path = tmp_path / "sub.toml"
    sub_profile_path.write_text(
        (
            "[lm]\n"
            'api_base = "https://chatgpt.com/backend-api/codex"\n'
            'model = "chatgpt/gpt-5.6-terra"\n'
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "run.toml"
    config_path.write_text(
        (
            'workload = "tasks_v0"\n'
            'sub_lm_profile = "./sub.toml"\n'
            "\n"
            "[lm]\n"
            'api_base = "https://openrouter.ai/api/v1"\n'
            'model = "openrouter/openai/gpt-oss-20b"\n'
        ),
        encoding="utf-8",
    )

    config = load_bench_run_config(config_path)

    assert config.lm.model == "openrouter/openai/gpt-oss-20b"
    assert config.sub_lm is not None
    assert config.sub_lm.model == "chatgpt/gpt-5.6-terra"


def test_load_bench_run_config_with_reference_main_and_inline_sub(
    tmp_path: Path,
) -> None:
    main_profile_path = tmp_path / "main.toml"
    main_profile_path.write_text(
        (
            "[lm]\n"
            'api_base = "https://openrouter.ai/api/v1"\n'
            'model = "openrouter/openai/gpt-oss-20b"\n'
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "run.toml"
    config_path.write_text(
        (
            'workload = "tasks_v0"\n'
            'lm_profile = "./main.toml"\n'
            "\n"
            "[sub_lm]\n"
            'api_base = "https://chatgpt.com/backend-api/codex"\n'
            'model = "chatgpt/gpt-5.6-terra"\n'
        ),
        encoding="utf-8",
    )

    config = load_bench_run_config(config_path)

    assert config.lm.model == "openrouter/openai/gpt-oss-20b"
    assert config.sub_lm is not None
    assert config.sub_lm.model == "chatgpt/gpt-5.6-terra"


def test_load_bench_run_config_rejects_both_inline_and_reference_for_sub_lm(
    tmp_path: Path,
) -> None:
    sub_profile_path = tmp_path / "sub.toml"
    sub_profile_path.write_text(
        '[lm]\napi_base = "x"\nmodel = "y"\n',
        encoding="utf-8",
    )
    config_path = tmp_path / "run.toml"
    config_path.write_text(
        (
            'workload = "tasks_v0"\n'
            'sub_lm_profile = "./sub.toml"\n'
            "\n"
            "[lm]\n"
            'api_base = "main_base"\n'
            'model = "main_model"\n'
            "\n"
            "[sub_lm]\n"
            'api_base = "x"\n'
            'model = "y"\n'
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Cannot specify both"):
        load_bench_run_config(config_path)


def test_load_bench_run_config_requires_lm(tmp_path: Path) -> None:
    config_path = tmp_path / "run.toml"
    config_path.write_text('workload = "tasks_v0"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="Main LM must be specified"):
        load_bench_run_config(config_path)


def test_bench_run_config_has_sensible_defaults(tmp_path: Path) -> None:
    lm = LMProfile(
        api_base="https://openrouter.ai/api/v1",
        model="openrouter/openai/gpt-oss-20b",
        request_kwargs={"temperature": 0.0},
        supported_parameter_mode="off",
        ignore_unsupported_parameters=frozenset(),
    )
    config = BenchRunConfig(
        log_dir=tmp_path / "logs",
        workload=WorkloadSpec(name="tasks_v0", options={}, task_limit=1),
        lm=lm,
    )

    assert config.sub_lm is None
    assert config.adapter_mode == "auto"
    assert config.seed == 1
    assert config.max_iterations == 100
    assert config.max_llm_calls == 200
    assert config.repl == ReplSpec()
    assert config.repl.backend == "docker"
    assert config.repl.docker_image == "python:3.14-slim"


def test_load_bench_run_config_expands_env_vars_in_log_dir(
    monkeypatch, tmp_path: Path
) -> None:
    log_root = tmp_path / "env-logs"
    monkeypatch.setenv("RLM_TEST_LOG_ROOT", str(log_root))
    config_path = tmp_path / "run.toml"
    config_path.write_text(
        (
            'workload = "tasks_v0"\n'
            'lm_profile = "model-chatgpt-gpt-5.6-terra_low"\n'
            'log_dir = "${RLM_TEST_LOG_ROOT}/run-logs"\n'
        ),
        encoding="utf-8",
    )

    config = load_bench_run_config(config_path)

    assert config.log_dir == (log_root / "run-logs").resolve()


def test_load_bench_run_config_expands_short_env_var_in_log_dir(
    monkeypatch, tmp_path: Path
) -> None:
    log_root = tmp_path / "short-env-logs"
    monkeypatch.setenv("RLM_TEST_LOG_ROOT_SHORT", str(log_root))
    config_path = tmp_path / "run.toml"
    config_path.write_text(
        (
            'workload = "tasks_v0"\n'
            'lm_profile = "model-chatgpt-gpt-5.6-terra_low"\n'
            'log_dir = "$RLM_TEST_LOG_ROOT_SHORT/run-logs"\n'
        ),
        encoding="utf-8",
    )

    config = load_bench_run_config(config_path)

    assert config.log_dir == (log_root / "run-logs").resolve()


def test_load_bench_run_config_expands_tilde_in_log_dir(
    monkeypatch, tmp_path: Path
) -> None:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    config_path = tmp_path / "run.toml"
    config_path.write_text(
        (
            'workload = "tasks_v0"\n'
            'lm_profile = "model-chatgpt-gpt-5.6-terra_low"\n'
            'log_dir = "~/rlm-logs"\n'
        ),
        encoding="utf-8",
    )

    config = load_bench_run_config(config_path)

    assert config.log_dir == (home_dir / "rlm-logs").resolve()


def test_load_bench_run_config_resolves_relative_log_dir_from_config_dir(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    config_path = config_dir / "run.toml"
    config_path.write_text(
        (
            'workload = "tasks_v0"\n'
            'lm_profile = "model-chatgpt-gpt-5.6-terra_low"\n'
            'log_dir = "./logs"\n'
        ),
        encoding="utf-8",
    )

    config = load_bench_run_config(config_path)

    assert config.log_dir == (config_dir / "logs").resolve()


def test_load_bench_run_config_accepts_absolute_log_dir(tmp_path: Path) -> None:
    absolute = tmp_path / "absolute-logs"
    config_path = tmp_path / "run.toml"
    config_path.write_text(
        (
            'workload = "tasks_v0"\n'
            'lm_profile = "model-chatgpt-gpt-5.6-terra_low"\n'
            f'log_dir = "{absolute}"\n'
        ),
        encoding="utf-8",
    )

    config = load_bench_run_config(config_path)

    assert config.log_dir == absolute.resolve()


def test_resolve_lm_profile_path_accepts_names_with_dots() -> None:
    resolved = resolve_lm_profile_path("model-chatgpt-gpt-5.6-terra_low")

    assert (
        resolved
        == (BUNDLED_LM_PROFILES_DIR / "model-chatgpt-gpt-5.6-terra_low.toml").resolve()
    )


def test_load_runtime_toml_user_file_fully_replaces_bundled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The user override must replace the bundled profile entirely —
    # bundled keys not present in the user file must NOT carry over.
    from rlmbenchy import runtime_config

    bundled_root = tmp_path / "bundled" / "lm_profiles"
    user_root = tmp_path / "user" / "lm_profiles"
    bundled_root.mkdir(parents=True)
    user_root.mkdir(parents=True)

    bundled_path = bundled_root / "example.toml"
    bundled_path.write_text(
        (
            "[lm]\n"
            'api_base = "https://bundled.example/api"\n'
            'model = "bundled/model"\n'
            "\n"
            "[lm.request]\n"
            "temperature = 0.1\n"
        ),
        encoding="utf-8",
    )
    user_path = user_root / "example.toml"
    user_path.write_text(
        ('[lm]\napi_base = "https://user.example/api"\nmodel = "user/model"\n'),
        encoding="utf-8",
    )

    monkeypatch.setattr(runtime_config, "BUNDLED_LM_PROFILES_DIR", bundled_root)
    monkeypatch.setattr(runtime_config, "user_lm_profiles_dir", lambda: user_root)

    raw = load_runtime_toml(bundled_path)

    assert raw["lm"]["api_base"] == "https://user.example/api"
    assert raw["lm"]["model"] == "user/model"
    # Bundled-only keys do NOT leak through.
    assert "request" not in raw["lm"]


def test_load_runtime_toml_uses_bundled_when_no_user_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from rlmbenchy import runtime_config

    bundled_root = tmp_path / "bundled" / "lm_profiles"
    user_root = tmp_path / "user" / "lm_profiles"
    bundled_root.mkdir(parents=True)
    user_root.mkdir(parents=True)

    bundled_path = bundled_root / "example.toml"
    bundled_path.write_text(
        ('[lm]\napi_base = "https://bundled.example/api"\nmodel = "bundled/model"\n'),
        encoding="utf-8",
    )

    monkeypatch.setattr(runtime_config, "BUNDLED_LM_PROFILES_DIR", bundled_root)
    monkeypatch.setattr(runtime_config, "user_lm_profiles_dir", lambda: user_root)

    raw = load_runtime_toml(bundled_path)

    assert raw["lm"]["api_base"] == "https://bundled.example/api"
    assert raw["lm"]["model"] == "bundled/model"
