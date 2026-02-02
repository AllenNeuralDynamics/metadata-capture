"""Agent extraction accuracy tests.

Tests that the agent correctly extracts metadata from scientist input
and saves it to SQLite via the capture_metadata tool.

These tests require ANTHROPIC_API_KEY and make real API calls.
Run with: pytest evals/tasks/extraction/test_agent_extraction.py -v -m llm
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
import yaml

from agent.service import chat
from agent.tools.metadata_store import get_draft_metadata
from agent.db.database import init_db, close_db


CASES_PATH = Path(__file__).parent / "cases.yaml"


def _load_cases() -> list[dict[str, Any]]:
    with open(CASES_PATH) as f:
        return yaml.safe_load(f)


_CASES = _load_cases()


def _run_async(coro):
    """Run an async function synchronously for testing."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        return asyncio.run(coro)
    return loop.run_until_complete(coro)


async def _consume_chat(session_id: str, user_input: str) -> None:
    """Run the agent and consume all output."""
    async for _ in chat(session_id, user_input):
        pass


def _assert_fields_match(actual: Any, expected: Any, path: str) -> None:
    """Recursively check that actual contains all expected fields."""
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: expected dict, got {type(actual)}"
        for key, value in expected.items():
            assert key in actual, f"{path}.{key}: field missing"
            _assert_fields_match(actual[key], value, f"{path}.{key}")
    elif isinstance(expected, list):
        assert isinstance(actual, list), f"{path}: expected list, got {type(actual)}"
        assert len(actual) >= len(expected), f"{path}: expected at least {len(expected)} items"
        for i, item in enumerate(expected):
            _assert_fields_match(actual[i], item, f"{path}[{i}]")
    else:
        assert actual == expected, f"{path}: expected {expected}, got {actual}"


@pytest.fixture(autouse=True)
def setup_and_teardown_db():
    """Initialize and teardown database for each test."""
    _run_async(init_db())
    yield
    _run_async(close_db())


@pytest.mark.llm
@pytest.mark.parametrize(
    "case",
    [c for c in _CASES if c.get("expected") and c["expected"] != {}],
    ids=[c["id"] for c in _CASES if c.get("expected") and c["expected"] != {}],
)
def test_agent_extracts_metadata(case: dict[str, Any]) -> None:
    """Test that agent correctly extracts metadata from scientist input."""
    session_id = f"test-{case['id']}"
    user_input = case["input"]
    expected = case["expected"]

    # Run the agent
    _run_async(_consume_chat(session_id, user_input))

    # Check SQLite for expected fields
    draft = _run_async(get_draft_metadata(session_id))

    if not expected:
        # For cases with empty expected, just verify no crash
        return

    assert draft is not None, f"No draft found for session {session_id}"

    # Check each expected top-level field
    for key, expected_value in expected.items():
        json_key = f"{key}_json"
        saved_value = draft.get(json_key)
        assert saved_value is not None, f"Field {key} not saved (input: {user_input!r})"
        _assert_fields_match(saved_value, expected_value, key)


@pytest.mark.llm
@pytest.mark.parametrize(
    "case",
    [c for c in _CASES if c.get("absent_keys")],
    ids=[c["id"] for c in _CASES if c.get("absent_keys")],
)
def test_agent_does_not_extract_absent_keys(case: dict[str, Any]) -> None:
    """Test that agent does NOT extract certain fields (guards against false positives)."""
    session_id = f"test-absent-{case['id']}"
    user_input = case["input"]
    absent_keys = case["absent_keys"]

    # Run the agent
    _run_async(_consume_chat(session_id, user_input))

    # Check SQLite
    draft = _run_async(get_draft_metadata(session_id))

    if draft is None:
        # No draft means nothing was extracted, which is correct
        return

    for key in absent_keys:
        json_key = f"{key}_json"
        saved_value = draft.get(json_key)
        assert saved_value is None or saved_value == {}, \
            f"Field {key} should NOT be extracted from: {user_input!r}"
