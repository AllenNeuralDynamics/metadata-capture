"""Tools for persisting and retrieving draft metadata in SQLite."""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from ..db.database import get_db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Metadata field names that map to JSON columns
# ---------------------------------------------------------------------------
METADATA_FIELDS = (
    "subject_json",
    "procedures_json",
    "data_description_json",
    "instrument_json",
    "acquisition_json",
    "session_json",
    "processing_json",
    "quality_control_json",
    "rig_json",
)


def _row_to_dict(row) -> dict[str, Any]:
    """Convert an aiosqlite Row to a plain dict, parsing JSON columns."""
    d = dict(row)
    for field in METADATA_FIELDS:
        if d.get(field):
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                pass
    if d.get("validation_results_json"):
        try:
            d["validation_results_json"] = json.loads(d["validation_results_json"])
        except (json.JSONDecodeError, TypeError):
            pass
    return d


async def save_draft_metadata(session_id: str, metadata_json: dict[str, Any]) -> dict[str, Any]:
    """Save a new draft metadata entry for the given session.

    Parameters
    ----------
    session_id : str
        The session identifier.
    metadata_json : dict
        A dict whose keys are top-level metadata fields (e.g. "subject",
        "procedures", "data_description") and values are the JSON-serialisable
        data for that field.

    Returns
    -------
    dict
        The saved draft row as a dict including its generated id.
    """
    db = await get_db()
    draft_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    columns = ["id", "session_id", "status", "created_at", "updated_at"]
    values: list[Any] = [draft_id, session_id, "draft", now, now]

    for field in METADATA_FIELDS:
        key = field.replace("_json", "")
        if key in metadata_json:
            raw = metadata_json[key]
            # Guard against double-serialization: if the value is already a
            # JSON string, store it directly instead of wrapping it again.
            if isinstance(raw, str):
                try:
                    json.loads(raw)  # validate it's proper JSON
                    serialized = raw
                except (json.JSONDecodeError, ValueError):
                    serialized = json.dumps(raw)
            else:
                serialized = json.dumps(raw)
            columns.append(field)
            values.append(serialized)

    placeholders = ", ".join("?" for _ in values)
    col_names = ", ".join(columns)

    await db.execute(
        f"INSERT INTO draft_metadata ({col_names}) VALUES ({placeholders})",
        values,
    )
    await db.commit()

    return await get_draft_metadata(session_id)


async def get_draft_metadata(session_id: str) -> dict[str, Any] | None:
    """Retrieve the most recent draft metadata for a session.

    Parameters
    ----------
    session_id : str
        The session identifier.

    Returns
    -------
    dict or None
        The draft metadata row or None if not found.
    """
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM draft_metadata WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
        (session_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


async def update_draft_metadata(session_id: str, field: str, value: Any) -> dict[str, Any] | None:
    """Update a specific metadata field for the latest draft in a session.

    Parameters
    ----------
    session_id : str
        The session identifier.
    field : str
        The metadata field name (e.g. "subject", "procedures"). The "_json"
        suffix is added automatically if missing.
    value : Any
        The new value (will be JSON-serialised).

    Returns
    -------
    dict or None
        The updated row, or None if no draft exists for this session.
    """
    col = field if field.endswith("_json") else f"{field}_json"
    if col not in METADATA_FIELDS and col != "validation_results_json":
        return {"error": f"Unknown metadata field: {field}"}

    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()

    # Find the latest draft for this session
    cursor = await db.execute(
        "SELECT id FROM draft_metadata WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
        (session_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None

    # Guard against double-serialization
    if isinstance(value, str):
        try:
            json.loads(value)
            serialized = value
        except (json.JSONDecodeError, ValueError):
            serialized = json.dumps(value)
    else:
        serialized = json.dumps(value)

    await db.execute(
        f"UPDATE draft_metadata SET {col} = ?, updated_at = ? WHERE id = ?",
        (serialized, now, row["id"]),
    )
    await db.commit()
    return await get_draft_metadata(session_id)


async def list_all_drafts(status_filter: str | None = None) -> list[dict[str, Any]]:
    """List all draft metadata entries, optionally filtered by status.

    Parameters
    ----------
    status_filter : str, optional
        Filter by status: "draft", "validated", "confirmed", "error".

    Returns
    -------
    list[dict]
        List of draft metadata rows.
    """
    db = await get_db()
    if status_filter:
        cursor = await db.execute(
            "SELECT * FROM draft_metadata WHERE status = ? ORDER BY created_at DESC",
            (status_filter,),
        )
    else:
        cursor = await db.execute(
            "SELECT * FROM draft_metadata ORDER BY created_at DESC"
        )
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


async def confirm_metadata(session_id: str) -> dict[str, Any] | None:
    """Mark the latest draft for a session as confirmed.

    Parameters
    ----------
    session_id : str
        The session identifier.

    Returns
    -------
    dict or None
        The updated row, or None if no draft exists.
    """
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()

    cursor = await db.execute(
        "SELECT id FROM draft_metadata WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
        (session_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None

    await db.execute(
        "UPDATE draft_metadata SET status = 'confirmed', updated_at = ? WHERE id = ?",
        (now, row["id"]),
    )
    await db.commit()
    return await get_draft_metadata(session_id)


async def delete_session(session_id: str) -> bool:
    """Delete all data for a session (conversations and draft metadata).

    Returns True if anything was deleted, False otherwise.
    """
    db = await get_db()
    c1 = await db.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
    c2 = await db.execute("DELETE FROM draft_metadata WHERE session_id = ?", (session_id,))
    await db.commit()
    return (c1.rowcount or 0) + (c2.rowcount or 0) > 0


# ---------------------------------------------------------------------------
# Conversation history helpers
# ---------------------------------------------------------------------------

async def save_conversation_turn(session_id: str, role: str, content: str) -> None:
    """Persist a single conversation turn."""
    db = await get_db()
    await db.execute(
        "INSERT INTO conversations (session_id, role, content) VALUES (?, ?, ?)",
        (session_id, role, content),
    )
    await db.commit()


async def get_conversation_history(session_id: str) -> list[dict[str, Any]]:
    """Retrieve full conversation history for a session."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT role, content, created_at FROM conversations WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]
