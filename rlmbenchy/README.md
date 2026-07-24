# rlmbenchy Package Layout

`rlmbenchy` has two main layers:

- `rlmbenchy.rlm`: the canonical runtime library API
- the rest of the package: repo-local runner, logging, and viewer code built around that API

If you are building on top of this project from another codebase, import from `rlmbenchy.rlm`.

## Structure

```text
rlmbenchy/
  cli.py                        # main CLI: run, workloads, logs, paths
  rlm/                          # canonical reusable RLM runtime
  workbench/config.py           # run config + LM profile resolution
  workbench/runner.py           # workload execution wrappers on top of rlm.run_task
  visualizers/                  # web and tui viewers
  logger/                       # telemetry logging, shared projection, and CLI log inspection helpers
  resources/lm_profiles/          # bundled LM profile templates
  ~/.config/lukleh/rlmbenchy/   # user overrides and runtime config
  ~/.local/state/lukleh/rlmbenchy/  # runtime logs
```

## Entry Commands

```bash
uv run rlmbenchy paths
uv run rlmbenchy run --config config/run_profiles/smoke-3-tasks-v0-oss.toml --task-id <task_id>
uv run rlmbenchy workloads list
uv run rlmbenchy workloads tasks tasks_v0 --limit 3
uv run rlmbenchy workloads task tasks_v0 <task_id>
uv run rlmbenchy run --config config/run_profiles/smoke-3-tasks-v0-oss.toml
uv run rlmbenchy logs latest
uv run rlmbenchy logs stats
uv run rlmbenchy logs tree
uv run rlmbenchy logs show --only-failures
```

Default runtime paths:

- config and overrides: `~/.config/lukleh/rlmbenchy/`
- state and logs: `~/.local/state/lukleh/rlmbenchy/`
- cache: `~/.cache/lukleh/rlmbenchy/`

LM profile lookups search user overrides under `~/.config/lukleh/rlmbenchy/lm_profiles/` before falling back to profiles bundled in the installed package.

## Current Surface

Use these as the main entrypoints:

- `rlmbenchy.rlm` for reusable runtime imports such as `RLM`, `RLMRunConfig`, `build_task_signature(...)`, and `run_task(...)`
- `rlmbenchy.workbench` for repo-local config/workload execution
- `rlmbenchy.visualizers.web` and `rlmbenchy.visualizers.tui` for the two log viewers
- `rlmbenchy.logger.api` for stable telemetry-log reads
- `rlmbenchy logs ...` for CLI log inspection
