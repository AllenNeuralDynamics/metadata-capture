"""LLM-as-judge grader using the Anthropic Claude API."""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"


def grade_conversation(
    transcript: str,
    rubric: dict[str, str],
    *,
    pass_threshold: float = 3.5,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Score a conversation transcript against a rubric using Claude.

    Parameters
    ----------
    transcript : str
        The full conversation text to evaluate.
    rubric : dict[str, str]
        Mapping of dimension name to description, e.g.
        {"accuracy": "Did the agent extract correct metadata?",
         "completeness": "Were all required fields captured?"}
    pass_threshold : float
        Minimum average score (1-5) to pass. Default 3.5.
    model : str
        Anthropic model ID.

    Returns
    -------
    dict with keys:
        passed : bool
        avg_score : float
        scores : dict[str, float]   (dimension -> score)
        reasoning : dict[str, str]  (dimension -> explanation)
    """
    dimensions_text = "\n".join(
        f"- **{dim}**: {desc}" for dim, desc in rubric.items()
    )
    prompt = (
        "You are an expert evaluator for a metadata-capture AI agent. "
        "Score the following transcript on each dimension from 1 (terrible) to 5 (excellent).\n\n"
        f"## Dimensions\n{dimensions_text}\n\n"
        f"## Transcript\n{transcript}\n\n"
        "Respond with ONLY a JSON object (no markdown fences) with this structure:\n"
        '{"scores": {"dimension_name": <number 1-5>, ...}, '
        '"reasoning": {"dimension_name": "<brief explanation>", ...}}'
    )

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        logger.error("LLM judge returned invalid JSON: %s", text)
        return {
            "passed": False,
            "avg_score": 0.0,
            "scores": {},
            "reasoning": {"error": text},
        }

    scores: dict[str, float] = {
        k: float(v) for k, v in parsed.get("scores", {}).items()
    }
    reasoning: dict[str, str] = parsed.get("reasoning", {})
    avg_score = sum(scores.values()) / len(scores) if scores else 0.0

    return {
        "passed": avg_score >= pass_threshold,
        "avg_score": round(avg_score, 2),
        "scores": scores,
        "reasoning": reasoning,
    }
