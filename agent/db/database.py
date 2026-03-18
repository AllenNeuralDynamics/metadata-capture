"""Async database setup for the metadata capture system.

Automatically selects PostgreSQL (via asyncpg) when DATABASE_URL is set,
otherwise falls back to SQLite (via aiosqlite) for local development.
"""

from __future__ import annotations

import logging
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _sqlite_to_pg(sql: str) -> str:
    """Convert ``?`` placeholders to ``$1, $2, ...`` for PostgreSQL."""
    counter = 0

    def _replacer(match: re.Match) -> str:
        nonlocal counter
        counter += 1
        return f"${counter}"

    return re.sub(r"\?", _replacer, sql)


_TABLE_NAME_RE = re.compile(
    r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)", re.IGNORECASE
)
_COLUMN_RE = re.compile(r"^\s+(\w+)\s+", re.MULTILINE)
_SKIP_KEYWORDS = frozenset({
    "CHECK", "CONSTRAINT", "UNIQUE", "PRIMARY", "FOREIGN", "REFERENCES",
})


def _parse_ddl(ddl: str) -> tuple[str, set[str]]:
    """Extract table name and column names from a CREATE TABLE DDL."""
    m = _TABLE_NAME_RE.search(ddl)
    if not m:
        raise ValueError(f"Cannot parse table name from DDL: {ddl[:80]}")
    table = m.group(1)

    body_start = ddl.index("(", m.end()) + 1
    body_end = ddl.rindex(")")
    body = ddl[body_start:body_end]

    columns: set[str] = set()
    for line_match in _COLUMN_RE.finditer(body):
        word = line_match.group(1).upper()
        if word not in _SKIP_KEYWORDS:
            columns.add(line_match.group(1).lower())
    return table, columns


class Database(ABC):
    """Unified async database interface."""

    @abstractmethod
    async def execute(self, sql: str, params: tuple | list = ()) -> str:
        """Execute a statement. Returns a status string (e.g. 'DELETE 1')."""

    @abstractmethod
    async def fetch(self, sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
        """Execute a query and return all rows as dicts."""

    @abstractmethod
    async def fetchrow(self, sql: str, params: tuple | list = ()) -> dict[str, Any] | None:
        """Execute a query and return a single row as a dict, or None."""

    @abstractmethod
    async def close(self) -> None:
        """Close the database connection / pool."""

    @abstractmethod
    async def init_tables(self) -> None:
        """Create tables and indexes, run backend-specific migrations."""


class PostgresDatabase(Database):
    """PostgreSQL backend using asyncpg."""

    def __init__(self) -> None:
        self._pool = None

    async def _get_pool(self):
        if self._pool is None:
            import asyncpg
            database_url = os.environ["DATABASE_URL"]
            self._pool = await asyncpg.create_pool(database_url, min_size=2, max_size=10)
            logger.info("PostgreSQL connection pool created")
        return self._pool

    async def execute(self, sql: str, params: tuple | list = ()) -> str:
        pool = await self._get_pool()
        result = await pool.execute(_sqlite_to_pg(sql), *params)
        return result or ""

    async def fetch(self, sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
        pool = await self._get_pool()
        rows = await pool.fetch(_sqlite_to_pg(sql), *params)
        return [dict(r) for r in rows]

    async def fetchrow(self, sql: str, params: tuple | list = ()) -> dict[str, Any] | None:
        pool = await self._get_pool()
        row = await pool.fetchrow(_sqlite_to_pg(sql), *params)
        return dict(row) if row else None

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("PostgreSQL connection pool closed")

    async def init_tables(self) -> None:
        from .models import PG_TABLES, CREATE_INDEXES
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            for ddl in PG_TABLES:
                await conn.execute(ddl)
                table, expected_cols = _parse_ddl(ddl)
                rows = await conn.fetch(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = $1", table
                )
                actual_cols = {r["column_name"] for r in rows}
                missing = expected_cols - actual_cols
                if missing:
                    logger.warning(
                        "Schema drift in %s: missing columns %s — dropping and rebuilding",
                        table, missing,
                    )
                    await conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
                    await conn.execute(ddl)
            for idx in CREATE_INDEXES:
                await conn.execute(idx)


class SQLiteDatabase(Database):
    """SQLite backend using aiosqlite."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._conn = None

    async def _get_conn(self):
        if self._conn is None:
            import aiosqlite
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA foreign_keys=ON")
            logger.info("SQLite connection opened: %s", self._db_path)
        return self._conn

    async def execute(self, sql: str, params: tuple | list = ()) -> str:
        conn = await self._get_conn()
        cursor = await conn.execute(sql, tuple(params))
        await conn.commit()
        return f"OK {cursor.rowcount}"

    async def fetch(self, sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
        conn = await self._get_conn()
        cursor = await conn.execute(sql, tuple(params))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def fetchrow(self, sql: str, params: tuple | list = ()) -> dict[str, Any] | None:
        conn = await self._get_conn()
        cursor = await conn.execute(sql, tuple(params))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            logger.info("SQLite connection closed")

    async def init_tables(self) -> None:
        from .models import SQLITE_TABLES, CREATE_INDEXES
        conn = await self._get_conn()
        for ddl in SQLITE_TABLES:
            await conn.executescript(ddl)
            table, expected_cols = _parse_ddl(ddl)
            cursor = await conn.execute(f"PRAGMA table_info({table})")
            actual_cols = {row[1] for row in await cursor.fetchall()}
            missing = expected_cols - actual_cols
            if missing:
                logger.warning(
                    "Schema drift in %s: missing columns %s — dropping and rebuilding",
                    table, missing,
                )
                await conn.execute(f"DROP TABLE IF EXISTS {table}")
                await conn.executescript(ddl)
        for idx in CREATE_INDEXES:
            await conn.execute(idx)
        await conn.commit()


_db: Database | None = None


def _create_backend() -> Database:
    """Select the right backend based on environment."""
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        logger.info("Using PostgreSQL backend (DATABASE_URL is set)")
        return PostgresDatabase()
    else:
        db_dir = Path(os.environ.get("METADATA_DB_DIR", Path(__file__).resolve().parent.parent))
        db_path = db_dir / "metadata.db"
        logger.info("Using SQLite backend: %s", db_path)
        return SQLiteDatabase(db_path)


async def get_db() -> Database:
    """Return the shared database instance, creating it if needed."""
    global _db
    if _db is None:
        _db = _create_backend()
    return _db


async def init_db() -> None:
    """Initialize the database tables and indexes."""
    db = await get_db()
    await db.init_tables()
    logger.info("Database tables initialized")


async def close_db() -> None:
    """Close the database connection."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None
