# Setup

## What You Need

- Internet access to load the base OOLONG dataset from Hugging Face.
- Optional Hugging Face credentials if anonymous access is not enough in your
  environment.

## Defaults And Resolution

- Default dataset: `oolongbench/oolong-synth`
- Default config: `default`
- Default split: `test`
- Default `query_index`: `0`
- Auth sources are tried in this order:
  workload `token`, `HF_TOKEN`, then `secrets.toml`
- `query_index` only changes the prompt template selection. It does not change
  the underlying data access requirements.

If you keep the token in `secrets.toml`, use:

```toml
[providers.huggingface]
token = "hf_xxx"
```

## Minimal Setup

- Start with anonymous access first.
- If dataset access fails, rerun with `-o token=hf_xxx` or set `HF_TOKEN`.

## Verify Setup

```bash
uv run python -m rlmbenchy workloads tasks oolong_pairs --limit 1
```

If authenticated access is required:

```bash
uv run python -m rlmbenchy workloads tasks oolong_pairs --limit 1 -o token=hf_xxx
```

## Common Failure Modes

- `workloads tasks` succeeds locally, but the real run fails because network
  access is down.
- Anonymous dataset access fails and no Hugging Face token is configured.
- The selected `query_index` is mistaken for a dataset split or config selector.
- The workload is treated like it has expected answers even though it is
  intentionally open-ended.
