# OOLONG

Workload-local implementation of the OOLONG benchmark.
See `setup.md` for prerequisites and first-run setup.

## Data Location

- Source type: remote public dataset.
- Dataset id: `oolongbench/oolong-synth`
- Access path: Hugging Face datasets server helpers in `rlmbenchy.datahub.workloads.support.hf`
- Default workload config: `default`
- Default split: `test`
- License metadata: the upstream dataset card declares no license. Review the
  upstream terms before use; see the repository's
  [third-party notices](../../../../THIRD_PARTY_NOTICES.md#dataset-integrations).

The generic `rlmbenchy run --workload oolong` path uses the same loader defaults as the rest of DataHub.

## Raw Row Shape

The workload uses these row fields:

- `id`
- `question`
- `answer`
- `context_window_text`

Rows missing `question` or `answer` are skipped.

## Loaded Task Shape

Each usable row becomes one `WorkloadTask` with:

- `id`: `oolong_<config>_<split>_row_<row_index>_<source_id>`, or the same
  prefix without `<source_id>` when the row has no upstream `id`
- `inputs.question`
- `inputs.task_id`
- `inputs.context_lines`
- `answer`: normalized expected answer payload
- `metadata.source = "oolong"`
- `metadata.config`
- `metadata.split`
- `metadata.row_index`
- `metadata.source_id`: the upstream row `id`

The full context stays behind a tool:

- `oolong_get_context(task_id)`

## Workload Options

- `dataset_id`: defaults to `oolongbench/oolong-synth`
- `config`: defaults to `default`
- `split`: defaults to `test`
- `score_kind`: defaults to `exact`
- `max_rows`: defaults to `50`
- `token`: optional HF token override

## Notes

- The broader OOLONG ecosystem also includes `oolongbench/oolong-real`, but
  this workload currently uses `oolong-synth`.
- `task_id` lookups stream source rows and stop once the canonical id is found.
  The default `max_rows=50` is only a listing/batch cap; it does not hide a
  targeted task id.

## Task Id Audit Notes

Audit date: 2026-04-24.

- Official source checked: <https://huggingface.co/datasets/oolongbench/oolong-synth>.
- Current official config is `default`; the older `trec_coarse` config is not
  available in the public dataset view used by this loader.
- Source views audited with `datasets.load_dataset`: `default/validation` and
  `default/test`.
- `default/validation`: 1,300 rows; duplicate upstream `id` values found: 0;
  duplicate canonical task ids found: 0.
- `default/test`: 5,200 rows; duplicate upstream `id` values found: 0;
  duplicate canonical task ids found: 0.
- First observed `default/test` ids: `810080000`, `810080001`, `810080002`.
- Public task ids still include config/split/row dimensions even though the
  audited upstream ids were unique, because native ids alone are not scoped to
  workload options.

## Files

- `__init__.py`: workload loader
- `source.py`: row parsing and task-building helpers
- `tools.py`: `oolong_get_context`
- use `rlmbenchy run --config config/run_profiles/smoke-7-oolong-oss.toml --task-id <id>` for one-task execution
- use `rlmbenchy workloads tasks oolong` or `task` for inspection
