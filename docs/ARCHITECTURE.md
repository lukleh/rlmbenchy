# Architecture at a glance

A one-page map of how the parts fit together. `SPEC.md` is the source of truth for intent and invariants; this file is orientation.

## Flow

```text
workbench (optional)
  load LM profile + workload bundle → build run config
  call run_task(...)
    Logger: run.started / task.started
    Executor: build LM + adapter, start REPL, inject tools
               (SUBMIT, llm_query, workload tools)
    RLM loop, per step:
      LM emits reasoning + code
      REPL executes code (persistent state across steps)
      stdout fed back on the next iteration
      SUBMIT(...) raises FinalOutput → loop ends
    Logger: task.finished / task.evaluated / run.finished
  return TaskRunResult
```

If the loop hits a budget without `SUBMIT`, the extract fallback produces a final answer (see `RLM.md`).

## Layers

| Layer | Package | What it owns |
|---|---|---|
| Library | `rlmbenchy.rlm` | RLM loop, REPL runtime, LM factory, executor |
| Workbench | `rlmbenchy.workbench` | Loads configs and workloads; drives the library for benchmarks |
| Workloads | `rlmbenchy/datahub/` | Tasks, tools, signatures — the benchmark content |
| Logger | `rlmbenchy.logger` | Emits the canonical JSONL telemetry stream |
| Viewers | `rlmbenchy.visualizers` | TUI and web; consume JSONL (define the log contract) |

## Where to go for details

- Intent, invariants, named roles — `SPEC.md`
- Loop algorithm, paper divergences — `RLM.md`
- Paper — `reference/2512.24601v2.md`
