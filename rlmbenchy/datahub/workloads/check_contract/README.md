# check_contract

Internal contract-check workload backed by a local JSON task file.
See `setup.md` for prerequisites and first-run setup.

This workload is mainly for validating the basic task/query/context contract
used by the workbench.

## Data Location

- Source type: local checked-in JSON.
- Default file: `rlmbenchy/datahub/workloads/check_contract/tasks.json`.
- Override: `options.tasks_path`.
- Paths are expanded and resolved as local filesystem paths.
- Explicit relative `tasks_path` values are resolved from the current working directory.

## Raw Task File Shape

The loader expects a JSON list of task objects.

```json
[
  {
    "task_id": "check_001",
    "category": "realistic_table_math",
    "query": "Compute the total from context.",
    "context": "csv or plain text here"
  }
]
```

Supported row fields:

- `task_id`: logical task id; defaults to `check_NNN` when missing
- `query`: required prompt/question
- `context`: string context payload
- `context_chunks`: optional list of strings instead of a single `context`
- `category`: optional category label; defaults to `unknown`
- any additional keys: preserved into metadata

If `context_chunks` is present, the workload joins them with blank lines before
building the task.

## Loaded Task Shape

Each row becomes one `WorkloadTask` with:

- `id`: copied from `task_id`, or generated as `check_NNN`
- `inputs.query`
- `inputs.context`
- `metadata.category`
- `metadata.<extra fields>`

This workload does not define tools and does not currently carry expected
answers.

## Task Id Audit Notes

Audit date: 2026-04-24.

- Source view audited: checked-in `tasks.json`.
- Rows audited: 20.
- Duplicate task ids found: 0.
- First observed ids:
  `rl01_invoice_total_acme`, `rl02_net_revenue_after_refunds`,
  `rl03_unique_users_single_day`.
- Authored `task_id` values are treated as the task ids. Duplicate ids in a
  loaded task file are invalid input and raise an error instead of being
  silently accepted.

## Workload Options

- `tasks_path`: path to the JSON task file

## Files

- `__init__.py`: loader and row normalization
- `source.py`: local task-file helpers used by the workload-local scripts
- use `rlmbenchy run --config config/run_profiles/smoke-1-check-contract-oss.toml --task-id <id>` for one-task execution
- use `rlmbenchy workloads tasks check_contract` or `task` for inspection
- `tasks.json`: default internal validation task set
