# S-NIAH

Workload-local implementation of a synthetic needle-in-a-haystack task.
See `setup.md` for prerequisites and first-run setup.

## Data Location

- Source type: generated in memory at workload-load time.
- External dependency: none.
- Canonical generator: `build_s_niah_synthetic_task()` in `source.py`

This workload does not read a local file or remote dataset. It creates one task
from a deterministic random seed.

## Generated Data Shape

The synthetic task builder emits payloads shaped like:

```json
{
  "task_id": "s_niah_synthetic_seed_1_lines_120_account_id",
  "query": "What is the value of account_id? Return only the value.",
  "context": "record_0000: token_a=123; token_b=456\n...",
  "expected": {"kind": "exact", "value": "48291"},
  "dataset_meta": {
    "source": "s_niah_synthetic",
    "seed": 1,
    "haystack_lines": 120,
    "needle_position": 42,
    "needle_key": "account_id"
  }
}
```

The haystack is one segment per line. One line contains the real
`<needle_key>=<needle_value>` pair; the rest are distractor records.

## Loaded Task Shape

The workload always builds a single `WorkloadTask` with:

- `id`: `s_niah_synthetic_seed_<seed>_lines_<haystack_lines>_<needle_key>`
- `inputs.task_id`
- `inputs.needle_key`
- `inputs.haystack_lines`
- `answer`: exact expected value
- `metadata.source = "s_niah_synthetic"`
- `metadata.seed`
- `metadata.needle_position`
- `metadata.needle_key`

The haystack stays behind a tool:

- `s_niah_get_haystack(task_id)`

## Workload Options

- `seed`: defaults to `1`
- `haystack_lines`: defaults to `120`
- `needle_key`: defaults to `account_id`

## Notes

- This is not a fixed dataset snapshot. It is a reproducible synthetic task
  generator in the style of a RULER/S-NIAH benchmark.
- `seed` alone is not a unique task id because `haystack_lines` and
  `needle_key` also change the generated task. All three task-shaping options
  are included in the canonical id.

## Task Id Audit Notes

Audit date: 2026-04-24.

- Source type audited: deterministic local generator, not a remote dataset.
- Default generated id shape:
  `s_niah_synthetic_seed_1_lines_120_account_id`.
- A targeted loader check with `seed=7`, `haystack_lines=40`, and
  `needle_key=account_id` produced
  `s_niah_synthetic_seed_7_lines_40_account_id`.
- There is only one generated task per workload load, so duplicate ids are not
  possible inside one bundle unless id construction changes.

## Files

- `__init__.py`: workload loader
- `source.py`: synthetic task builder
- `tools.py`: `s_niah_get_haystack`
- use `rlmbenchy run --config config/run_profiles/smoke-4-s-niah-oss.toml --task-id <id>` for one-task execution
- use `rlmbenchy workloads tasks s_niah` or `task` for inspection
