from __future__ import annotations

from rlmbenchy.datahub.scoring import score_answer


def test_score_answer_one_of_accepts_options_alias() -> None:
    score, ok, detail = score_answer(
        "Yes",
        {"kind": "one_of", "options": ["yes", "maybe"]},
    )

    assert score == 100.0
    assert ok is True
    assert "yes" in detail
