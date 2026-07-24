# Setup

## What You Need

- Internet access to stream the dataset from Hugging Face.
- Optional Hugging Face credentials if anonymous streaming is not enough
  in your environment.

## Defaults And Resolution

- Default dataset: `LongHorizonReasoning/longcot`.
- Default config: `logic`.
- Default split: `easy`.
- Default `max_rows`: `5` (small, meant for smoke-testing; override for
  real evaluation). Explicit `--task-id` lookups ignore this cap and scan
  the full selected split.
- Auth sources are tried in this order:
  workload option `token`, environment `HF_TOKEN`, then `secrets.toml`.

If you keep the token in `secrets.toml`, use:

```toml
[providers.huggingface]
token = "hf_xxx"
```

## Minimal Setup

- Start with anonymous access first. The dataset is public.
- If dataset streaming fails with auth errors, rerun with
  `-o token=hf_xxx` or set `HF_TOKEN`.

## Verify Setup

```bash
uv run python -m rlmbenchy workloads tasks longcot --limit 1
```

Override the config/split/limit for a quick smoke across domains:

```bash
uv run python -m rlmbenchy workloads tasks longcot --limit 3 -o config=math -o split=hard
uv run python -m rlmbenchy workloads tasks longcot --limit 1 -o config=cs
```

If you use `config=all`, task ids are domain-qualified to stay unique across
domains, for example `math_401` or `chess_401`.

## Common Failure Modes

- Anonymous dataset access fails and no Hugging Face token is configured.
- `config` is set to a value outside `all / logic / cs / chemistry / chess /
  math`.
- `split` is set to a value outside `easy / medium / hard`.
- `max_rows` is set too low (defaults to 5 for the smoke path; pass
  `-o max_rows=500` or higher for a benchmark-scale run).
