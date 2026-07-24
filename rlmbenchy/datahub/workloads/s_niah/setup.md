# Setup

## What You Need

- Nothing external. This workload is generated in memory.

## Defaults And Resolution

- Default `seed`: `1`
- Default `haystack_lines`: `120`
- Default `needle_key`: `account_id`
- One normalized task is generated per workload load.

## Minimal Setup

- No setup is required for the defaults.
- Override `seed`, `haystack_lines`, or `needle_key` only if you want a
  different synthetic task shape.

## Verify Setup

```bash
uv run python -m rlmbenchy workloads tasks s_niah --limit 1
```

Example with non-default parameters:

```bash
uv run python -m rlmbenchy workloads tasks s_niah --limit 1 -o seed=7 -o haystack_lines=200 -o needle_key=session_id
```

## Common Failure Modes

- `haystack_lines` is set too low; validation expects a minimum-sized haystack.
- Two runs are compared as if they were the same task even though `seed` or
  `needle_key` changed.
- The workload is treated like a persisted dataset even though it is generated
  fresh from the current options.
