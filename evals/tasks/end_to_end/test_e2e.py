"""End-to-end test suite: full API pipeline tests.

Tests the FastAPI server endpoints using httpx.AsyncClient with ASGI
transport (no network needed). Uses a temporary database to avoid
polluting the real one.

Run:
    pytest evals/tasks/end_to_end/ -v -m "not llm"
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

CASES_PATH = Path(__file__).parent / "cases.yaml"


def _load_cases() -> list[dict[str, Any]]:
    with open(CASES_PATH) as f:
        return yaml.safe_load(f)


_CASES = _load_cases()


def _case_id(case: dict[str, Any]) -> str:
    return case["id"]


@pytest.fixture()
def e2e_client(tmp_path: Path):
    """Create an AsyncClient with a temporary database."""
    import asyncio

    async def _make_client():
        # Point the database at a temp directory
        os.environ["METADATA_DB_DIR"] = str(tmp_path)

        import agent.db.database as db_mod

        db_mod._db_connection = None
        db_mod.DB_DIR = tmp_path
        db_mod.DB_PATH = tmp_path / "metadata.db"

        # Initialize the DB tables (lifespan doesn't run with ASGI transport)
        from agent.db.database import init_db
        await init_db()

        from agent.server import app

        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://testserver")

    loop = asyncio.new_event_loop()
    client = loop.run_until_complete(_make_client())
    client._test_loop = loop  # type: ignore[attr-defined]
    yield client

    async def _cleanup():
        await client.aclose()
        from agent.db.database import close_db
        await close_db()

    loop.run_until_complete(_cleanup())


@pytest.mark.parametrize("case", _CASES, ids=_case_id)
def test_api_endpoint(e2e_client: AsyncClient, case: dict[str, Any]) -> None:
    """Test an API endpoint against expected status and body."""

    async def _run():
        method = case["method"].upper()
        path = case["path"]
        expected_status = case["expected_status"]

        if method == "GET":
            response = await e2e_client.get(path)
        elif method == "POST":
            response = await e2e_client.post(path)
        else:
            pytest.fail(f"Unsupported HTTP method: {method}")

        assert response.status_code == expected_status, (
            f"Expected status {expected_status}, got {response.status_code}. "
            f"Body: {response.text}"
        )

        # Check expected_body (exact key/value matches)
        expected_body = case.get("expected_body")
        if expected_body:
            body = response.json()
            for key, value in expected_body.items():
                assert key in body, f"Missing key '{key}' in response body: {body}"
                assert body[key] == value, (
                    f"Expected body.{key}={value!r}, got {body[key]!r}"
                )

        # Check expected_body_type
        expected_type = case.get("expected_body_type")
        if expected_type == "list":
            body = response.json()
            assert isinstance(body, list), (
                f"Expected response body to be a list, got {type(body).__name__}"
            )

    e2e_client._test_loop.run_until_complete(_run())  # type: ignore[attr-defined]
