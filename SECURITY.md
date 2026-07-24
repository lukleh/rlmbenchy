# Security Policy

## Supported version

Security updates are applied to the latest revision of `main`. This project is
experimental and does not currently maintain older release branches.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for this repository. Do
not include credentials, sensitive prompts, private datasets, or complete run
logs in a public issue. If private reporting is unavailable, open a public
issue containing only enough non-sensitive information to request a private
contact channel.

## Security model

- `LocalProcessReplRuntime` executes model-generated Python with the current
  user's permissions. It is intended only for trusted models and inputs.
- Runtime JSONL logs intentionally preserve detailed inputs, configuration,
  generated code, and provider responses for reproducibility.
- The web log viewer is unauthenticated and is intended to remain bound to
  `127.0.0.1` unless protected by external access controls.
- Remote datasets and model providers have their own security and data-handling
  terms.

## Known dependency advisory

DSPy 3.2.1 depends on `diskcache` 5.6.3, which is affected by
[`PYSEC-2026-2447`](https://github.com/pypa/advisory-database/blob/main/vulns/diskcache/PYSEC-2026-2447.yaml).
The advisory concerns unsafe deserialization when an attacker can write to a
cache directory that a victim later reads. No fixed `diskcache` release was
listed when this repository was audited on 2026-07-15.

Until the dependency path provides a fix, keep Python and DSPy cache directories
writable only by the current trusted user. Do not reuse cache directories from
untrusted users, archives, containers, or CI artifacts. CI ignores this one
advisory explicitly so that any additional vulnerability still fails the audit.
