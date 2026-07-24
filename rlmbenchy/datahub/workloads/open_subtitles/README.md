# OpenSubtitles

Workload-local implementation of the OpenSubtitles translation workload.
See `setup.md` for prerequisites and first-run setup.

## Data Location

- Source type: remote bilingual archive, cached locally after download.
- Canonical dataset id: `Helsinki-NLP/open_subtitles`
- Actual download URL pattern:
  `https://object.pouta.csc.fi/OPUS-OpenSubtitles/v2018/moses/{config}.txt.zip`
- Local cache directory:
  `<runtime cache dir>/datahub/open_subtitles`

The workload does not use the Hugging Face datasets server for row access. It
downloads the OPUS archive directly, caches the ZIP, and parses aligned text
files locally.

The referenced dataset card reports its license as `unknown`, and subtitle
content may be subject to additional upstream rights. Review the
[OPUS/OpenSubtitles terms](https://opus.nlpl.eu/legacy/OpenSubtitles-v2018.php)
before use; see the repository's
[third-party notices](../../../../THIRD_PARTY_NOTICES.md#dataset-integrations).

## Raw Row Shape

`source.py` converts the archive into rows shaped like:

```json
{
  "id": "13",
  "meta": {
    "year": 2017,
    "imdbId": 7006210,
    "subtitleId": {"en": 123, "hi": 456},
    "sentenceIds": {"en": [1, 2], "hi": [1, 2]}
  },
  "translation": {
    "en": "Where are you going?",
    "hi": "tum kahaan ja rahe ho?"
  }
}
```

Only aligned non-empty subtitle pairs are kept.

## Loaded Task Shape

Each usable row becomes one `WorkloadTask` with:

- `id`: `open_subtitles_<config>_<split>_<direction>_row_<row_index>_<source_id>`
- `inputs.task_id`
- `inputs.source_lang`
- `inputs.target_lang`
- `answer`: normalized expected target-language subtitle text
- `metadata.source = "open_subtitles"`
- `metadata.dataset_id = "Helsinki-NLP/open_subtitles"`
- `metadata.config`
- `metadata.split`
- `metadata.row_index`
- `metadata.source_id`: the archive line index
- `metadata.direction`
- `metadata.source_lang`
- `metadata.target_lang`

The source subtitle text stays behind a tool:

- `subtitles_get_source_text(task_id)`

## Workload Options

- `config`: language pair such as `en-hi`; defaults to `en-hi`
- `split`: currently only `train` is supported
- `direction`: `forward` or `reverse`; defaults to `forward`
- `score_kind`: defaults to `exact`
- `max_rows`: defaults to `50`
- `timeout_s`: download timeout; defaults to `60.0`
- `retries`: download retry count; defaults to `3`

## Notes

- The loader enforces `dataset_id == "Helsinki-NLP/open_subtitles"` and
  `split == "train"` today.
- The query shown to the model is a translation instruction, but the actual
  subtitle text is retrieved through the tool rather than stored directly in the
  workload inputs.
- `task_id` lookup is pushed into archive iteration. A targeted lookup scans
  until the matching canonical id is found, builds only that task/tool payload,
  and stops; it does not materialize the full subtitle archive into a list.

## Task Id Audit Notes

Audit date: 2026-04-24.

- Official sources checked:
  - <https://huggingface.co/datasets/Helsinki-NLP/open_subtitles>
  - <https://opus.nlpl.eu/legacy/OpenSubtitles-v2018.php>
- Source view audited through the local OPUS archive parser:
  `config=en-hi`, `split=train`, `direction=forward`.
- Parsed aligned non-empty rows: 93,016.
- Duplicate native line ids found: 0.
- Duplicate canonical task ids found: 0.
- First observed native line ids: `0`, `1`, `2`, `3`, `4`.
- Last observed native line ids: `93013`, `93014`, `93015`.
- Public task ids include config, split, direction, row index, and source id
  because numeric line ids are only meaningful inside one parsed archive and
  direction.

## Files

- `__init__.py`: workload loader
- `source.py`: archive download, caching, parsing, and task-building helpers
- `tools.py`: `subtitles_get_source_text`
- use `rlmbenchy run --config config/run_profiles/smoke-11-open-subtitles-oss.toml --task-id <id>` for one-task execution
- use `rlmbenchy workloads tasks open_subtitles` or `task` for inspection
