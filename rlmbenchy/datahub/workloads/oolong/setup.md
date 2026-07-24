# Setup

## What You Need

- Internet access to load the dataset from Hugging Face.
- Optional Hugging Face credentials if anonymous access is not enough in your
  environment.

## Defaults And Resolution

- Workload loader defaults:
  dataset `oolongbench/oolong-synth`, config `default`, split `test`
- Auth sources are tried in this order:
  workload `token`, `HF_TOKEN`, then `secrets.toml`
- `rlmbenchy run --workload oolong` uses the same workload loader defaults as the rest of DataHub.

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
uv run python -m rlmbenchy workloads tasks oolong --limit 1
```

If authenticated access is required:

```bash
uv run python -m rlmbenchy workloads tasks oolong --limit 1 -o token=hf_xxx
```

## Common Failure Modes

- `workloads tasks` succeeds locally, but the real run fails because network
  access is down.
- Anonymous dataset access fails and no Hugging Face token is configured.
- The runner default config is assumed to match the workload loader default
  when it does not.
- `max_rows` is set too low for the slice you are trying to inspect.
