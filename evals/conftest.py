"""Shared pytest fixtures for the eval suite."""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import AsyncIterator

import aiosqlite
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Configure pytest-asyncio
import pytest_asyncio

# For pytest-asyncio 1.x, use the loop_scope fixture
# and ensure async fixtures are properly configured


@pytest.fixture(scope="session")
def event_loop():
    """Use a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture()
async def tmp_db(tmp_path: Path) -> AsyncIterator[aiosqlite.Connection]:
    """Create a temporary SQLite database with the agent schema.

    Yields an open connection; the database file is automatically
    cleaned up when the fixture goes out of scope.
    """
    db_path = tmp_path / "test_metadata.db"
    db = await aiosqlite.connect(str(db_path))
    db.row_factory = aiosqlite.Row

    # Mirror the schema from agent/db/models.py exactly
    from agent.db.models import ALL_TABLES

    for ddl in ALL_TABLES:
        await db.executescript(ddl)
    await db.commit()
    yield db
    await db.close()


@pytest_asyncio.fixture()
async def api_client() -> AsyncIterator[AsyncClient]:
    """Provide an httpx AsyncClient wired to the FastAPI app (no network)."""
    from agent.server import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# Note: The old extract_fn fixture that returned _extract_metadata_fields
# has been removed. Extraction is now handled by Claude via the capture_metadata tool.
# Tests should use capture_metadata_handler directly for tool handler testing.
