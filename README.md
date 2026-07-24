# rlmbenchy

A clean-room Recursive Language Model (RLM) implementation for experimentation. An RLM is an LLM that writes and executes code in a persistent REPL to answer questions, iterating until it calls `SUBMIT(...)` or hits a budget. Built on DSPy.

See the [documentation](https://github.com/lukleh/rlmbenchy/tree/main/docs):
start with the [specification](https://github.com/lukleh/rlmbenchy/blob/main/docs/SPEC.md)
for intent and invariants, the [architecture map](https://github.com/lukleh/rlmbenchy/blob/main/docs/ARCHITECTURE.md)
for a one-page overview, and the [documentation index](https://github.com/lukleh/rlmbenchy/blob/main/docs/README.md)
for the full set.

This is experimental research software. The repository builds a self-contained
Python wheel with the CLI, builtin workloads, LM profiles, and web viewer
assets.

## Prerequisites

- Python 3.12 or 3.13
- [uv](https://docs.astral.sh/uv/)
- Docker when using the Docker REPL backend

## Quick Start

From a checkout:

```bash
git clone https://github.com/lukleh/rlmbenchy.git
cd rlmbenchy
uv sync --frozen --dev
```

From a built wheel (`dist/` is not checked in, so build it first):

```bash
uv build
uv tool install ./dist/rlmbenchy-*.whl
rlmbenchy workloads list
```

## Main Commands

```bash
uv run rlmbenchy paths
uv run rlmbenchy run --config <run-config.toml>
uv run rlmbenchy workloads list
uv run rlmbenchy workloads tasks tasks_v0 --limit 3
uv run rlmbenchy logs latest
uv run python -m rlmbenchy.visualizers.web --help
uv run python -m rlmbenchy.visualizers.tui --help
```

## Library Use

The supported library surface is `rlmbenchy.rlm`. It is importable from both a
checkout and an installed distribution.

```python
from rlmbenchy.rlm import (
    LocalProcessReplRuntime,
    RLMRunConfig,
    SignatureFieldSpec,
    build_task_signature,
    load_lm_profile,
    resolve_lm_profile_path,
    run_task,
)

signature = build_task_signature(
    name="ExampleTask",
    instructions="Answer the question using the provided context.",
    inputs=[
        SignatureFieldSpec("query", str, "Question to answer."),
        SignatureFieldSpec("context", str, "Supporting context."),
    ],
    outputs=[
        SignatureFieldSpec("answer", str, "Final answer."),
    ],
)

task_run, _logger = run_task(
    signature=signature,
    run_config=RLMRunConfig(
        api_base="https://openrouter.ai/api/v1",
        model="openrouter/openai/gpt-oss-20b",
        api_key="...",
        adapter_mode="chat",
        request_kwargs={"temperature": 0.0},
    ),
    task_inputs={"query": "What is 2 + 2?", "context": "Arithmetic only."},
    runtime=LocalProcessReplRuntime(),
)

print(task_run.final_outputs["answer"])
```

Applications should keep domain-specific signatures, tools, clients, and task
context in the application repository. `rlmbenchy.rlm` supplies the generic RLM
runtime plus LM profile loading; it does not need to import or register the
application.

## Execution, Costs, and Data

- Live runs call model providers and may cost money. The default pytest suite
  excludes tests marked `live_llm`; opt in only when you intend to use real
  credentials and incur provider usage.
- `LocalProcessReplRuntime` executes model-generated Python with the current
  user's filesystem, network, and environment access. Use it only with models
  and inputs you trust. The Docker backend provides a more isolated runtime.
- JSONL logs intentionally preserve configuration, prompts, generated code,
  model responses, and tool results for reproducibility. Do not run sensitive
  inputs unless storing those details in the configured log directory is
  acceptable.
- The web viewer has no authentication and defaults to `127.0.0.1`. Binding it
  to `0.0.0.0` can expose complete run logs to other machines on the network.
- Remote dataset workloads download data under the upstream dataset's terms.
  See the [third-party notices](https://github.com/lukleh/rlmbenchy/blob/main/THIRD_PARTY_NOTICES.md#dataset-integrations).

### Experimental ChatGPT subscription transport

The bundled ChatGPT LM profiles provide an experimental compatibility path for
running against the Codex Responses backend with an existing ChatGPT
subscription. This is not a stable OpenAI Platform API:

- requests go directly to the Codex Responses backend and identify their
  originator as `rlmbenchy`;
- authentication reads a current access token from a file-backed
  `~/.codex/auth.json` (or `$CODEX_HOME/auth.json`);
- rlmbenchy never refreshes tokens or modifies the Codex credential file;
- create or update the required file-backed login with
  `codex login -c cli_auth_credentials_store=file`, then retry;
- Codex credentials stored only in an operating-system keyring are not
  available to this compatibility transport;
- file-backed Codex authentication stores sensitive tokens in plaintext;
  protect `auth.json` like a password;
- an OpenAI Platform API key is not interchangeable with a ChatGPT/Codex OAuth
  access token.

The backend protocol may change without notice. Prefer a normal OpenAI Platform
profile when stability is more important than subscription-backed experiments.

## Layout

- `rlmbenchy/rlm` — reusable RLM runtime (library)
- `rlmbenchy/workbench` — config loading and workload execution
- `rlmbenchy/logger` — JSONL telemetry log producer, stable read API, and shared projection layer
- `rlmbenchy/visualizers` — TUI and web viewers
- `rlmbenchy/datahub` — builtin workloads, manifests, and scoring
- `rlmbenchy/resources/lm_profiles` — bundled LM profiles
- `docs/` — project documentation

Runtime defaults:

- config and overrides: `~/.config/lukleh/rlmbenchy/`
- state and logs: `~/.local/state/lukleh/rlmbenchy/`
- cache: `~/.cache/lukleh/rlmbenchy/`

Use `uv run rlmbenchy paths` to print the resolved directories, including any `RLMBENCHY_*_DIR` overrides.

## Project Policies

- [Contributing](https://github.com/lukleh/rlmbenchy/blob/main/CONTRIBUTING.md)
- [Security](https://github.com/lukleh/rlmbenchy/blob/main/SECURITY.md)
- [Third-party notices](https://github.com/lukleh/rlmbenchy/blob/main/THIRD_PARTY_NOTICES.md)
- [MIT license](https://github.com/lukleh/rlmbenchy/blob/main/LICENSE)
