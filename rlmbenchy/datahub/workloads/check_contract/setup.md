# Setup

## What You Need

- Nothing external. The default task file is checked in at
  `rlmbenchy/datahub/workloads/check_contract/tasks.json`.
- Optional: a different JSON task file via `tasks_path`.

## Defaults And Resolution

- Default `tasks_path`:
  `rlmbenchy/datahub/workloads/check_contract/tasks.json`
- If you pass an explicit `tasks_path`, absolute paths are used as-is.
- If you pass a relative `tasks_path`, it resolves from the current working
  directory.

## Minimal Setup

- No setup is required for the checked-in default file.
- For an override file, provide a JSON list of task rows matching
  `README.md`.

## Verify Setup

```bash
uv run python -m rlmbenchy workloads tasks check_contract --limit 1
```

For an override file:

```bash
uv run python -m rlmbenchy workloads tasks check_contract --limit 1 -o tasks_path=relative/or/absolute/tasks.json
```

## Common Failure Modes

- `tasks_path` resolves from a different working directory than expected.
- The task file is valid JSON, but not a JSON list.
- Rows are missing required `task_id` or `query` fields.
- `context_chunks` is present but is not a list of strings.
