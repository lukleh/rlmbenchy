run_profiles_dir := "config/run_profiles"
default_web_host := "127.0.0.1"
rlmbenchy_cli := "-m rlmbenchy"
tui_viewer := "-m rlmbenchy.visualizers.tui"
web_viewer := "-m rlmbenchy.visualizers.web"

# List available recipes.
default:
  @just --list

# Run the rlmbenchy web visualizer.
# Extra args can override the default host, for example:
#   just web --host 0.0.0.0 --port 8030
web *args:
  uv run python {{web_viewer}} --host {{default_web_host}} {{args}}

# Run the rlmbenchy TUI visualizer.
tui *args:
  uv run python {{tui_viewer}} {{args}}

# Run ty against the current phase-1 typed surface.
ty *args:
  uv run ty check {{args}}

# Run Ruff lint checks against the main package.
ruff *args:
  uv run ruff check rlmbenchy {{args}}

# Apply Ruff formatting to the main package.
ruff-format *args:
  uv run ruff format rlmbenchy {{args}}

# Build and smoke-test the installed wheel outside the checkout.
package-check:
  ./scripts/check-wheel.sh

# List all available DataHub workloads.
workloads *args:
  uv run python {{rlmbenchy_cli}} workloads {{args}}

# List tasks in a workload. Pass --limit N to cap output.
# Example:
#   just tasks tasks_v0
#   just tasks check_contract --limit 5
tasks workload *args:
  uv run python {{rlmbenchy_cli}} workloads tasks {{workload}} {{args}}

# Show full details for a single task.
# Example:
#   just task tasks_v0 v0_reconcile_ledgers
task workload task_id *args:
  uv run python {{rlmbenchy_cli}} workloads task {{workload}} {{task_id}} {{args}}

# Run one benchmark task using a run profile filename from config/run_profiles/.
# Example:
#   just run-rlm-task smoke-transcripts-oss.toml transcripts_smoke_first_1
run-rlm-task profile task_id:
  uv run python {{rlmbenchy_cli}} run --config {{run_profiles_dir}}/{{profile}} --task-id {{task_id}}
