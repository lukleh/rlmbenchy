# Run Profiles

Run profiles are optional TOML files that wire workloads to one or more LM
profiles.

Use a run profile when you want to bundle:

- `lm_profile = "model-..."`
- optional `sub_lm_profile = "model-..."`
- `workload` and `[workload.options]`
- `task_limit`
- `adapter_mode`
- `log_dir`

Keep LM endpoint/model/request settings in `rlmbenchy/resources/lm_profiles/`. Run profiles
should reference those LM profiles rather than embedding a second LM definition.

Example:

```toml
lm_profile = "model-chatgpt-gpt-5.4_low"
sub_lm_profile = "model-openrouter-qwen-qwen3-14b"
workload = "tasks_v0"
task_limit = 1
```
