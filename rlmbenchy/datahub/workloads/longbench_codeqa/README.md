# LongBench-v2 CodeQA

Workload-local implementation of the LongBench-v2 CodeQA slice.
See `setup.md` for prerequisites and first-run setup.

## Data Location

- Source type: remote public dataset.
- Dataset id: `zai-org/LongBench-v2`
- Access path: Hugging Face datasets server helpers in `rlmbenchy.datahub.workloads.support.hf`
- Default config: `default`
- Default split: `train`
- License metadata: Apache-2.0; see the repository's
  [third-party notices](../../../../THIRD_PARTY_NOTICES.md#dataset-integrations).

This workload does not use every row from LongBench-v2. It filters to rows with
`sub_domain == "Code repo QA"`.

## Raw Row Shape

The workload uses these row fields:

- `_id`
- `sub_domain`
- `question`
- `context`
- `answer`
- `choice_A`
- `choice_B`
- `choice_C`
- `choice_D`

Rows outside the CodeQA subset, or rows missing `question`, `context`, or
`answer`, are skipped.

The real public dataset uses `_id` as the native row identifier. The loader
falls back to `id` only for tests or compatible local rows.

## Loaded Task Shape

Each usable row becomes one `WorkloadTask` with:

- `id`: `longbench_codeqa_<config>_<split>_row_<raw_row_index>_<_id>`, or the
  same prefix without a source id when the row has no `_id`/`id`
- `inputs.question`: question plus the instruction to return only `A`/`B`/`C`/`D`
- `inputs.task_id`
- `inputs.code_lines`
- `inputs.options`
- `answer`: normalized exact-match option label
- `metadata.source = "longbench_v2"`
- `metadata.config`
- `metadata.split`
- `metadata.row_index`
- `metadata.source_id`: the upstream `_id`

The code repository context stays behind a tool:

- `longbench_get_code_context(task_id)`

## Workload Options

- `dataset_id`: defaults to `zai-org/LongBench-v2`
- `config`: defaults to `default`
- `split`: defaults to `train`
- `score_kind`: defaults to `exact`
- `max_rows`: defaults to `50`
- `token`: optional HF token override

## Notes

- The workload currently models the CodeQA subset as a multiple-choice task
  over a large code context.
- This repo filters the public LongBench-v2 dataset down to the
  `Code repo QA` sub-domain.
- `max_rows` counts emitted CodeQA tasks, not raw LongBench-v2 rows. This
  matters because the first CodeQA row in the public train split appears after
  non-CodeQA rows.
- `task_id` lookups scan by canonical id before task construction and stop once
  the selected CodeQA task is found.

## Task Id Audit Notes

Audit date: 2026-04-24.

- Official source checked: <https://huggingface.co/datasets/zai-org/LongBench-v2>.
- Source view audited: `default/train`.
- Total rows audited: 503.
- Duplicate upstream `_id` values across all rows: 0.
- CodeQA subset audited: 50 rows where `sub_domain == "Code repo QA"`.
- First CodeQA raw row index: 7.
- Duplicate CodeQA `_id` values found: 0.
- Duplicate canonical CodeQA task ids found: 0.
- First observed CodeQA ids:
  `66fa208bbb02136c067c5fc1`, `66ec56dd821e116aacb1cd0e`,
  `66fa3843bb02136c067c655d`.
- Public task ids include the raw row index and `_id` so the id remains stable
  inside the full dataset ordering and scoped to config/split.

## Files

- `__init__.py`: workload loader
- `source.py`: subset filtering and task-building helpers
- `tools.py`: `longbench_get_code_context`
- use `rlmbenchy run --config config/run_profiles/smoke-10-longbench-codeqa-oss.toml --task-id <id>` for one-task execution
- use `rlmbenchy workloads tasks longbench_codeqa` or `task` for inspection
