# Workloads

Specifies the workload contract. `SPEC.md` gives the high-level invariants; this file gives the contract workloads must satisfy.

## Intent

A workload is a benchmark unit the workbench runs through the RLM library. It provides:

- The tasks (what to solve).
- The DSPy signature for those tasks (input/output shape for the LM).
- The dataset-specific tools for the REPL.
- Provenance metadata for logs.

The workload layer exists because the library is signature-agnostic — it doesn't know about datasets, task schemas, or task selection. Workloads answer all dataset-specific questions before the RLM loop starts.

## The contract

Defined in `rlmbenchy/datahub/types.py`.

**`WorkloadTask`** — one unit of work.

- `id`: stable benchmark identifier.
- `inputs`: model-facing dict; keys match the workload signature's input fields.
- `answer`: optional reference (gold label).
- `metadata`: host-side only (provenance, bookkeeping).

**`WorkloadBundle`** — the loaded workload.

- `workload_name`, `tasks`, `tools`, `signature` (DSPy), `metadata`.

**`WorkloadLoader`** — callable shape:

```python
def load_workload(
    task_limit: int | None,
    task_id: str | None,
    options: dict[str, Any],
) -> WorkloadBundle: ...
```

## Invariants

- One workload per run.
- `WorkloadTask.inputs` keys exactly match `WorkloadBundle.signature` input fields.
- `WorkloadTask.id` values are canonical ids for the loaded task, not blindly reused source ids. They are unique within a loaded `WorkloadBundle`.
- `WorkloadTask.metadata` and `WorkloadBundle.metadata` are host-side only; never passed to the model.
- Loader output is deterministic given the same source and options.
- Workload metadata is JSON-serializable.

## Task selection

- `task_id` is an exact selector after string trimming. It is not a prefix, substring, row offset, or pattern.
- Workloads must define how the canonical id is derived. Source-backed workloads should include the dimensions that make a task distinct, such as workload name, config, split, direction, template/query index, source row position, and the native source id when present.
- Native dataset ids belong in metadata unless they are already part of a canonical id. Authored local task files are stricter: explicit duplicate ids are invalid input rather than being silently rewritten.
- `task_id` selection is independent of `task_limit`; asking for one id must be able to find that id even when it is outside the default preview or smoke-run limit.
- For large or remote sources, loaders should push `task_id` into the source iteration path and stop once the selected task is found. Targeted inspection should not materialize the full archive just to select one row.
- `task_limit` applies to enumeration paths (`task_id is None`) and keeps preview/smoke loads bounded. Workloads may define whether the limit counts raw source rows or valid emitted tasks, but the behavior should be deterministic and documented locally when non-obvious.
- Duplicate canonical ids are rejected when a bundle is loaded. Targeted streaming lookup may stop at the first matching id for performance; use a full load or the audit helpers when the goal is to prove a source has no duplicates.

## Design choices

- **Signatures are per-workload, not shared.** The library doesn't own one fixed task schema. Different evaluation surfaces need different model input shapes; forcing one schema creates runner-level conditionals.
- **`task_limit` semantics are workload-owned.** Different selection models exist (authored tasks, dataset rows, authored queries over corpora); the loader API is shared, but "N tasks" means what the workload says it means.
- **Large corpora go behind tools, not into `inputs`.** Keeps prompts small, tool usage observable, and workload behavior intentional.

## Where this is in code

- Shared types: `rlmbenchy/datahub/types.py`.
- Workload registry: `rlmbenchy/datahub/workloads/__init__.py`.
- Per-workload loaders: `rlmbenchy/datahub/workloads/<name>/`.

To author a new workload, read an existing one in `rlmbenchy/datahub/workloads/` and follow the same shape.
