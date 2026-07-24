# Review Prompt Additions

Use these repo-specific notes when drafting or running a review prompt for this
project.

## Project Snapshot

- The main product surface is the reusable RLM runtime in `rlmbenchy/rlm/`,
  with same-repo workbench wrappers under
  `rlmbenchy/workbench/`.
- The active runtime model is: prompt an LLM for reasoning plus code, execute
  that code in a persistent REPL, and stop only when executed code calls
  `SUBMIT(...)`.
- `llm_query(prompt)` is a bounded sub-LLM helper exposed inside the REPL. It
  should be treated as a separate actor family from main-LLM calls.
- Visualizers, tests, and offline tooling are expected to consume the canonical
  telemetry JSONL stream rather than sidecar reports or repaired legacy payloads.

## Authoritative Docs

- `docs/SPEC.md`: intent, invariants, named roles, soundness check.
- `docs/ARCHITECTURE.md`: one-page orientation — flow and layer map.
- `docs/RLM.md`: RLM loop algorithm and divergences from the paper.
- `docs/WORKLOADS.md`: workload contract (tasks, bundles, loaders).
- `docs/LOGS.md`: telemetry log event contract and invariants.

## Chosen Architecture To Assume

- The telemetry log is the canonical record of a run.
- One JSONL file represents one run and should be reconstructable from the
  event stream alone.
- Telemetry rows should use the canonical envelope and taxonomy from
  `docs/LOGS.md`.
- Raw payloads belong in `data`, measurements in `stats`, and derived rollups
  in `summary`.
- Explicit lineage matters: `run_id`, `task_id`, `step_index`, and `call_id`
  should not be dropped, guessed late, or overloaded.
- The project is intentionally pruning legacy log formats and compatibility
  shims. Reintroducing repair heuristics or dual-schema handling is usually a
  regression unless the change explicitly asks for migration support.

## High-Value Review Focus

- Behavioral regressions in the RLM loop: step progression, persistent REPL
  state, `SUBMIT(...)` handling, and termination behavior.
- Event-schema drift: wrong event names, missing lineage fields, flattened
  fields that should be nested, or data placed in the wrong `data`/`stats`/
  `summary` bucket.
- Accounting mistakes: step/task/run counters, token totals, elapsed timing,
  pricing, and consistency between emitted events and rollup summaries.
- Hidden compatibility code: alias backfills, legacy field fallbacks, old event
  types, or viewer repair logic that assumes pre-spec payloads.
- Visualizer correctness: the TUI and web views should materialize the telemetry
  stream directly, not rely on sidecar matching or alternate report formats.
- Missing or stale tests when behavior changes affect the runtime, logging,
  normalizers, or visualizers.

## Lower-Value Feedback

- Relitigating the broader architecture when the change is an incremental fix
  inside the chosen runtime.
- Asking for backward compatibility with removed mixed-schema logs unless the
  task explicitly requires it.
- Preferring broad rewrites over targeted fixes without a concrete correctness
  or maintainability win.

## Verification Expectations

- For Python behavior changes, expect targeted `pytest` coverage and note if
  only part of the suite was run.
- For logging and visualizer changes, reviewers should check both producer and
  consumer sides of the telemetry stream.
- For web visualizer changes, expect TypeScript validation such as:
  `npm --prefix rlmbenchy/visualizers/web run typecheck` and
  `npm --prefix rlmbenchy/visualizers/web run build`.

## Useful Paths

- `rlmbenchy/rlm/`
- `rlmbenchy/workbench/config.py`
- `rlmbenchy/workbench/runner.py`
- `rlmbenchy/workbench/cli.py`
- `rlmbenchy/logger/`
- `rlmbenchy/visualizers/`
- `tests/`
