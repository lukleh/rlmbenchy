# DataHub

Single point for builtin workload definitions, workload loading, and workload scoring.

For the workload layer's contract and invariants, see
[`docs/WORKLOADS.md`](../../docs/WORKLOADS.md).
Remote datasets are not bundled with this repository. Their source, observed
license metadata, and attribution are recorded in
[`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md#dataset-integrations).

## Structure

- `rlmbenchy/datahub/types.py`: core types such as `WorkloadTask` and `WorkloadBundle`
- `rlmbenchy/datahub/registry.py`: builtin-only workload lookup and loading
- `rlmbenchy/datahub/scoring.py`: `score_answer()` for workload evaluation
- `rlmbenchy/datahub/workloads/catalog_builtins.py`: builtin workload registration
- `rlmbenchy/datahub/workloads/support/`: shared helpers for manifests, dataset loading, filtering, and generic workload execution
- `rlmbenchy/datahub/workloads/`: canonical builtin workload packages

Task ids are exact, trimmed selectors. For source-backed workloads, derive a
canonical task id from the dimensions that make the task unique instead of
trusting a native source id by itself. For authored local task files, duplicate
explicit ids are invalid input. Use `rlmbenchy.datahub.workloads.support.task_selection`
in loaders and `rlmbenchy.datahub.workloads.support.task_id_audit` when auditing source
rows before they are materialized as workload tasks.

Each workload directory keeps:

- `README.md` for data/task/tool shape
- `setup.md` for prerequisites and first-run setup
- `source.py` and `tools.py` where needed

## Available Workloads

| Name | Source | Docs |
|---|---|---|
| `tasks_v0` | Local JSON (algorithmic tasks) | [`README`](workloads/tasks_v0/README.md), [`setup`](workloads/tasks_v0/setup.md) |
| `check_contract` | Local JSON (contract check tasks) | [`README`](workloads/check_contract/README.md), [`setup`](workloads/check_contract/setup.md) |
| `check_adapter_matrix` | Local JSON (adapter test tasks) | [`README`](workloads/check_adapter_matrix/README.md), [`setup`](workloads/check_adapter_matrix/setup.md) |
| `browsecomp_plus` | Hugging Face dataset `Tevatron/browsecomp-plus` | [`README`](workloads/browsecomp_plus/README.md), [`setup`](workloads/browsecomp_plus/setup.md) |
| `oolong` | Hugging Face dataset `oolongbench/oolong-synth` | [`README`](workloads/oolong/README.md), [`setup`](workloads/oolong/setup.md) |
| `oolong_pairs` | Derived from `oolongbench/oolong-synth` with fixed query templates | [`README`](workloads/oolong_pairs/README.md), [`setup`](workloads/oolong_pairs/setup.md) |
| `open_subtitles` | OPUS OpenSubtitles archive | [`README`](workloads/open_subtitles/README.md), [`setup`](workloads/open_subtitles/setup.md) |
| `longbench_codeqa` | Hugging Face dataset `zai-org/LongBench-v2` | [`README`](workloads/longbench_codeqa/README.md), [`setup`](workloads/longbench_codeqa/setup.md) |
| `s_niah` | Synthetic needle-in-a-haystack task generation | [`README`](workloads/s_niah/README.md), [`setup`](workloads/s_niah/setup.md) |
| `transcripts` | Local transcript corpora plus task spec | [`README`](workloads/transcripts/README.md), [`setup`](workloads/transcripts/setup.md) |

## Usage

```python
from rlmbenchy.datahub import AVAILABLE_WORKLOADS, load_workload, score_answer

bundle = load_workload("tasks_v0", task_limit=5)
for task in bundle.tasks:
    print(task.id, task.inputs)
```

## CLI Surface

Use the main `rlmbenchy` command for workload discovery and execution:

```bash
uv run rlmbenchy workloads list
uv run rlmbenchy workloads tasks tasks_v0 --limit 3
uv run rlmbenchy workloads task tasks_v0 <task_id>
uv run rlmbenchy run --config config/run_profiles/smoke-3-tasks-v0-oss.toml
```
