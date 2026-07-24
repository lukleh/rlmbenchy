# Contributing

Contributions are welcome. This is an experimental source-first project, so
changes should keep the runtime behavior, tests, and documentation aligned.

## Setup

Install Python 3.12 or 3.13 and `uv`, then run:

```bash
uv sync --frozen --dev
```

The web viewer additionally requires a current Node.js release:

```bash
npm --prefix rlmbenchy/visualizers/web ci
```

## Checks

Run these before submitting a pull request:

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest -q
npm --prefix rlmbenchy/visualizers/web run typecheck
npm --prefix rlmbenchy/visualizers/web run build
```

Tests marked `live_llm` use real model providers and may cost money. They are
excluded from the default test command and should not be required for ordinary
pull requests.

## Pull requests

Keep changes focused, add tests for behavior changes, update relevant docs, and
include the validation commands you ran. Never commit credentials, private
datasets, generated run outputs, or sensitive log files.
