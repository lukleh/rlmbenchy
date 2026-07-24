# Glossary

Terms used across the SPEC-family docs. Listed by area — core loop first, then scope, workloads, logging.

## Core loop

- **RLM loop** — the iterate-execute-feedback cycle: LM emits reasoning + code → REPL executes → output feeds back → stop on `SUBMIT` or budget.
- **step** — one iteration of the RLM loop (one LM call + one REPL execution).
- **REPL** — the persistent Python interpreter the RLM loop drives. State (variables, imports) persists across steps within a task; isolated across tasks.
- **budget** — iteration / token / wall-time cap that bounds the loop.
- **SUBMIT** — the function (injected into the REPL) the LM's code calls to terminate a task with a final answer.
- **extract (fallback)** — a separate LM call that produces a final answer from accumulated history if the loop hits a budget without `SUBMIT`. Ours, not in the paper.
- **sub-LLM / `llm_query`** — bounded LM call from within REPL code, for semantic sub-tasks (summarize, extract, classify). Distinct from the main LM.

## Task and run scope

- **task** — one unit of benchmark work: a DSPy signature + one set of input values + optional reference answer.
- **run** — the execution/logging envelope around one or more tasks. Today runs are 1:1 with tasks; the distinction keeps future multi-task runs a schema-safe change.

## Workload layer

- **workload** — a benchmark unit: a set of tasks plus the DSPy signature, REPL tools, and metadata they need. Lives in `rlmbenchy/datahub/workloads/`.
- **workbench** — the library-consuming layer that loads workloads and configs and drives the RLM library against them.

## Logging

- **telemetry log (JSONL)** — canonical append-only OpenTelemetry-shaped event stream per run. One file = one run. The contract between runtime and viewers.
- **projection** — derivation layer that turns raw events into a viewer-friendly model (reconstructs run/task/step/call structure, derives summaries). In `rlmbenchy/logger/projection.py`.
- **call** (as in `call_id`) — one request/response pair at the LM, tool, REPL, or sub-LLM boundary. A step contains multiple calls.
