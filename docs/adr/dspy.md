# ADR — DSPy Dependence

**Status:** Accepted
**Date:** 2026-04-19
**Context:** Phase 7 of `docs/SIMPLIFICATION_PLAN.md`

## Problem

The project imports DSPy across six modules. Before we rework any of those
surfaces, we want to record — once, deliberately — how much DSPy we intend to
carry and why. The alternative to recording this is drift: future cleanup
decisions made per-file without the bigger picture.

## Current DSPy Surface

Where DSPy appears today (paths at time of writing):

- `rlmbenchy/rlm/rlm.py` — `class RLM(dspy.Module)`; uses
  `dspy.Signature`, `dspy.Tool`, and DSPy's REPL primitives
  (`CodeInterpreter`, `FinalOutput`, `REPLHistory`, `REPLVariable`).
- `rlmbenchy/rlm/signatures.py` — builds signatures dynamically via
  `dspy.make_signature`, `dspy.InputField`, `dspy.OutputField`.
- `rlmbenchy/rlm/lm.py` — subclasses `dspy.LM` with
  `ChatGPTResponsesLM` for the ChatGPT Responses transport; `build_lm()`
  returns `dspy.LM` instances.
- `rlmbenchy/rlm/runtime.py` — `build_adapter()` returns
  `dspy.ChatAdapter` or `dspy.JSONAdapter`; `LMLoggingCallback` implements
  `dspy.utils.callback.BaseCallback`.
- `rlmbenchy/rlm/executor.py` — wraps callables as `dspy.Tool` and
  consumes `dspy.Prediction`.
- `rlmbenchy/rlm/reasoning.py` — one monkey-patch on
  `dspy.adapters.types.reasoning.Reasoning.adapt_to_native_lm_feature`.
  The patch exists because the ChatGPT Responses transport is not in
  LiteLLM's `model_cost` map, so DSPy's default "does this model support
  native reasoning?" check returns `False` even though the endpoint does
  surface reasoning. The patch forces the reasoning field to remain in
  the signature for that one transport.

## What We Actually Use

- **Used**: `dspy.Module` (base class for `RLM`), `dspy.Signature`
  (+builder), `dspy.LM` (+subclass for ChatGPT Responses), `dspy.Tool`,
  `dspy.Prediction`, `dspy.ChatAdapter`, `dspy.JSONAdapter`,
  `BaseCallback` (for logging), `CodeInterpreter` / `FinalOutput` /
  `REPLHistory` / `REPLVariable` (REPL primitives).
- **Not used**: `dspy.ChainOfThought`, `dspy.Predict`,
  optimizers/teleprompters, DSPy's evaluate framework, DSPy's assertions.

## What DSPy Gives Us Cheaply

- **Response caching and retries** on LM calls (via `dspy.LM`).
- **Adapter-based response parsing** (ChatAdapter, JSONAdapter) — a
  non-trivial amount of free handling for structured output extraction
  and JSON-mode fallback.
- **Callback infrastructure** (`BaseCallback`, `ACTIVE_CALL_ID`) that
  `LMLoggingCallback` piggybacks on for telemetry-log hooks around every LM
  and tool call. Recreating this would be a small observability
  framework in its own right.
- **REPL primitives** (`CodeInterpreter`, `FinalOutput`,
  `REPLHistory`, `REPLVariable`) for the RLM loop; these are the shape
  our loop already speaks.

## What We Pay

- Version pin at `dspy==3.2.1` — any DSPy bump must be treated as a
  surface-area review.
- One monkey-patch (`reasoning.py`). Tight coupling to DSPy's internal
  `Reasoning.adapt_to_native_lm_feature` classmethod. If DSPy refactors
  that method, our patch silently breaks (reasoning field may disappear
  from prompts on ChatGPT Responses runs).
- Signature-builder ceremony: callers use `build_task_signature()` which
  returns a `type[dspy.Signature]`; DSPy types leak into
  `build_lm()`'s return type and `RLM`'s public surface. Library users
  see DSPy classes.
- Debugging signature/adapter behavior means reading DSPy source, not
  our own code.

## Options Considered

### A. Keep DSPy, narrow surface

Hide `dspy.Signature`/`dspy.Module` behind internal adapters so the
library's public surface doesn't leak DSPy types. Keep LM callbacks,
keep the LM subclass, keep REPL primitives. Document the monkey-patch
risk explicitly so future DSPy bumps trigger a check.

- Effort: ~2 days.
- Risk: Low. No observable behavior change; mostly type-signature tidying.
- Outcome: Easier to swap DSPy later if we ever decide to; clearer
  boundary today.

### B. Replace DSPy with direct LM integration

Rewrite `RLM` to not inherit `dspy.Module`; reimplement adapters
(response-to-dict parsing); wire our own LM client with caching and
retries; rewrite the callback infrastructure that `LMLoggingCallback`
depends on.

- Effort: ~5–7 days.
- Risk: Medium-to-high. Touches the RLM loop, logging, response
  handling, and the telemetry log contract. Every rewritten piece is a new
  bug surface.
- Losses to rebuild: LM-level caching, retry logic, adapter-style
  response parsing, callback event hooks, reasoning-field signature
  logic. Each has a DSPy equivalent we'd be re-creating.

## Decision

**Accept Option A: keep DSPy, narrow its surface.**

Reasons:

1. The callback infrastructure is load-bearing for `LMLoggingCallback`.
   We haven't found evidence that DSPy's callback model constrains us;
   re-creating it is pure cost.
2. Response caching and retry behavior come free. We have no cached
   reason to regret them.
3. The monkey-patch is a single point of coupling, not a distributed
   problem. If DSPy breaks it, we'll know immediately (reasoning stops
   surfacing on ChatGPT Responses runs) and the fix is localized.
4. Phases 1–6 of the simplification plan already deliver the bulk of
   the accidental-complexity reduction. The DSPy surface is real
   complexity, but it earns its keep.

## Revisit Triggers

Come back to this decision if any of these happen:

- DSPy refactors `Reasoning.adapt_to_native_lm_feature` and our
  monkey-patch breaks twice in a single quarter.
- A DSPy dependency upgrade becomes blocking (transitive conflicts
  with another critical library).
- We need a feature DSPy actively resists (e.g. a new transport shape
  that can't fit the `dspy.LM` mold without its own monkey-patch).

## Next Actions (when acted on in a future session)

Not in this change set. Sequenced proposal for when we do act:

1. Move `signatures.py` behind an internal boundary so that callers go
   through `rlmbenchy.rlm.build_task_signature` and receive an opaque
   handle, not a `type[dspy.Signature]`. Keeps the signature mechanics
   where they already live; hides the DSPy type.
2. Make `RLM.forward` return a native `TaskRunResult` directly instead
   of a `dspy.Prediction`, so callers never touch DSPy's prediction
   object.
3. Add a short section to `docs/ARCHITECTURE.md` naming DSPy as a
   load-bearing dependency and linking to this ADR. One inbound link is
   enough; the ADR is the canonical record.

None of these are urgent. Phases 1–6 land first.
