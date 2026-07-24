# Setup

## What You Need

- Internet access on first load so the OPUS archive can be downloaded.
- A writable runtime cache directory for the downloaded ZIP.
- No Hugging Face token is required for this adapter.

## Defaults And Resolution

- Default config: `en-hi`
- Supported split today: `train`
- Default direction: `forward`
- Archive cache location:
  `<runtime cache dir>/datahub/open_subtitles`
- Typical default cache path:
  `~/.cache/lukleh/rlmbenchy/datahub/open_subtitles`

To inspect your runtime directories:

```bash
uv run python -m rlmbenchy paths
```

## Minimal Setup

- No pre-download step is required.
- The first real workload load will download and cache the archive for the
  selected language pair.

## Verify Setup

```bash
uv run python -m rlmbenchy workloads tasks open_subtitles --limit 1 -o max_rows=1
```

## Common Failure Modes

- `workloads tasks` succeeds locally, but the archive download fails because
  network access is unavailable.
- `split` is set to something other than `train`.
- `config` is malformed instead of using a language-pair shape like `en-hi`.
- The first run is assumed to be broken when it is only slower because the
  archive is being downloaded and cached.
