"""rlmbenchy app package."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rlmbenchy import _litellm_bootstrap as _litellm_bootstrap

if TYPE_CHECKING:
    from rlmbenchy.logger import RLMLogger, VerbosePrinter
    from rlmbenchy.rlm import RLM

__all__ = ["RLM", "RLMLogger", "VerbosePrinter", "main"]


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
