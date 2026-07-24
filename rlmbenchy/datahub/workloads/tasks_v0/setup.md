# Setup

## What You Need

- Nothing external. The default task file is checked in at
  `rlmbenchy/datahub/workloads/tasks_v0/tasks.json`.
- Optional: a different JSON task file via `tasks_path`.

## Defaults And Resolution

- Default `tasks_path`:
  `rlmbenchy/datahub/workloads/tasks_v0/tasks.json`
- If you pass an explicit `tasks_path`, absolute paths are used as-is.
- If you pass a relative `tasks_path`, it resolves from the current working
  directory.

## Minimal Setup

- No setup is required for the checked-in default file.
- For an override file, provide a JSON list of task rows matching
  `README.md`.

## Verify Setup

```bash
uv run python -m rlmbenchy workloads tasks tasks_v0 --limit 1
```

For an override file:

```bash
uv run python -m rlmbenchy workloads tasks tasks_v0 --limit 1 -o tasks_path=relative/or/absolute/tasks.json
```

## Common Failure Modes

- `tasks_path` points to a different file than expected because the shell
  working directory changed.
- The task file is valid JSON, but not a JSON list.
- Rows are present, but they do not use the required `id` and `task` fields.
