# Repository Guidelines

## Git Workflow

- Never make changes directly in the primary checkout or on `main`. Before
  editing, create a dedicated branch in a linked worktree under the primary
  checkout's ignored `worktrees/` directory (for example,
  `worktrees/<task-name>`) and do all task work there. Do not place worktrees
  beside the repository at the same filesystem level.
- After validating the requested work, commit all task changes on the worktree
  branch. Do not leave completed work unstaged or uncommitted unless the user
  explicitly asks for that.

## Project Structure & Module Organization
`rlmbenchy/` is the main Python package. The canonical runtime lives under `rlm/`; repo-local runners and config loading live under `workbench/`; logging lives under `logger/`; CLI entrypoints are in `cli.py` and `__main__.py`; visualizers live in `visualizers/`. Workloads and dataset adapters live under `rlmbenchy/datahub/`. Tests are in `tests/` and usually mirror the feature area they cover. Shared TOML configs live in `config/`, current docs live in `docs/`, and generated artifacts belong in `outputs/`.

## Build, Test, and Development Commands
Use `uv` for Python workflows:

- `uv sync --dev` installs project and test dependencies into `.venv`.
- `uv run pytest` runs the full Python test suite.
- `uv run pytest tests/test_rlmbenchy_cli.py -q` runs a focused test file while iterating.
- `uv run python -m rlmbenchy run --config config/run_profiles/<profile>.toml` runs the workload defined in that run config.
- `uv run python -m rlmbenchy run --config config/run_profiles/smoke-2-check-adapter-matrix-oss.toml` runs the adapter comparison workload.
- `just web --port 8030` starts the web visualizer; `just tui` opens the TUI log viewer.
- `npm --prefix rlmbenchy/visualizers/web run typecheck` and `npm --prefix rlmbenchy/visualizers/web run build` validate the TypeScript viewer.

## Coding Style & Naming Conventions
Target Python 3.12+ and follow the existing typed style: 4-space indentation, explicit type hints, and `from __future__ import annotations` in new Python modules when practical. Use `snake_case` for modules, functions, tests, and TOML profile names; use `PascalCase` for classes and typed containers. In TypeScript, keep `camelCase` for values and `PascalCase` for interfaces/types. Match the surrounding import order and keep helpers small; add brief docstrings only where behavior is not obvious.

## Testing Guidelines
Add or update `pytest` coverage with every behavior change, especially for CLI flags, provider adapters, pipelines, and visualizers. Name files `test_<feature>.py` and test functions `test_<expected_behavior>()`. No coverage threshold is configured, so contributors should provide targeted automated tests instead of relying on manual checks alone.

## Commit & Pull Request Guidelines
Recent history uses short, imperative commit subjects such as `Fix visualizer trace iteration handling` and `Prune docs and remove top-level examples`. Keep commits focused on one behavior change and explain why in the body when needed. Pull requests should include a concise summary, linked task or issue, the commands you ran, and screenshots for web or TUI visualizer changes. Do not commit secrets from `.env`, generated files in `outputs/`, or private data under `rlmbenchy/datahub/private/`.
