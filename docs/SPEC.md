# SPEC.md

## Intent

A clean-room implementation of a Recursive Language Model (RLM): an LLM that answers questions by writing and executing code in a persistent REPL, iterating until it calls `SUBMIT(answer=...)` or hits a budget. The project owns every layer — prompt assembly, parsing, REPL runtime, loop control — so each can be measured and optimized independently. Built on DSPy, which provides the Signature / Module / LM / Adapter vocabulary the project extends.

## Invariants

- Between completed REPL executions, the RLM loop terminates by `SUBMIT(...)`
  or an explicit iteration/token budget. The local REPL does not enforce a
  wall-time limit on model-generated Python.
- REPL state persists across iterations within a single task and is fully isolated across tasks.
- Each LM iteration sees the previous iteration's REPL output as feedback.
- The library layer (`rlmbenchy.rlm`) has no knowledge of workbench types; dependencies only flow workbench → library.
- The JSONL telemetry log is the contract between runtime and viewers — runs are fully reconstructable from it, no load-bearing state lives only in memory.
- Pytest is the canonical correctness contract — no change ships that breaks the suite.
- Plumbing before algorithm — HTTP, parsing, code execution, and termination must be reliable before algorithm changes ship.
- Configuration is composed, not monolithic: an LM profile, a workload spec, and a REPL spec combine into a run config.
- One execution path — one RLM loop, one workload surface, one logging model. No parallel implementations.

## Named roles

- **RLM loop** — runs the iterate-execute-feedback cycle; stops on `SUBMIT` or budget.
- **REPL runtime** — persistent Python execution; `execute(code) → output`; owns subprocess lifecycle.
- **LM** — produces the next code action given prompt state (DSPy's abstraction).
- **Executor** — orchestrates one task run: build LM, start REPL, drive the loop, return a `TaskRunResult`.
- **Logger** — emits the canonical JSONL telemetry event stream; the producer side of the log contract.
- **Workbench** — runs benchmarks and workloads on top of the library; the library never imports it.
- **Workload** — defines tasks, REPL tools, DSPy signature, and metadata; consumed by the Workbench.
- **LM profile** — reusable TOML-defined LM connection + request parameters.
- **Viewer** — consumes the JSONL telemetry log (TUI, web); reconstructs run state from the log alone.

## Soundness check

Before any change, ask:

1. Does any invariant get weakened?
2. Does any named role take on a responsibility outside its contract?
3. Did the intent shift?

All "no" → change is safe. Any "yes" → update this file (or `docs/RLM.md` if loop semantics change) first, then the code.
