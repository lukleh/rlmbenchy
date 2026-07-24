# OOLONG-Pairs

Workload-local implementation of the OOLONG-Pairs benchmark.
See `setup.md` for prerequisites and first-run setup.

This workload is derived from OOLONG contexts plus a fixed prompt template,
rather than from a separate standalone dataset.

## Data Location

- Source type: remote public dataset plus local prompt templates.
- Dataset id: `oolongbench/oolong-synth`
- Access path: Hugging Face datasets server helpers in `rlmbenchy.datahub.workloads.support.hf`
- Default config: `default`
- Default split: `test`
- Canonical query templates: `OOLONG_PAIRS_QUERY_TEMPLATES` in `source.py`
- License metadata: the upstream OOLONG dataset card declares no license.
  Review the upstream terms before use; see the repository's
  [third-party notices](../../../../THIRD_PARTY_NOTICES.md#dataset-integrations).

## Raw Row Shape

The workload only uses:

- `id`
- `context_window_text`

The question is not taken from the dataset row. Instead, the loader applies one
of the built-in query templates selected by `query_index`.

## Loaded Task Shape

Each usable row becomes one `WorkloadTask` with:

- `id`: `oolong_pairs_<config>_<split>_query_<query_index>_row_<row_index>_<source_id>`,
  or the same prefix without `<source_id>` when the row has no upstream `id`
- `inputs.question`: the selected template text
- `inputs.task_id`
- `inputs.context_lines`
- `answer`: always `None`
- `metadata.source = "oolong_pairs"`
- `metadata.config`
- `metadata.split`
- `metadata.row_index`
- `metadata.query_index`
- `metadata.source_id`: the upstream row `id`

The full context stays behind a tool:

- `oolong_pairs_get_context(task_id)`

## Workload Options

- `dataset_id`: defaults to `oolongbench/oolong-synth`
- `config`: defaults to `default`
- `split`: defaults to `test`
- `query_index`: template index; defaults to `0`
- `max_rows`: defaults to `20`
- `token`: optional HF token override

## Notes

- This repo’s implementation uses the template set defined in `source.py`.
- The workload is intentionally open-ended and does not ship expected answers.
- `query_index` is part of the canonical task id because the same OOLONG row
  becomes a different task under each pair-query template.
- `task_id` lookups stream source rows and stop once the canonical id is found.
  The default `max_rows=20` is only a listing/batch cap.

## Task Id Audit Notes

Audit date: 2026-04-24.

- Official source checked: <https://huggingface.co/datasets/oolongbench/oolong-synth>.
- This workload uses the same `oolongbench/oolong-synth` rows audited for
  `oolong`.
- Source views audited with `datasets.load_dataset`: `default/validation` and
  `default/test`.
- `default/validation`: 1,300 rows; duplicate upstream `id` values found: 0;
  duplicate canonical task ids found: 0 for a fixed `query_index`.
- `default/test`: 5,200 rows; duplicate upstream `id` values found: 0;
  duplicate canonical task ids found: 0 for a fixed `query_index`.
- First observed `default/test` ids: `810080000`, `810080001`, `810080002`.
- Public task ids include `query_index` so tool payloads do not collide when
  multiple prompt templates are run over the same upstream row.

## Files

- `__init__.py`: workload loader
- `source.py`: template definitions and task-building helpers
- `tools.py`: `oolong_pairs_get_context`
- use `rlmbenchy run --config config/run_profiles/smoke-8-oolong-pairs-oss.toml --task-id <id>` for one-task execution
- use `rlmbenchy workloads tasks oolong_pairs` or `task` for inspection
