# BrowseComp-Plus

Workload-local implementation of the `browsecomp_plus` benchmark.
See `setup.md` for prerequisites and first-run setup.

## Data Location

- Source type: remote public dataset.
- Dataset id: `Tevatron/browsecomp-plus`
- Access path: Hugging Face datasets server helpers in `rlmbenchy.datahub.workloads.support.hf`
- Default config: `default`
- Default split: `test`
- License metadata: MIT; see the repository's
  [third-party notices](../../../../THIRD_PARTY_NOTICES.md#dataset-integrations).

The workload loader pulls rows from the remote dataset (cached locally on
first use via `~/.cache/huggingface/datasets/`) and keeps the document
payload behind a tool instead of inlining every document into task inputs.

## Raw Row Shape

The code uses these dataset fields when present:

- `query_id`
- `query`
- `answer`
- `gold_docs`
- `evidence_docs`
- `negative_docs`

Document fields may be plain strings or objects such as:

```json
{"title": "Doc title", "text": "Document text"}
```

The loader flattens `gold_docs`, `evidence_docs`, and `negative_docs` into one
ordered list of document texts.

## Loaded Task Shape

Each row becomes one `WorkloadTask` with:

- `id`: `browsecomp_plus_<config>_<split>_row_<row_index>_<query_id>`
- `inputs.question`
- `inputs.query_id`: the canonical task id used by `browsecomp_get_docs`
- `inputs.docs_total`
- `answer`: the extracted gold answer text
- `metadata.source_query_id`: the upstream `query_id`
- `metadata.docs_total`

The full documents are exposed through:

- `browsecomp_get_docs(task_id, offset, max_docs)`

## Workload Options

- `dataset_id`: defaults to `Tevatron/browsecomp-plus`
- `config`: defaults to `default`
- `split`: defaults to `test`
- `token`: optional Hugging Face token override; if omitted, the loader falls
  back to `HF_TOKEN` or `secrets.toml`
- `max_docs_per_task`: optional cap when preloading docs for a task
- `max_docs_per_tool_call`: optional cap returned by `browsecomp_get_docs`

## Notes

- This repo uses the public BrowseComp-Plus dataset directly.
- The current implementation maps directly onto the public dataset, while the
  paper setup sampled a smaller subset with many documents per query.
- `task_id` lookups use the canonical id and stop once the matching row is
  built, so a single-task inspection does not need to build document payloads
  for skipped rows.

## Task Id Audit Notes

Audit date: 2026-04-24.

- Official source checked: <https://huggingface.co/datasets/Tevatron/browsecomp-plus>.
- Source view audited: `default/test`.
- Rows audited: 830.
- Upstream key checked: `query_id`.
- Duplicate upstream `query_id` values found: 0.
- Duplicate canonical task ids found: 0.
- First observed upstream ids: `769`, `770`, `771`, `772`, `773`.
- Public task ids intentionally include workload/config/split/row dimensions in
  addition to `query_id`, so future duplicate `query_id` values cannot collide
  in the document-tool payload map.

## Files

- `__init__.py`: workload loader
- `source.py`: row parsing and task-building helpers
- `tools.py`: `browsecomp_get_docs`
- use `rlmbenchy run --config config/run_profiles/smoke-9-browsecomp-plus-oss.toml --task-id <id>` for one-task execution
- use `rlmbenchy workloads tasks browsecomp_plus` or `task` for inspection
