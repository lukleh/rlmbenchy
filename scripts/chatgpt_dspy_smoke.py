from __future__ import annotations

import argparse
import sys

import dspy

from rlmbenchy.core.dspy.lm import build_lm
from rlmbenchy.core.dspy.runtime import build_dspy_settings_adapter


class ReplyWithToken(dspy.Signature):
    """Reply with the requested token and nothing else."""

    request: str = dspy.InputField(
        desc="Instruction telling the model what exact token to return."
    )
    answer: str = dspy.OutputField(desc="Exact token requested by the user.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Minimal DSPy smoke test for the ChatGPT subscription runtime."
    )
    parser.add_argument(
        "--api-base",
        default="https://chatgpt.com/backend-api/codex",
        help="ChatGPT subscription API base to use.",
    )
    parser.add_argument(
        "--model",
        default="chatgpt/gpt-5.4",
        help="Model id to use.",
    )
    parser.add_argument(
        "--request",
        default="Return exactly OK and nothing else.",
        help="User request for the DSPy predictor.",
    )
    parser.add_argument(
        "--reasoning-effort",
        default="low",
        help="Reasoning effort passed to the responses transport.",
    )
    parser.add_argument(
        "--verbosity",
        default="low",
        help="Text verbosity passed to the responses transport.",
    )
    parser.add_argument(
        "--show-history",
        action="store_true",
        help="Print the last DSPy history entry after the call.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    lm = build_lm(
        api_base=args.api_base,
        model=args.model,
        api_key="",
        request_kwargs={
            "reasoning": {"effort": args.reasoning_effort},
            "text": {"verbosity": args.verbosity},
        },
    )

    dspy.settings.configure(
        lm=lm,
        adapter=build_dspy_settings_adapter("chat"),
    )

    predictor = dspy.Predict(ReplyWithToken)

    try:
        result = predictor(request=args.request)
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print("DSPY predictor completed.")
    print(f"answer={result.answer!r}")

    if args.show_history:
        print("history=")
        print(dspy.inspect_history(n=1))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
