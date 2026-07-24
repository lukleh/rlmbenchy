#!/usr/bin/env bash
set -euo pipefail

release_tmp="$(mktemp -d "${TMPDIR:-/tmp}/rlmbenchy-wheel-check.XXXXXX")"
cleanup() {
  rm -rf -- "$release_tmp"
}
trap cleanup EXIT

dist_dir="$release_tmp/dist"
venv_dir="$release_tmp/venv"
smoke_dir="$release_tmp/smoke"
mkdir -p "$smoke_dir"

uv build --out-dir "$dist_dir"
uvx --from twine twine check "$dist_dir"/*

wheel_path="$(find "$dist_dir" -maxdepth 1 -type f -name '*.whl' -print -quit)"
if [[ -z "$wheel_path" ]]; then
  echo "No wheel was built." >&2
  exit 1
fi

uv venv --python 3.12 "$venv_dir"
uv pip install --python "$venv_dir/bin/python" "$wheel_path"

(
  cd "$smoke_dir"
  "$venv_dir/bin/rlmbenchy" paths --json >/dev/null
  "$venv_dir/bin/rlmbenchy" workloads list >/dev/null
  "$venv_dir/bin/rlmbenchy" workloads tasks check_adapter_matrix --limit 1 >/dev/null
  "$venv_dir/bin/rlmbenchy" workloads tasks check_contract --limit 1 >/dev/null
  "$venv_dir/bin/rlmbenchy" workloads tasks tasks_v0 --limit 1 >/dev/null
  "$venv_dir/bin/python" -m rlmbenchy.visualizers.web --help >/dev/null
  "$venv_dir/bin/python" - <<'PY'
from rlmbenchy.datahub.workloads.check_adapter_matrix.source import (
    DEFAULT_TASKS_PATH as adapter_tasks,
)
from rlmbenchy.datahub.workloads.check_contract.source import (
    DEFAULT_TASKS_PATH as contract_tasks,
)
from rlmbenchy.datahub.workloads.tasks_v0.source import (
    DEFAULT_TASKS_PATH as v0_tasks,
)
from rlmbenchy.runtime_config import BUNDLED_LM_PROFILES_DIR
from rlmbenchy.visualizers.web.server import DEFAULT_STATIC_DIR

assert adapter_tasks.is_file()
assert contract_tasks.is_file()
assert v0_tasks.is_file()
assert len(list(BUNDLED_LM_PROFILES_DIR.glob("*.toml"))) >= 1
assert (BUNDLED_LM_PROFILES_DIR / "README.md").is_file()
assert (DEFAULT_STATIC_DIR / "index.html").is_file()
assert (DEFAULT_STATIC_DIR / "styles.css").is_file()
PY
)

echo "Installed wheel smoke test passed."
