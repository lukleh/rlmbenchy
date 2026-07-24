"""Pytest-wide bootstrap.

Pins LiteLLM to its bundled model-cost map so test behavior depends on the
installed wheel, not on whatever
``BerriAI/litellm:main/model_prices_and_context_window.json`` happens to
serve right now. See ``rlmbenchy/_litellm_bootstrap.py`` for the rationale.

Must execute before any ``import litellm`` or ``import dspy``; pytest loads
repo-root ``conftest.py`` before test modules, so this is the right hook.
"""

from __future__ import annotations

from rlmbenchy import _litellm_bootstrap as _litellm_bootstrap  # noqa: F401
