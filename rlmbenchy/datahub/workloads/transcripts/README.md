# Transcripts

Local transcript workload with task selectors and tool-based transcript access.
The workload is language-agnostic: the loader, signature, and tools do not
assume any particular language; responses follow whatever language the
transcript content is in. See `setup.md` for prerequisites and first-run setup.

## Data Location

- Source type: local transcript corpus plus local task-spec JSON.
- Default transcript root:
  `<runtime share dir>/datasets/transcripts/transcripts`
- Default task-spec path:
  `<runtime share dir>/workloads/transcripts/tasks.json`
- Example task-spec file:
  `rlmbenchy/datahub/workloads/transcripts/tasks.example.json`
- Optional runtime config file:
  `<runtime config dir>/transcripts.toml`

Path precedence and runtime-config setup are documented in `setup.md`.

## Transcript Corpus Layout

The transcript root is a flat directory of hashed transcript directories:

```text
<root>/
  <64-hex-hash-a>/
    transcript.txt
  <64-hex-hash-b>/
    transcript.txt
```

Rules enforced by the loader:

- directory names must be 64 lowercase hex characters
- each selected directory must contain `transcript.txt` (UTF-8)
- empty transcript files (no non-empty lines) are skipped
- each non-empty stripped line inside `transcript.txt` is one segment

## Task Spec Schema

`tasks.json` is a JSON list. Fields the loader actually reads per row:

| field | type | required | purpose |
|---|---|---|---|
| `id` | str | no (defaults to `transcripts_task_NNN`) | unique task id |
| `query` | str | yes | prompt, injected as `inputs.question` |
| `data.selector.mode` | `"ALL" \| "FILE_COUNT" \| "HASH_IDS"` | yes | selection strategy |
| `data.selector.value` | `"ALL"` / int ≥ 0 / non-empty list[str] | yes | strategy argument |
| `answer` | any | no | expected answer (passthrough for evaluation) |
| `metadata` | dict | no | passthrough into task metadata |

`data` must contain *only* `selector` — any other key is rejected. Legacy
fields `task_id`, `data.hash_ids`, `data.file_count`, `data.data_keyword`,
`data.keyword`, and top-level `query_lines` are explicitly rejected.

Selector shapes:

- `{"selector": {"mode": "ALL", "value": "ALL"}}`
- `{"selector": {"mode": "FILE_COUNT", "value": 10}}`
- `{"selector": {"mode": "HASH_IDS", "value": ["<hash>", "..."]}}`

Value constraints:

- `ALL` requires the literal string `"ALL"`.
- `FILE_COUNT` requires an integer `>= 0`; if it resolves to zero selected
  transcripts, task loading fails.
- `HASH_IDS` requires a non-empty list of non-empty strings; every requested
  hash id must exist under the indexed transcript root or task loading fails.

Example:

```json
[
  {
    "id": "task_a",
    "query": "Summarize the selected transcripts.",
    "data": {"selector": {"mode": "HASH_IDS", "value": ["aaaaaaaa..."]}},
    "metadata": {"topic": "station opening"}
  }
]
```

## Loaded Task Shape

Each row becomes one `WorkloadTask`:

- `id`: copied from `id`, or generated as `transcripts_task_NNN`
- `inputs.question: str`
- `inputs.transcripts_count: int`
- `answer`: passthrough from the spec
- `metadata.task_data.selector: dict`
- `metadata.task_data.hash_ids: list[str]`
- `metadata.task_data.transcripts_count: int`
- `metadata.tasks_path`, `metadata.row_index`

## Tools

Tools are scoped to the active task's selected transcript hashes:

- `list_transcripts() -> list[{hash_id: str, segment_count: int}]`
- `get_segments(hash_id: str) -> list[str]`
- `segment_count() -> int` — total across all selected transcripts
- `get_segment(position: int) -> str` — 1-based, format `"[<hash_id>] <segment_text>"`, empty string when out of range

## Workload Options

- `root`: transcript root directory
- `tasks_path`: task-spec JSON path

## Task Id Audit Notes

Audit date: 2026-04-24.

- Source view audited: checked-in `tasks.example.json`.
- Rows audited: 1.
- Duplicate task ids found: 0.
- First observed id: `transcripts_smoke_first_1`.
- Authored `id` values are treated as the task ids. Duplicate ids in a loaded
  task file are invalid input and raise an error instead of allowing
  `hash_ids_by_task_id` tool scoping to collide.
- Legacy top-level `task_id` is rejected for this workload; use `id`.

## Files Layout

```
rlmbenchy/datahub/workloads/transcripts/
  __init__.py          # loader, selector parsing, path resolution, signature
  tools.py             # transcript access tools (task-scoped)
  source.py            # helper for flattening selected transcripts into direct-run payloads
  README.md            # this file
  setup.md             # first-run setup
  tasks.example.json   # minimal, language-agnostic example task
```

CLI:

- `rlmbenchy run --config config/run_profiles/smoke-5-transcripts-oss.toml --task-id <id>`
- `rlmbenchy workloads tasks transcripts` or `task` for inspection
