# Logs

Specifies the RLM telemetry log contract. `SPEC.md` makes the log the contract
between runtime and viewers; this file gives the on-disk model.

## Intent

Every run produces an append-only JSONL telemetry log: the canonical record from
which the run can be reconstructed, replayed, and summarized. Viewers (TUI, web),
tests, and offline tooling all consume from this stream. No load-bearing
information lives only in memory.

The persisted format is OpenTelemetry-shaped. Domain-specific RLM event payloads
are preserved inside OTel log/event attributes rather than as a separate
legacy audit envelope.

## File Shape

- One JSONL file = one run.
- Each line is one `rlmbenchy_otel` record.
- Records are append-only and carry a monotonic `seq`.
- Record types:
  - `log` — one OpenTelemetry LogRecord-shaped event for every RLM domain event.
  - `span` — one completed OpenTelemetry span for paired lifecycle events.
  - `metric` — one OpenTelemetry metric measurement derived from usage, cost,
    duration, or correctness fields.

Batch execution is many independent run files plus an optional batch summary. No
merged logs.

## Common Envelope

Every record carries:

- `schema_name: "rlmbenchy_otel"`
- `schema_version: 1`
- `record_type`
- `record_id`
- `seq`
- `run_id`
- `trace_id`
- `resource` with `service.name=rlmbenchy`
- `scope` with `name=rlmbenchy.rlm`

Timestamps include ISO strings for local readability and `*_unix_nano` strings
for OpenTelemetry-style tooling compatibility.

`schema_version` is part of the reader gate. Current CLI, TUI, and web
projection code reject any value other than `1`.

The JSON Schema for this envelope lives at
`docs/schemas/otel-log-v1.schema.json`. It validates the common record envelope
and the required fields for `log`, `span`, and `metric` records. Event-specific
`body.data`, `body.stats`, and `body.summary` payloads remain intentionally
extensible.

## Log Records

Every RLM domain event is emitted as a `record_type: "log"` record.

Important fields:

- `event_name` uses the `rlmbenchy.<family>.<verb>` form, for example
  `rlmbenchy.llm.response`.
- `body.data`, `body.stats`, and `body.summary` preserve the factual RLM payload.
- `attributes.rlmbenchy.event_type` preserves the compact domain event type, for
  example `llm.response`.
- `attributes.rlmbenchy.event_id`, `rlmbenchy.event_seq`, `rlmbenchy.task_id`,
  `rlmbenchy.step_index`, `rlmbenchy.call_id`, and
  `rlmbenchy.parent_call_id` preserve lineage.
- `attributes.rlmbenchy.data`, `rlmbenchy.stats`, and `rlmbenchy.summary` mirror
  the body for span-event and projection compatibility.

`stats.run_elapsed_ms` is emitted for every domain event. It remains a
measurement, not part of event identity.

## Span Records

Completed lifecycle pairs produce `record_type: "span"` records:

- Run span: `run.started` to `run.finished`.
- Task span: `task.started` to `task.finished`.
- Step span: `step.started` to `step.finished`.
- GenAI span: `llm.request`/`subllm.request` to response or error.
- JSON-RPC span: `repl.request` to response, final, or error.
- Tool span: `tool.request` to response or error.

Span records carry deterministic `span_id` and `parent_span_id` values so logs,
spans, and metrics correlate without needing a live SDK in process.

The standard attributes intentionally use current OpenTelemetry semantic
conventions where they fit:

- GenAI: `gen_ai.operation.name`, `gen_ai.provider.name`,
  `gen_ai.request.model`, `gen_ai.usage.input_tokens`,
  `gen_ai.usage.output_tokens`, `gen_ai.response.finish_reasons`.
- JSON-RPC: `rpc.system.name=jsonrpc`, `jsonrpc.protocol.version=2.0`,
  `jsonrpc.request.id`, `rpc.method`, `rpc.response.status_code`.
- Errors: `error.type` and `exception.message`.

Project-specific facts stay under `rlmbenchy.*`.

## Metric Records

Metric records are emitted when a domain event contains the relevant measurement:

- `gen_ai.client.token.usage`
- `gen_ai.client.operation.duration`
- `rlmbenchy.gen_ai.client.cost`
- `rlmbenchy.run.duration`
- `rlmbenchy.task.duration`
- `rlmbenchy.step.duration`
- `rlmbenchy.repl.duration`
- `rlmbenchy.tool.duration`
- `rlmbenchy.task.correctness`

## Examples

These examples are shortened to show shape and naming. Real records include the
same envelope fields on every line and may include additional `rlmbenchy.*`
attributes.

`llm.response` log record:

```jsonc
{
  "schema_name": "rlmbenchy_otel",
  "schema_version": 1,
  "record_type": "log",
  "record_id": "run1:record:4",
  "seq": 4,
  "run_id": "run1",
  "trace_id": "0123456789abcdef0123456789abcdef",
  "resource": {"service.name": "rlmbenchy", "service.version": "0.1.0"},
  "scope": {"name": "rlmbenchy.rlm", "version": "0.1.0"},
  "event_id": "run1:event:4",
  "event_seq": 4,
  "time": "2026-03-07T12:00:04+00:00",
  "time_unix_nano": "1772884804000000000",
  "observed_time": "2026-03-07T12:00:04+00:00",
  "observed_time_unix_nano": "1772884804000000000",
  "span_id": "1111111111111111",
  "severity_text": "INFO",
  "severity_number": 9,
  "event_name": "rlmbenchy.llm.response",
  "body": {
    "data": {"model": "openai/gpt-4.1", "response_text": "SUBMIT(answer=4)"},
    "stats": {"run_elapsed_ms": 42, "elapsed_ms": 1200, "prompt_tokens": 10, "generated_tokens": 5},
    "summary": {"response_preview": "SUBMIT(answer=4)"}
  },
  "attributes": {
    "rlmbenchy.event_type": "llm.response",
    "rlmbenchy.event_id": "run1:event:4",
    "rlmbenchy.event_seq": 4,
    "rlmbenchy.run_id": "run1",
    "rlmbenchy.log.schema_version": 1,
    "rlmbenchy.task_id": "task_1",
    "rlmbenchy.step_index": 1,
    "rlmbenchy.call_id": "llm:1",
    "gen_ai.operation.name": "chat",
    "gen_ai.provider.name": "openai",
    "gen_ai.request.model": "openai/gpt-4.1",
    "gen_ai.usage.input_tokens": 10,
    "gen_ai.usage.output_tokens": 5,
    "rlmbenchy.data": {"model": "openai/gpt-4.1", "response_text": "SUBMIT(answer=4)"},
    "rlmbenchy.stats": {"run_elapsed_ms": 42, "elapsed_ms": 1200, "prompt_tokens": 10, "generated_tokens": 5},
    "rlmbenchy.summary": {"response_preview": "SUBMIT(answer=4)"}
  }
}
```

Completed GenAI span record:

```jsonc
{
  "schema_name": "rlmbenchy_otel",
  "schema_version": 1,
  "record_type": "span",
  "record_id": "run1:record:5",
  "seq": 5,
  "run_id": "run1",
  "trace_id": "0123456789abcdef0123456789abcdef",
  "resource": {"service.name": "rlmbenchy", "service.version": "0.1.0"},
  "scope": {"name": "rlmbenchy.rlm", "version": "0.1.0"},
  "span_id": "1111111111111111",
  "parent_span_id": "2222222222222222",
  "name": "chat openai/gpt-4.1",
  "span_kind": "CLIENT",
  "start_time": "2026-03-07T12:00:03+00:00",
  "start_time_unix_nano": "1772884803000000000",
  "end_time": "2026-03-07T12:00:04+00:00",
  "end_time_unix_nano": "1772884804000000000",
  "status": {"code": "OK"},
  "attributes": {
    "rlmbenchy.span.start_event_type": "llm.request",
    "rlmbenchy.span.end_event_type": "llm.response",
    "gen_ai.operation.name": "chat",
    "gen_ai.provider.name": "openai"
  },
  "events": [
    {"name": "rlmbenchy.llm.request", "time": "2026-03-07T12:00:03+00:00", "time_unix_nano": "1772884803000000000", "attributes": {"rlmbenchy.event_type": "llm.request"}},
    {"name": "rlmbenchy.llm.response", "time": "2026-03-07T12:00:04+00:00", "time_unix_nano": "1772884804000000000", "attributes": {"rlmbenchy.event_type": "llm.response"}}
  ]
}
```

Token metric record:

```jsonc
{
  "schema_name": "rlmbenchy_otel",
  "schema_version": 1,
  "record_type": "metric",
  "record_id": "run1:record:6",
  "seq": 6,
  "run_id": "run1",
  "trace_id": "0123456789abcdef0123456789abcdef",
  "resource": {"service.name": "rlmbenchy", "service.version": "0.1.0"},
  "scope": {"name": "rlmbenchy.rlm", "version": "0.1.0"},
  "time": "2026-03-07T12:00:04+00:00",
  "time_unix_nano": "1772884804000000000",
  "name": "gen_ai.client.token.usage",
  "description": "Number of input and output tokens used.",
  "unit": "{token}",
  "instrument_type": "histogram",
  "value": 10,
  "attributes": {
    "gen_ai.token.type": "input",
    "gen_ai.provider.name": "openai",
    "gen_ai.request.model": "openai/gpt-4.1",
    "rlmbenchy.run_id": "run1"
  }
}
```

## Event Ownership

Three producers, each at its natural boundary:

1. **Runner** — execution envelope + task boundary: `run.started`,
   `run.finished`, `task.started`, `task.finished`, optional `task.evaluated`.
2. **RLM loop** — step boundary: `step.started`, `step.finished`.
3. **DSPy callbacks** — call-level traces at the LM/tool boundary: `llm.*`,
   `repl.*`, `tool.*`, `subllm.*`, optional `adapter.*`.

## Event Families

- **Lifecycle**: `run.started`, `run.finished`, `task.started`,
  `task.finished`, `step.started`, `step.finished`, optional `task.evaluated`.
- **Main LM**: `llm.request`, `llm.response`, `llm.error`.
- **REPL**: `repl.request`, `repl.response`, `repl.error`, `repl.final`.
- **Tools**: `tool.request`, `tool.response`, `tool.error`.
- **Sub-LLM**: `subllm.request`, `subllm.response`, `subllm.error`.
- **Adapter (optional)**: `adapter.format_start`, `adapter.format_end`,
  `adapter.parse_start`, `adapter.parse_end`.

## Invariants

- Append-only. No mutation of past records.
- Terminal events (`step.finished`, `task.finished`, `run.finished`) carry
  factual outcomes only.
- `final_outputs` may appear on either `repl.final.body.data` (SUBMIT path) or
  `step.finished.body.data` (extract-fallback path). These two shapes are
  mutually exclusive per step, not a fallback pair.
- Summaries, step narratives, and activity rollups are derived in the projection
  layer from child events. Never duplicated into terminal events.
- Lineage is explicit on every relevant event through `rlmbenchy.*` attributes.
- Raw OTel records remain accessible; viewers project them but never hide them.

## Projection Layer

`rlmbenchy/logger/projection.py` turns raw telemetry rows into a shared viewer
model:

- Reconstructs run / task / step / call structure.
- Derives step narratives and usage summaries from child events.
- Provides one shared interpretation consumed by every viewer.

The projection accepts only the current `rlmbenchy_otel` schema. Older audit v2
logs must be migrated before they can be loaded by the CLI, TUI, or web viewer.
Consumers should prefer `rlmbenchy.logger.api` or the package-root API exports
over importing the projection layer directly.

## Migration From Audit V2

There is no compatibility reader for audit v2 logs in this branch. A migrated
file must be rewritten as JSONL where every row has:

- `schema_name: "rlmbenchy_otel"`
- `schema_version: 1`
- an OTel-shaped `record_type: "log"` row for each legacy domain event
- optional derived `span` and `metric` rows

The projection only needs `log` rows to reconstruct a run. Spans and metrics
provide OpenTelemetry-style trace and measurement context for downstream tools.

## Shared Viewer Semantics

Console, TUI, and web may differ in presentation but must agree on:

- What a step is.
- What counts as a main LM call vs a sub-LLM call.
- What counts as the step result, error, or final outputs.
- How aggregate numbers are derived.

## Where This Is In Code

- Logger and OTel conversion: `rlmbenchy/logger/`.
- Public read API: `rlmbenchy/logger/api.py`.
- Projection: `rlmbenchy/logger/projection.py`.
- Viewers: `rlmbenchy/visualizers/tui/`, `rlmbenchy/visualizers/web/`.
