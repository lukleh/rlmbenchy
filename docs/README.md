# Docs

## Specifications

- `SPEC.md` — project intent, invariants, named roles, soundness check.
- `RLM.md` — RLM loop algorithm and divergences from the paper.
- `WORKLOADS.md` — workload contract.
- `LOGS.md` — telemetry log event contract.
- `GLOSSARY.md` — terms used across the above.

## Schemas

- `schemas/otel-log-v1.schema.json` — JSON Schema for one
  `rlmbenchy_otel` JSONL record.

## Orientation

- `ARCHITECTURE.md` — one-page map: flow, layers, pointers.
- `SIMPLIFICATION_PLAN.md` — phased plan for reducing accidental complexity.

## Reference

- `reference/2512.24601v2.md` — Markdown conversion of RLM paper v2;
  [original paper](https://arxiv.org/abs/2512.24601v2).
- `reference/2512.24601v3.md` — Markdown conversion of RLM paper v3;
  [original paper](https://arxiv.org/abs/2512.24601v3).
- `reference/README.md` — attribution and license details for the converted
  paper text and extracted figures.
- `reference/gepa-vista-related-work.md` — GEPA, VISTA, and related
  prompt optimization reading notes.

## Other

- `PACKAGING.md` — flat vs `src/` layout rationale.
- `guides/REVIEW_PROMPT_ADDITIONS.md` — repo-specific review guidance.
