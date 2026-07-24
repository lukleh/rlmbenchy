# Repo Layout and Packaging

The repository uses a flat package layout: `rlmbenchy/` is at the repository
root rather than below `src/`. The built distribution is nevertheless
self-contained and does not depend on files elsewhere in the checkout.

## Distribution boundary

The wheel contains:

- the `rlmbenchy` package and console script;
- builtin workloads under `rlmbenchy.datahub`;
- bundled task manifests;
- bundled LM profiles under `rlmbenchy.resources`;
- static assets for the web log viewer.

Runtime assets are loaded with `importlib.resources`. Run profiles under
`config/run_profiles/`, development documentation, tests, and helper scripts
are not installed by the wheel. Tests may still be included in the source
archive so downstream packagers can validate it.

User overrides and generated state are resolved through the platform runtime
directories printed by `rlmbenchy paths`; they are never written into the
installed package.

## Verification

Run the same installed-distribution check used by CI:

```bash
./scripts/check-wheel.sh
```

The check builds both distribution formats, validates their metadata, installs
the wheel into a clean Python 3.12 environment, changes to an empty working
directory, and exercises the CLI plus every bundled resource class. This
guards against accidentally relying on the source checkout.

Before publishing a release:

1. Set a new, unique version in `pyproject.toml`.
2. Run the normal test, lint, type, web, and installed-wheel checks.
3. Inspect the generated artifacts under `dist/`.
4. Upload to TestPyPI and smoke-test that installation.
5. Publish the exact same artifacts to PyPI.

The ChatGPT subscription-backed transport is an experimental compatibility
feature, not a stable OpenAI Platform API. It directly calls the Codex
Responses backend and reads an existing file-backed Codex access token without
refreshing it or modifying the Codex credential file. Release notes and public
documentation must preserve that experimental label and direct users to run
`codex login -c cli_auth_credentials_store=file` when the cached token is
missing or expired. File-backed authentication stores sensitive tokens in
plaintext, so documentation must also tell users to protect `auth.json` like a
password.

## References

- PyPA: <https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/>
- setuptools discovery: <https://setuptools.pypa.io/en/latest/userguide/package_discovery.html>
