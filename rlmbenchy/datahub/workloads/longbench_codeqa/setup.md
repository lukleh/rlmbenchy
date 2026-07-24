# Setup

## What You Need

- Internet access to load the dataset from Hugging Face.
- Optional Hugging Face credentials if anonymous access is not enough in your
  environment.

## Defaults And Resolution

- Default dataset: `zai-org/LongBench-v2`
- Default config: `default`
- Default split: `train`
- Auth sources are tried in this order:
  workload `token`, `HF_TOKEN`, then `secrets.toml`
- This workload filters the dataset to `sub_domain == "Code repo QA"` after
  loading rows.

If you keep the token in `secrets.toml`, use:

```toml
[providers.huggingface]
token = "hf_xxx"
```

## Minimal Setup

- Start with anonymous access first.
- If dataset access fails, rerun with `-o token=hf_xxx` or set `HF_TOKEN`.
- If the first probe finds no CodeQA rows, increase `max_rows`.

## Verify Setup

```bash
uv run python -m rlmbenchy workloads tasks longbench_codeqa --limit 1 -o max_rows=300
```

If authenticated access is required:

```bash
uv run python -m rlmbenchy workloads tasks longbench_codeqa --limit 1 -o max_rows=300 -o token=hf_xxx
```

## Common Failure Modes

- `workloads tasks` succeeds locally, but the real run fails because network
  access is down.
- Anonymous dataset access fails and no Hugging Face token is configured.
- `max_rows` is too small, so no `Code repo QA` rows are found in the scanned
  window.
- The workload is treated like generic LongBench rows instead of the filtered
  CodeQA slice.
