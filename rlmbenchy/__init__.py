"""rlmbenchy app package."""

from __future__ import annotations

from rlmbenchy import _litellm_bootstrap as _litellm_bootstrap  # noqa: F401

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rlmbenchy.rlm import RLM
    from rlmbenchy.logger import RLMLogger, VerbosePrinter

__all__ = ["main", "RLM", "RLMLogger", "VerbosePrinter"]


def __getattr__(name: str) -> Any:
    if name == "RLM":
        from rlmbenchy.rlm import RLM as exported

        return exported
    if name in {"RLMLogger", "VerbosePrinter"}:
        from rlmbenchy.logger import RLMLogger, VerbosePrinter

        return {"RLMLogger": RLMLogger, "VerbosePrinter": VerbosePrinter}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def main(argv: list[str] | None = None) -> None:
    from rlmbenchy.cli import main as _main

    _main(argv)
