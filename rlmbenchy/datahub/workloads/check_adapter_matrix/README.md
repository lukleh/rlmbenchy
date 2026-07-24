# check_adapter_matrix

Small local workload used to sanity-check adapter behavior on simple,
deterministic prompts.
See `setup.md` for prerequisites and first-run setup.

## Data Location

- Source type: local checked-in JSON.
- Default file: `rlmbenchy/datahub/workloads/check_adapter_matrix/tasks.json`.
- Override: `options.tasks_path`.
- Paths are expanded and resolved as local filesystem paths.
- Explicit relative `tasks_path` values are resolved from the current working directory.

## Raw Task File Shape

The loader expects a JSON list of task objects.

```json
[
  {
    "task_id": "arith_01",
    "query": "Compute 17 + 26. Return only the number.",
    "expected": {"kind": "exact", "value": "43"}
  }
]
```

Supported row fields:

- `task_id`: optional task id
- `query`: prompt text
- `expected`: expected-answer payload used for scoring
- any additional keys: preserved into metadata

The checked-in file uses short exact-match and one-of answer contracts to
exercise model/adapter combinations.

## Loaded Task Shape

Each row becomes one `WorkloadTask` with:

- `id`: copied from `task_id`, or generated as `matrix_NNN`
- `inputs.question`
- `answer`: copied from `expected`
- `metadata`: any extra row fields

This workload has no tools.

## Task Id Audit Notes

Audit date: 2026-04-24.

- Source view audited: checked-in `tasks.json`.
- Rows audited: 14.
- Duplicate task ids found: 0.
- First observed ids: `arith_01`, `alpha_01`, `count_01`.
- Authored `task_id` values are treated as the task ids. Duplicate ids in a
  loaded task file are invalid input and raise an error instead of being
  silently accepted.

## Workload Options

- `tasks_path`: path to the JSON task file

## Files

- `__init__.py`: loader and row normalization
- `source.py`: local task-file helpers used by the workload-local scripts
- use `rlmbenchy run --config config/run_profiles/smoke-2-check-adapter-matrix-oss.toml --task-id <id>` for one-task execution
- use `rlmbenchy workloads tasks check_adapter_matrix` or `task` for inspection
- `tasks.json`: default adapter matrix checks
