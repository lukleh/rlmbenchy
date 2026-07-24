# Simplification Plan

## Purpose

This document turns the current repo analysis into a concrete simplification
plan. The goal is not to "make everything smaller" at any cost; the goal is to
remove accidental complexity while preserving the parts that are genuinely
required by the project:

- the RLM loop
- the persistent REPL runtime
- the workload contract
- the JSONL telemetry log contract

The main principle is to simplify the edges before touching the core loop.

## Current Read

The core RLM path is reasonably focused:

- `rlmbenchy/rlm/rlm.py`
- `rlmbenchy/rlm/executor.py`
- `rlmbenchy/rlm/repl.py`

Most accidental complexity sits outside that core:

- duplicated CLI surfaces and mode validation
- LM response extraction and callback logging glue
- multi-layer log normalization and viewer formatting
- config composition and overlay rules
- test files that mirror historical seams more than subsystem boundaries

## Guiding Rules

1. Keep one canonical run surface.
2. Keep one owner for each transformation boundary.
3. Prefer explicit rules over flexible generic merge behavior.
4. Remove indirection before rewriting the algorithm.
5. Do not break the telemetry log contract casually.
6. Delay framework replacement decisions until local cleanup is done.

## Target End State

The project should converge toward the following shape:

- one obvious way to start a run
- one obvious way to normalize a log file
- one obvious boundary for provider-response parsing
- one obvious config override model
- tests grouped by subsystem

## Phase 1: Collapse Run Entry Points

### Goal

Make `--config` the canonical way to run workloads and remove the current
"Mode 1 vs Mode 2" split.

### Why

The repo already leans config-first:

- `README.md` documents `uv run rlmbenchy run --config <run-config.toml>`
- `justfile` uses `run --config ...`
- `config/run_profiles/` already contains real run-profile examples

The current split creates extra validation and forwarding logic in:

- `rlmbenchy/cli.py`
- `rlmbenchy/workbench/cli.py`

### Changes

- Make the top-level CLI own the `run` command directly.
- Remove the duplicate argument surface in `rlmbenchy/workbench/cli.py`.
- Remove the "`--config` XOR `--lm-profile + --workload`" validation path.
- Keep direct flag-based runs only as a temporary compatibility shim if needed.
- If a compatibility shim is kept, it should synthesize a config object and
  call the same implementation as `--config`.

### Files

- `rlmbenchy/cli.py`
- `rlmbenchy/workbench/cli.py`
- `README.md`
- `tests/test_rlmbenchy_cli.py`
- `tests/test_workbench_task_groups.py`

### Acceptance Criteria

- One parser owns the `run` command.
- No argv-forwarding layer remains.
- No mode-mutex logic remains.
- Documentation shows one canonical run workflow.

### Risk

Medium. This changes a user-facing entrypoint, but the existing repo shape
already supports a config-first transition well.

## Phase 2: Shrink LM Response Extraction Behind a Small Adapter Boundary

### Goal

Replace the current large helper collection in
`rlmbenchy/rlm/_response_extraction.py` with a smaller, more explicit adapter
boundary used by logging.

### Why

Today the logging callback imports many response-shape helpers directly from
`_response_extraction.py`. Provider and transport knowledge is spread across a
large module instead of concentrated behind a small API.

### Changes

- Define a compact interface for logging-oriented extraction:
  `extract_usage()`, `extract_cost()`, `extract_finish_reason()`,
  `extract_preview()`, `extract_reasoning()`, and `extract_message()`.
- Split provider- or transport-aware handling into a few adapters rather than a
  long list of mostly single-use helpers.
- Keep truly generic utilities separate:
  `response_to_dict`, redaction, and safe numeric coercion.
- Update `LMLoggingCallback` to depend on the adapter boundary, not many helper
  functions.

### Files

- `rlmbenchy/rlm/_response_extraction.py`
- `rlmbenchy/rlm/runtime.py`
- `rlmbenchy/litellm_responses.py`
- tests currently covering extraction behavior

### Acceptance Criteria

- `LMLoggingCallback` imports a small extraction API.
- Provider-specific logic is concentrated in a few clear places.
- Existing token/cost/preview logging behavior stays covered by tests.

### Risk

Medium to high. This touches logging correctness and provider-shape handling.

## Phase 3: Make Projection the Single Log-Normalization Owner

### Goal

Remove unnecessary normalization indirection and make one module clearly own log
projection.

### Why

The current shape is harder to follow than it needs to be:

- `logger.projection` builds normalized run data
- `visualizers.normalize` wraps that projection
- `logger.viewer` imports through the visualizer layer and adds more payload
  shaping

This is extra layering without a strong ownership boundary.

### Changes

- Make `rlmbenchy/logger/projection.py` the direct owner of `normalize_run`.
- Remove `rlmbenchy/visualizers/normalize.py` as a shim, or reduce it to a
  direct re-export only if a compatibility path is temporarily needed.
- Have both viewers and log CLI utilities import from the projection owner.
- Deduplicate small helper patterns such as `_safe_int` and `_snippet` where
  practical.

### Files

- `rlmbenchy/logger/projection.py`
- `rlmbenchy/logger/viewer.py`
- `rlmbenchy/visualizers/normalize.py`
- `rlmbenchy/visualizers/tui/log_viewer.py`
- `rlmbenchy/visualizers/web/server.py`

### Acceptance Criteria

- There is one obvious place to understand run normalization.
- Viewers format normalized data rather than own normalization indirection.
- The dependency direction becomes easier to explain.

### Risk

Low. This is mostly ownership cleanup.

## Phase 4: Simplify Config Overlay Rules

### Goal

Replace generic recursive config overlay behavior with a smaller, documented
override model.

### Why

The current paired bundled/user TOML merge is flexible, but the main practical
value appears to be local overrides such as secrets and request tweaks. Generic
recursive merge is more powerful than the documented use cases seem to require.

### Changes

- Choose one explicit override rule for LM profiles:
  user file fully overrides bundled file by name, or only a short allowlist of
  nested keys merges.
- Remove the current generic recursive merge unless real use cases justify it.
- Document the override model clearly in one short section.
- Keep secrets lookup logic separate from config composition logic.

### Files

- `rlmbenchy/runtime_config.py`
- `rlmbenchy/workbench/config.py`
- `rlmbenchy/resources/lm_profiles/README.md`
- `tests/test_runtime_config.py`

### Acceptance Criteria

- Override behavior fits in a short explanation.
- Tests describe one clear model rather than many permutations.
- The config loader becomes easier to reason about.

### Risk

Medium. This can change user-local override behavior.

## Phase 5: Reduce Logger Modes to One Primary Production Model

### Goal

Keep the logger focused on production logging and make auxiliary capture paths
explicitly optional.

### Why

`RLMLogger` currently combines:

- JSONL telemetry logging
- in-memory event capture
- callback emission for live display

The callback path is real runtime behavior, but in-memory trajectory capture is
more optional.

### Changes

- Keep disk logging and callback emission.
- Make in-memory capture optional rather than implicit if possible.
- Keep `get_trajectory()` only if it is a deliberate API, not an incidental side
  effect of logger internals.
- Avoid making tests the reason production objects keep extra state forever.

### Files

- `rlmbenchy/logger/rlm_logger.py`
- `rlmbenchy/workbench/runner.py`
- `rlmbenchy/rlm/executor.py`
- tests touching logger capture

### Acceptance Criteria

- The logger has one clear production responsibility.
- Optional capture behavior is explicit.
- Live display still works through the callback path.

### Risk

Low to medium.

## Phase 6: Split Mixed Test Files by Subsystem

### Goal

Make the test suite structure mirror the current architecture rather than old
implementation seams.

### Why

`tests/test_workbench_task_groups.py` currently mixes workload loading, CLI
behavior, runner flow, response extraction, and printer behavior. That makes the
file harder to maintain and obscures the true ownership boundaries in the code.

### Changes

- Split mixed files into focused modules, for example:
  `test_workloads_builtin.py`
  `test_workbench_cli.py`
  `test_workbench_runner.py`
  `test_response_extraction.py`
  `test_verbose_printer.py`
- Keep test names behavior-oriented.
- Move tests near the subsystem they actually validate.

### Files

- `tests/test_workbench_task_groups.py`
- related follow-on test modules

### Acceptance Criteria

- Each major subsystem has a focused test file.
- Removing or refactoring a seam does not require editing an unrelated grab-bag
  test module.

### Risk

Low.

## Phase 7: Re-evaluate DSPy Dependence

### Goal

Make an explicit architectural decision about how much DSPy the project wants to
carry.

### Why

DSPy currently shapes several surfaces:

- signature building
- callback integration
- adapters
- reasoning behavior, including a local monkey-patch

That may still be worth it, but it should be a deliberate choice rather than an
assumption.

### Changes

- Write a short decision memo before changing code.
- Compare two concrete options:
  keep DSPy but narrow its surface, or replace DSPy orchestration with thinner
  direct LM integration.
- Include migration cost, testing cost, and feature regressions in that memo.

### Files

- `rlmbenchy/rlm/reasoning.py`
- `rlmbenchy/rlm/signatures.py`
- `rlmbenchy/rlm/rlm.py`
- `rlmbenchy/rlm/executor.py`

### Acceptance Criteria

- The repo has an explicit decision, not drift.
- DSPy remains because it earns its keep, or it is reduced on purpose.

### Risk

High. This is not a first-pass cleanup.

## What Not to Do First

- Do not rewrite the RLM loop before simplifying the edges.
- Do not move `rlmbenchy/rlm/signatures.py` out of the library as an early
  cleanup. It is public API today and moving it first mostly redistributes DSPy
  coupling instead of removing it.
- Do not delete a viewer just to reduce file count. First simplify the shared
  normalization ownership.

## Recommended Order

1. Collapse run entrypoints around `--config`.
2. Shrink LM response extraction behind a smaller boundary.
3. Make projection the single normalization owner.
4. Simplify config overlay rules.
5. Reduce logger modes.
6. Split mixed test files.
7. Make an explicit DSPy decision.

## Delivery Strategy

Use small PRs or commits. Each phase should stand on its own and keep the suite
green.

Suggested execution strategy:

- Phase 1 as one change set.
- Phases 2 and 3 either separately or back-to-back if the logging boundary is
  already being touched.
- Phase 4 on its own because behavior changes are possible.
- Phase 5 and Phase 6 as cleanup after the bigger ownership shifts.
- Phase 7 only after the repo is locally simpler.

## Success Metrics

This plan is working if the repo trends toward the following outcomes:

- fewer duplicate parsers and forwarding layers
- fewer helper-heavy glue modules
- fewer tests that exist only to pin down accidental flexibility
- easier onboarding: a new reader can explain how a run starts, how a log is
  normalized, and where provider-shape handling lives
