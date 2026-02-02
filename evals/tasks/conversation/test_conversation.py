"""Conversation test suite: LLM-graded chat quality tests.

Uses the Anthropic API to judge conversation transcripts against rubrics.
Requires ANTHROPIC_API_KEY environment variable.

Run:
    pytest evals/tasks/conversation/ -v -m llm
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from evals.graders.llm_judge import grade_conversation

CASES_PATH = Path(__file__).parent / "cases.yaml"

PASS_THRESHOLD = 3.5


def _load_cases() -> list[dict[str, Any]]:
    with open(CASES_PATH) as f:
        return yaml.safe_load(f)


_CASES = _load_cases()


def _case_id(case: dict[str, Any]) -> str:
    return case["id"]


@pytest.mark.llm
@pytest.mark.parametrize("case", _CASES, ids=_case_id)
def test_conversation_quality(case: dict[str, Any]) -> None:
    """Grade a conversation transcript against its rubric using an LLM judge."""
    transcript = case["transcript"]
    rubric = case["rubric"]

    result = grade_conversation(
        transcript=transcript,
        rubric=rubric,
        pass_threshold=PASS_THRESHOLD,
    )

    # Report scores for visibility
    for dim, score in result["scores"].items():
        reasoning = result["reasoning"].get(dim, "")
        print(f"  {dim}: {score}/5 — {reasoning}")

    assert result["passed"], (
        f"Conversation eval failed with avg score {result['avg_score']:.2f} "
        f"(threshold {PASS_THRESHOLD}). Scores: {result['scores']}"
    )
