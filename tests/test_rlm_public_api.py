from __future__ import annotations

import importlib

import pytest

import rlmbenchy.rlm as runtime_api


def test_rlm_public_api_exposes_runtime_surface_only() -> None:
    assert runtime_api.RLM.__name__ == "RLM"
    assert runtime_api.RLMRunConfig.__name__ == "RLMRunConfig"
    assert runtime_api.TaskRunResult.__name__ == "TaskRunResult"
    assert callable(runtime_api.run_task)
    assert callable(runtime_api.build_task_signature)
    assert callable(runtime_api.load_lm_profile)
    assert callable(runtime_api.resolve_lm_profile_path)
    assert callable(runtime_api.validate_supported_parameters_for_openrouter)
    assert runtime_api.LocalProcessReplRuntime.__name__ == "LocalProcessReplRuntime"

    for name in (
        "DEFAULT_CONFIG_PATH",
        "DEFAULT_LOG_DIR",
        "DEFAULT_WORKLOAD",
        "WorkbenchConfig",
        "load_config",
        "run_task_with_config",
        "run_task_from_config",
        "validate_supported_parameters",
    ):
        with pytest.raises(AttributeError):
            getattr(runtime_api, name)


def test_removed_adapters_package_is_not_part_of_public_surface() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("rlmbenchy.adapters")
