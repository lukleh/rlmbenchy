# tasks_v0

Small local JSON workload for generic algorithmic and data-manipulation tasks.
See `setup.md` for prerequisites and first-run setup.

## Data Location

- Source type: local checked-in JSON.
- Default file: `rlmbenchy/datahub/workloads/tasks_v0/tasks.json`.
- Override: `options.tasks_path`.
- Explicit relative `tasks_path` values are resolved from the current working directory.

## Raw Task File Shape

The loader expects a JSON list of objects. Each row uses `id` and `task`.

```json
[
  {
    "id": "v0_example",
    "task": "Solve the task and return compact JSON.",
    "answer": "optional expected answer"
  }
]
```

Accepted row fields:

- `id`: task identifier
- `task`: full task prompt text
- `answer`: optional expected answer payload

## Loaded Task Shape

Each row becomes one `WorkloadTask` with:

- `id`: copied from `id`, or `v0_task_NNN` when `id` is missing
- `inputs.task`: the prompt text
- `answer`: copied through from the row
- `metadata`: empty

This workload has no dataset-specific tools.

## Task Id Audit Notes

Audit date: 2026-04-24.

- Source view audited: checked-in `tasks.json`.
- Rows audited: 16.
- Duplicate task ids found: 0.
- First observed ids:
  `v0_reconcile_ledgers`, `v0_shortest_path_alt_routes`,
  `v0_shift_scheduler_constraints`.
- Authored `id` values are treated as the task ids. Duplicate ids in a loaded
  task file are invalid input and raise an error instead of being silently
  rewritten.
- The legacy alias `task_id` is rejected for this workload; use `id`.

## Workload Options

- `tasks_path`: path to the JSON file to load

## Files

- `__init__.py`: workload loader
- `source.py`: local task-file helpers used by the workload-local scripts
- use `rlmbenchy run --config config/run_profiles/smoke-3-tasks-v0-oss.toml --task-id <id>` for one-task execution
- use `rlmbenchy workloads tasks tasks_v0` or `task` for inspection
- `tasks.json`: default checked-in task set
- `tools.py`: returns no tools for this workload
