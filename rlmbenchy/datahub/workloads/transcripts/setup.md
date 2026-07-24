# Setup

## What You Need

- A transcript root directory containing hashed transcript folders.
- A JSON task-spec file selecting transcripts for each task.
- Optional runtime config file:
  `~/.config/lukleh/rlmbenchy/transcripts.toml`
  or the equivalent path under `RLMBENCHY_CONFIG_DIR`.

The transcript root is expected to look like:

```text
<root>/
  <64-hex-hash-a>/transcript.txt
  <64-hex-hash-b>/transcript.txt
```

## Defaults And Resolution

- `root` precedence:
  workload option `root` -> `transcripts.toml` -> runtime-share default
- `tasks_path` precedence:
  workload option `tasks_path` -> `transcripts.toml` -> runtime-share
  default
- Explicit path options resolve from the current working directory.
- Paths inside `transcripts.toml` resolve relative to that config file.

To inspect the runtime-share and config directories:

```bash
uv run python -m rlmbenchy paths
```

## Minimal Setup

Either:

- populate the default runtime-share locations, or
- point the workload at explicit paths every time, or
- set the paths once in `transcripts.toml`

To seed the default task file from the repo copy:

```bash
cp rlmbenchy/datahub/workloads/transcripts/tasks.example.json /path/to/runtime-share/workloads/transcripts/tasks.json
```

Minimal config example:

```toml
root = "/abs/path/to/transcripts"
tasks_path = "/abs/path/to/tasks.json"
```

## Verify Setup

If you pass paths explicitly:

```bash
uv run python -m rlmbenchy workloads tasks transcripts --limit 1 -o root=/abs/path/to/transcripts -o tasks_path=/abs/path/to/tasks.json
```

If you rely on `transcripts.toml` or the runtime-share defaults, omit the
path options from those commands.

## Common Failure Modes

- `root` points to the wrong directory level instead of the folder that
  directly contains the 64-hex transcript directories.
- Transcript directories exist, but `transcript.txt` is missing or empty.
- The task-spec selectors reference hashes that are not present under `root`.
- A relative `root` or `tasks_path` override resolves from a different working
  directory than expected.
- Relative paths inside `transcripts.toml` are assumed to resolve from
  the shell instead of from the config file location.
