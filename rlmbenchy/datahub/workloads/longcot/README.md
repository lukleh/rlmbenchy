# longcot

Long-horizon chain-of-thought reasoning problems from
[LongHorizonReasoning/longcot](https://github.com/LongHorizonReasoning/longcot)
(≈2,500 questions across 5 domains × 3 difficulties).

See `setup.md` for prerequisites.

## Why This Is Here

These prompts are long-horizon reasoning problems that exercise the RLM
loop on harder, multi-step tasks than the existing workloads. It is not a
scored benchmark in this repo — upstream verification is template-specific
(SMILES canonicalization, chess engine checks, sympy-backed math
equivalence, logic simulators) and deliberately out of scope.

## Data Location

- Source type: remote Hugging Face dataset.
- Dataset id: `LongHorizonReasoning/longcot`.
- Configs (subsets): `all`, `logic`, `cs`, `chemistry`, `chess`, `math`.
- Splits: `easy`, `medium`, `hard`.
- Access: `datasets.load_dataset(..., streaming=False)`. First call per
  `(config, split)` downloads into `~/.cache/huggingface/datasets/` (~4 MB
  per LongCoT config); subsequent calls are disk-bound and work offline.
  Public dataset; anonymous access works.
- License metadata: MIT; see the repository's
  [third-party notices](../../../../THIRD_PARTY_NOTICES.md#dataset-integrations).

Approximate row counts per domain × split (from the upstream bundle):

| Domain     | easy | medium | hard |
|------------|-----:|-------:|-----:|
| logic      |  105 |    195 |  200 |
| cs         |  100 |    150 |  250 |
| chemistry  |  100 |    200 |  200 |
| chess      |  100 |    150 |  250 |
| math       |  102 |    150 |  250 |

Prompt lengths span ≈250 → 28,000 characters depending on template and
difficulty.

## Raw Row Shape (on Hugging Face)

The HF dataset exposes these top-level fields:

- `question_id`: stable per-question identifier (e.g. `Sudoku_easy_1`).
- `domain`: one of `logic`, `cs`, `chemistry`, `chess`, `math`.
- `difficulty`: one of `easy`, `medium`, `hard`.
- `template`: template name (e.g. `BlocksWorld`, `HM`, `easy1`, `uci_to_fen`,
  `backtracking`). Templates differ per domain.
- `prompt`: the full text to send to an LLM. Contains the problem statement,
  rules, and the required answer format (typically `solution = <value>`).
- `answer`: the canonical reference answer **encoded as a JSON string**
  (e.g. `"null"`, `'["2013^{4025}", "2692"]'`, `'"canonical_smiles"'`,
  `'{"q1": "a", ...}'`). Always `"null"` for every logic-domain question
  (upstream verifiers reconstruct the answer from problem state).
- `canary`: LongCoT's public-dataset canary GUID. Useful for checking
  whether the benchmark has leaked into model training data.

## Loaded Task Shape

Each task produced by this workload has:

- `id`: `longcot_<config>_<split>_<domain>_row_<row_index>_<question_id>`, or
  the same prefix without `<question_id>` when the row has no upstream id.
- `inputs.prompt`: the full prompt string, passed directly to the model.
- `answer`: always `None`. The workload does **not** attempt to verify
  LongCoT answers because upstream verification is template-specific
  (SMILES canonicalization, chess engine checks, math-expression equivalence
  with optional LLM fallback) and is deliberately out of scope here.
- `metadata`:
  - `source`: `"longcot"`.
  - `domain`, `difficulty`, `template`: surfaced from the row for filtering
    and log inspection.
  - `question_id`: the upstream row id before canonical task-id composition.
  - `config`, `split`: the HF config/split used to load the task.
  - `row_index`: index inside the streamed rows.
  - `raw_answer`: the upstream reference, parsed from its JSON-string
    representation back to its native type. For logic-domain rows this is
    `None`.
  - `raw_answer_encoded`: the original HF wire bytes (the pre-parse JSON
    string) when the upstream `answer` field is a string; `None` when the
    row came from a bundled-JSON shape where `answer` is already native.
    A verifier can use this to distinguish a bare `"1"` (parses to `int`)
    from an intentionally wrapped `'"1"'` (parses to `str`).
  - `canary`: the per-row canary GUID (when available).

The workload exposes **no tools**; the prompt is self-contained.

## Workload Options

| Option | Default | Purpose |
|---|---|---|
| `dataset_id` | `LongHorizonReasoning/longcot` | HF dataset id. |
| `config` | `logic` | One of `all / logic / cs / chemistry / chess / math`. |
| `split` | `easy` | One of `easy / medium / hard`. |
| `max_rows` | `5` | Row cap per (config, split). Pass e.g. `-o max_rows=500` for a full-split run. |
| `token` | unset | Optional HF token override. |

## Notes

- **Verification is out of scope.** The workload loads prompts; it does not
  ship the upstream template-specific verifiers (chess engine, RDKit SMILES
  canonicalization, sympy-backed math equivalence, logic simulators). If
  you need proper scoring, read `metadata["raw_answer"]` off each task and
  run your own verifier offline.
- **Logic domain has `raw_answer = None` for every row.** Upstream
  reconstructs the answer from `problem.instance` at verify time; the HF
  dataset does not include `problem`, so there is no ground-truth string
  to preserve. You can still run the prompts and inspect model outputs in
  the telemetry log, but automatic correctness checks are not possible without
  the upstream simulators.
- **Canary preserved.** `metadata["canary"]` carries the public-dataset
  canary GUID so the benchmark's training-leak check keeps working.
- **Explicit task lookup ignores the smoke cap.** `max_rows=5` is the
  default for listings and batch runs, but `--task-id` lookups scan the full
  selected split so a real task id is not hidden behind the smoke default.
- The dataset id is lowercase: `LongHorizonReasoning/longcot`. The older
  mixed-case spelling does not resolve through the current dataset-server
  split/parquet endpoints.

## Task Id Audit Notes

Audit date: 2026-04-24.

- Official source checked: <https://huggingface.co/datasets/LongHorizonReasoning/longcot>.
- Source views audited: all 18 `(config, split)` combinations:
  `all`, `logic`, `cs`, `chemistry`, `chess`, `math` x
  `easy`, `medium`, `hard`.
- Duplicate `question_id` values within each audited view: 0.
- Duplicate canonical task ids within each audited view: 0.
- Row counts audited:
  - `all/easy`: 507, `all/medium`: 845, `all/hard`: 1,150.
  - `logic/easy`: 105, `logic/medium`: 195, `logic/hard`: 200.
  - `cs/easy`: 100, `cs/medium`: 150, `cs/hard`: 250.
  - `chemistry/easy`: 100, `chemistry/medium`: 200,
    `chemistry/hard`: 200.
  - `chess/easy`: 100, `chess/medium`: 150, `chess/hard`: 250.
  - `math/easy`: 102, `math/medium`: 150, `math/hard`: 250.
- Public task ids include config, split, domain, row index, and `question_id`
  even though the audited views had no duplicates. This keeps ids stable when
  the same question namespace appears under different workload options.

## Files

- `__init__.py`: workload loader and DSPy signature.
- `source.py`: HF row → task payload mapping + helpers.
- `tools.py`: `build_tools()` → empty list.
