# Setup

## What You Need

- Internet access to load the dataset from Hugging Face.
- Optional Hugging Face credentials if anonymous access is not enough in your
  environment.

## Defaults And Resolution

- Default dataset: `Tevatron/browsecomp-plus`
- Default config: `default`
- Default split: `test`
- Auth sources are tried in this order:
  workload `token`, `HF_TOKEN`, then `secrets.toml`
- `max_docs_per_task` and `max_docs_per_tool_call` are optional tuning knobs,
  not setup requirements.

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
uv run python -m rlmbenchy workloads tasks browsecomp_plus --limit 1
```

If authenticated access is required:

```bash
uv run python -m rlmbenchy workloads tasks browsecomp_plus --limit 1 -o token=hf_xxx
```

## Common Failure Modes

- `workloads tasks` succeeds locally, but a real run fails because network
  access is down.
- Anonymous dataset access fails and no Hugging Face token is configured.
- A token is configured in one shell, but `workloads tasks` is run from another
  shell without `HF_TOKEN`.
- `max_docs_per_task` or `max_docs_per_tool_call` are treated as required setup
  instead of optional limits.
