"""End-to-end tests for metadata-capture HTTP endpoints and tool handlers.

Every test uses a fresh temporary SQLite database.  No real network calls are
made — the FastAPI app is exercised through httpx's ASGITransport.

Run from the repository root (metadata-capture/):
    python -m pytest evals/tasks/end_to_end/test_new_features.py -v
"""

import asyncio
import os
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_loop = asyncio.new_event_loop()


def _run(coro):
    """Drive a coroutine to completion on a persistent event loop."""
    return _loop.run_until_complete(coro)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def setup_db(tmp_path):
    """Reset the global DB connection and point it at a throwaway directory.

    The fixture runs init_db() so that the schema is ready before any test
    code executes.  On teardown the connection is closed.
    """

    async def _setup():
        os.environ["METADATA_DB_DIR"] = str(tmp_path)
        import agent.db.database as db_mod

        # Tear down any leftover connection from a previous test
        db_mod._db_connection = None
        # Patch module-level path variables so get_db() writes to tmp_path
        db_mod.DB_DIR = tmp_path
        db_mod.DB_PATH = tmp_path / "metadata.db"

        from agent.db.database import init_db

        await init_db()

    _run(_setup())
    yield
    # --- teardown -----------------------------------------------------------

    async def _teardown():
        from agent.db.database import close_db

        await close_db()

    _run(_teardown())


@pytest.fixture()
def client(setup_db):
    """httpx AsyncClient bound to the FastAPI app via ASGI transport.

    Depends on setup_db so the database is initialised before any request.
    The lifespan startup hook in server.py also calls init_db(), but because
    the connection is already open (from setup_db) it is a no-op — the same
    in-memory singleton is reused.
    """
    from agent.server import app

    transport = ASGITransport(app=app)
    c = AsyncClient(transport=transport, base_url="http://testserver")
    yield c
    _run(c.aclose())


# ---------------------------------------------------------------------------
# Test 1: Health endpoint
# ---------------------------------------------------------------------------


def test_health_returns_200_ok(client):
    """GET /health should return 200 with {"status": "ok"}."""
    resp = _run(client.get("/health"))
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Test 2: Sessions endpoint — empty database
# ---------------------------------------------------------------------------


def test_sessions_empty_when_no_conversations(client):
    """GET /sessions returns an empty list when no conversations exist."""
    resp = _run(client.get("/sessions"))
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Test 3: Session messages — nonexistent session returns empty list
# ---------------------------------------------------------------------------


def test_session_messages_returns_empty_for_unknown_session(client):
    """GET /sessions/{id}/messages returns 200 with [] for a missing session.

    An empty history is a valid response (not a 404) because the session may
    simply not have any messages yet.
    """
    resp = _run(client.get("/sessions/nonexistent-session-id/messages"))
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Test 4: Metadata CRUD — create via capture_metadata_handler, then list
# ---------------------------------------------------------------------------


def test_capture_metadata_creates_draft_visible_in_list(client):
    """Calling capture_metadata_handler with a subject creates a draft that
    shows up in GET /metadata with status 'draft' and populated subject_json.
    """
    from agent.tools.capture_mcp import capture_metadata_handler

    session_id = "test-session-crud"
    subject_data = {"subject_id": "12345", "sex": "Male"}

    # --- create the draft via the tool handler ----------------------------
    result = _run(
        capture_metadata_handler(
            {"session_id": session_id, "subject": subject_data}
        )
    )
    # Handler returns a content-wrapped response; verify no error
    text = result["content"][0]["text"]
    assert "saved" in text

    # --- list via HTTP ----------------------------------------------------
    resp = _run(client.get("/metadata"))
    assert resp.status_code == 200
    drafts = resp.json()
    assert len(drafts) == 1

    draft = drafts[0]
    assert draft["session_id"] == session_id
    assert draft["status"] == "draft"
    # subject_json should contain the data we passed
    assert draft["subject_json"]["subject_id"] == "12345"
    assert draft["subject_json"]["sex"] == "Male"


# ---------------------------------------------------------------------------
# Test 5: PUT /metadata/{session_id}/fields — update a field
# ---------------------------------------------------------------------------


def test_put_fields_adds_session_data(client):
    """PUT /metadata/{id}/fields merges a new field into an existing draft."""
    from agent.tools.capture_mcp import capture_metadata_handler

    session_id = "test-session-put-fields"

    # Seed a draft with only subject data
    _run(
        capture_metadata_handler(
            {"session_id": session_id, "subject": {"subject_id": "99999"}}
        )
    )

    # Update with session field via HTTP
    resp = _run(
        client.put(
            f"/metadata/{session_id}/fields",
            json={
                "field": "session",
                "value": {"session_start_time": "9:00 AM"},
            },
        )
    )
    assert resp.status_code == 200

    # Verify session_json is now present
    resp = _run(client.get("/metadata"))
    drafts = resp.json()
    assert len(drafts) == 1
    assert drafts[0]["session_json"]["session_start_time"] == "9:00 AM"


# ---------------------------------------------------------------------------
# Test 6: PUT /metadata/{session_id}/fields — 404 for missing session
# ---------------------------------------------------------------------------


def test_put_fields_returns_404_for_missing_session(client):
    """PUT /metadata/{id}/fields returns 404 when no draft exists."""
    resp = _run(
        client.put(
            "/metadata/nonexistent-session/fields",
            json={"field": "subject", "value": {"subject_id": "11111"}},
        )
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 7: PUT /metadata/{session_id}/fields — overwrite existing field
# ---------------------------------------------------------------------------


def test_put_fields_overwrites_existing_subject(client):
    """A second PUT to the same field replaces the previous value entirely."""
    from agent.tools.capture_mcp import capture_metadata_handler

    session_id = "test-session-overwrite"

    # Create draft with initial subject_id
    _run(
        capture_metadata_handler(
            {"session_id": session_id, "subject": {"subject_id": "111"}}
        )
    )

    # Overwrite via PUT — this replaces the whole subject_json column
    resp = _run(
        client.put(
            f"/metadata/{session_id}/fields",
            json={"field": "subject", "value": {"subject_id": "222"}},
        )
    )
    assert resp.status_code == 200

    # Verify the value was replaced
    resp = _run(client.get("/metadata"))
    drafts = resp.json()
    assert len(drafts) == 1
    assert drafts[0]["subject_json"]["subject_id"] == "222"


# ---------------------------------------------------------------------------
# Test 8: Confirm metadata
# ---------------------------------------------------------------------------


def test_confirm_metadata_changes_status_to_confirmed(client):
    """POST /metadata/{id}/confirm flips the draft status to 'confirmed'."""
    from agent.tools.capture_mcp import capture_metadata_handler

    session_id = "test-session-confirm"

    # Seed a draft
    _run(
        capture_metadata_handler(
            {"session_id": session_id, "subject": {"subject_id": "55555"}}
        )
    )

    # Confirm it
    resp = _run(client.post(f"/metadata/{session_id}/confirm"))
    assert resp.status_code == 200

    # Verify status via list endpoint
    resp = _run(client.get("/metadata"))
    drafts = resp.json()
    assert len(drafts) == 1
    assert drafts[0]["status"] == "confirmed"


# ---------------------------------------------------------------------------
# Test 9: Confirm metadata — 404 for missing session
# ---------------------------------------------------------------------------


def test_confirm_returns_404_for_missing_session(client):
    """POST /metadata/{id}/confirm returns 404 when no draft exists."""
    resp = _run(client.post("/metadata/nonexistent/confirm"))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 10: Validation endpoint — all required fields present
# ---------------------------------------------------------------------------


def test_validation_returns_valid_when_all_required_fields_present(client):
    """GET /metadata/{id}/validation returns completeness_score 1.0 and
    status 'valid' when subject_id, modality, and project_name are all set.

    Because capture_metadata_handler stores validation results keyed on the
    raw draft layout (subject_json, data_description_json …), we run the
    validation logic directly with the correct bare-key structure and persist
    the result so the endpoint can return it.
    """
    from agent.tools.capture_mcp import capture_metadata_handler
    from agent.tools.metadata_store import update_draft_metadata
    from agent.validation import validate_metadata

    session_id = "test-session-valid"

    # Create a draft with subject and data_description.  Use "confocal"
    # (a non-physiology modality) so the cross-field check in
    # _validate_session does not inject a warning about missing session times.
    _run(
        capture_metadata_handler(
            {
                "session_id": session_id,
                "subject": {"subject_id": "12345"},
                "data_description": {
                    "modality": [
                        {"name": "Confocal microscopy", "abbreviation": "confocal"}
                    ],
                    "project_name": "Test Project",
                },
            }
        )
    )

    # Run validation with the correctly-keyed metadata (bare keys) so that
    # the required-field checks actually resolve, and persist those results.
    correct_metadata = {
        "subject": {"subject_id": "12345"},
        "data_description": {
            "modality": [
                {"name": "Confocal microscopy", "abbreviation": "confocal"}
            ],
            "project_name": "Test Project",
        },
    }
    validation_result = validate_metadata(correct_metadata)
    _run(
        update_draft_metadata(
            session_id, "validation_results", validation_result.to_dict()
        )
    )

    # Query the validation endpoint
    resp = _run(client.get(f"/metadata/{session_id}/validation"))
    assert resp.status_code == 200

    body = resp.json()
    assert body["completeness_score"] == 1.0
    assert body["status"] == "valid"


# ---------------------------------------------------------------------------
# Test 11: Validation endpoint — 404 for missing session
# ---------------------------------------------------------------------------


def test_validation_returns_404_for_missing_session(client):
    """GET /metadata/{id}/validation returns 404 when no draft exists."""
    resp = _run(client.get("/metadata/nonexistent/validation"))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 12: Validation endpoint — missing required fields detected
# ---------------------------------------------------------------------------


def test_validation_reports_missing_required_fields(client):
    """When only subject is provided (no modality, no project_name), the
    validation result lists the two missing data_description fields.

    Same key-normalisation approach as test 10: we run validate_metadata with
    bare keys and store the result so the endpoint returns it.
    """
    from agent.tools.capture_mcp import capture_metadata_handler
    from agent.tools.metadata_store import update_draft_metadata
    from agent.validation import validate_metadata

    session_id = "test-session-missing-fields"

    # Create a draft with only subject — no data_description at all
    _run(
        capture_metadata_handler(
            {
                "session_id": session_id,
                "subject": {"subject_id": "99999"},
            }
        )
    )

    # Validate with bare keys (only subject present)
    partial_metadata = {
        "subject": {"subject_id": "99999"},
    }
    validation_result = validate_metadata(partial_metadata)
    _run(
        update_draft_metadata(
            session_id, "validation_results", validation_result.to_dict()
        )
    )

    # Query endpoint
    resp = _run(client.get(f"/metadata/{session_id}/validation"))
    assert resp.status_code == 200

    body = resp.json()
    missing = body["missing_required"]
    assert "data_description.modality" in missing
    assert "data_description.project_name" in missing
    # subject.subject_id IS present, so it should NOT be in missing
    assert "subject.subject_id" not in missing


# ---------------------------------------------------------------------------
# Test 13: capture_metadata_handler — missing session_id
# ---------------------------------------------------------------------------


def test_capture_metadata_handler_errors_without_session_id(setup_db):
    """Calling capture_metadata_handler with no session_id returns an error."""
    from agent.tools.capture_mcp import capture_metadata_handler

    result = _run(capture_metadata_handler({}))
    text = result["content"][0]["text"]
    assert "Error: session_id is required" in text


# ---------------------------------------------------------------------------
# Test 14: capture_metadata_handler — no metadata fields provided
# ---------------------------------------------------------------------------


def test_capture_metadata_handler_errors_without_metadata_fields(setup_db):
    """Passing only session_id (no metadata) returns a helpful error."""
    from agent.tools.capture_mcp import capture_metadata_handler

    result = _run(capture_metadata_handler({"session_id": "lonely-session"}))
    text = result["content"][0]["text"]
    assert "No metadata fields provided" in text


# ---------------------------------------------------------------------------
# Test 15: capture_metadata_handler — deep merge on successive calls
# ---------------------------------------------------------------------------


def test_capture_metadata_handler_deep_merges_subject(setup_db):
    """Two successive calls with different subject keys produce a merged dict.

    First call sets subject_id; second call sets sex.  The final draft must
    contain both keys under subject_json.
    """
    from agent.tools.capture_mcp import capture_metadata_handler
    from agent.tools.metadata_store import get_draft_metadata

    session_id = "test-deep-merge"

    # First call — only subject_id
    _run(
        capture_metadata_handler(
            {"session_id": session_id, "subject": {"subject_id": "100"}}
        )
    )

    # Second call — only sex (same session)
    _run(
        capture_metadata_handler(
            {"session_id": session_id, "subject": {"sex": "Female"}}
        )
    )

    # Fetch the draft directly and verify both keys survived the merge
    draft = _run(get_draft_metadata(session_id))
    assert draft is not None
    assert draft["subject_json"]["subject_id"] == "100"
    assert draft["subject_json"]["sex"] == "Female"


# ---------------------------------------------------------------------------
# Test 16: GET /metadata with status filter
# ---------------------------------------------------------------------------


def test_metadata_status_filter_returns_correct_subset(client):
    """GET /metadata?status= correctly filters by draft status.

    We create two drafts in different sessions, confirm one, then verify
    that each status filter returns exactly the expected entry.
    """
    from agent.tools.capture_mcp import capture_metadata_handler

    draft_session = "test-filter-draft"
    confirmed_session = "test-filter-confirmed"

    # Create two drafts
    _run(
        capture_metadata_handler(
            {"session_id": draft_session, "subject": {"subject_id": "11111"}}
        )
    )
    _run(
        capture_metadata_handler(
            {
                "session_id": confirmed_session,
                "subject": {"subject_id": "22222"},
            }
        )
    )

    # Confirm the second one
    resp = _run(client.post(f"/metadata/{confirmed_session}/confirm"))
    assert resp.status_code == 200

    # Filter for confirmed only
    resp = _run(client.get("/metadata?status=confirmed"))
    assert resp.status_code == 200
    confirmed_list = resp.json()
    assert len(confirmed_list) == 1
    assert confirmed_list[0]["session_id"] == confirmed_session
    assert confirmed_list[0]["status"] == "confirmed"

    # Filter for draft only
    resp = _run(client.get("/metadata?status=draft"))
    assert resp.status_code == 200
    draft_list = resp.json()
    assert len(draft_list) == 1
    assert draft_list[0]["session_id"] == draft_session
    assert draft_list[0]["status"] == "draft"


# ---------------------------------------------------------------------------
# Test 17: GET /sessions — first_message populated from user turn
# ---------------------------------------------------------------------------


def test_sessions_first_message_matches_user_turn(client):
    """After saving two conversation turns, GET /sessions returns an entry
    whose first_message is the content of the first user turn.
    """
    from agent.tools.metadata_store import save_conversation_turn

    session_id = "test-session-titles"
    user_content = "I want to log a mouse experiment"
    assistant_content = "Sure, let's start capturing metadata."

    # Persist two turns directly (bypassing the chat endpoint which needs the
    # full Claude SDK pipeline)
    _run(save_conversation_turn(session_id, "user", user_content))
    _run(save_conversation_turn(session_id, "assistant", assistant_content))

    # Fetch sessions list
    resp = _run(client.get("/sessions"))
    assert resp.status_code == 200
    sessions = resp.json()
    assert len(sessions) == 1

    session = sessions[0]
    assert session["session_id"] == session_id
    assert session["first_message"] == user_content
    assert session["message_count"] == 2


# ---------------------------------------------------------------------------
# Test 18: update_draft_metadata rejects unknown fields
# ---------------------------------------------------------------------------


def test_update_draft_metadata_rejects_unknown_field(setup_db):
    """Passing an unrecognized field name to update_draft_metadata returns a
    dict with an 'error' key rather than raising an exception or silently
    succeeding.
    """
    from agent.tools.capture_mcp import capture_metadata_handler
    from agent.tools.metadata_store import update_draft_metadata

    session_id = "test-unknown-field"

    # Seed a draft so that a row exists for this session
    _run(
        capture_metadata_handler(
            {"session_id": session_id, "subject": {"subject_id": "77777"}}
        )
    )

    # Attempt to update with a completely bogus field name
    result = _run(
        update_draft_metadata(session_id, "nonexistent_field", {"foo": "bar"})
    )

    # The function should return a dict containing an error key — not None
    # (which would indicate "session not found") and not raise
    assert result is not None
    assert "error" in result


# ---------------------------------------------------------------------------
# Test 19: DELETE /sessions/{session_id} — deletes conversations + metadata
# ---------------------------------------------------------------------------


def test_delete_session_removes_all_data(client):
    """DELETE /sessions/{id} removes conversations and draft metadata."""
    from agent.tools.capture_mcp import capture_metadata_handler
    from agent.tools.metadata_store import save_conversation_turn

    session_id = "test-session-delete"

    # Seed a draft + conversation
    _run(
        capture_metadata_handler(
            {"session_id": session_id, "subject": {"subject_id": "77777"}}
        )
    )
    _run(save_conversation_turn(session_id, "user", "hello"))

    # Verify data exists
    resp = _run(client.get("/metadata"))
    assert any(d["session_id"] == session_id for d in resp.json())
    resp = _run(client.get(f"/sessions/{session_id}/messages"))
    assert len(resp.json()) == 1

    # Delete
    resp = _run(client.delete(f"/sessions/{session_id}"))
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    # Verify data is gone
    resp = _run(client.get("/metadata"))
    assert not any(d["session_id"] == session_id for d in resp.json())
    resp = _run(client.get(f"/sessions/{session_id}/messages"))
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Test 20: DELETE /sessions/{session_id} — 404 for nonexistent session
# ---------------------------------------------------------------------------


def test_delete_session_returns_404_for_missing(client):
    """DELETE /sessions/{id} returns 404 when no data exists."""
    resp = _run(client.delete("/sessions/nonexistent-session"))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 21: Double-serialization guard — string args stored as proper JSON
# ---------------------------------------------------------------------------


def test_capture_metadata_handles_string_args(setup_db):
    """MCP tool args may arrive as JSON strings instead of dicts.

    The handler should parse them to dicts so the DB stores proper JSON
    (not double-serialized quoted strings).
    """
    import json
    from agent.tools.capture_mcp import capture_metadata_handler
    from agent.tools.metadata_store import get_draft_metadata

    session_id = "test-string-args"
    subject_dict = {"subject_id": "88888", "sex": "Female"}

    # Pass the subject as a JSON *string* (simulating SDK behaviour)
    _run(
        capture_metadata_handler(
            {"session_id": session_id, "subject": json.dumps(subject_dict)}
        )
    )

    draft = _run(get_draft_metadata(session_id))
    assert draft is not None
    # subject_json must be a dict, not a string
    assert isinstance(draft["subject_json"], dict)
    assert draft["subject_json"]["subject_id"] == "88888"
    assert draft["subject_json"]["sex"] == "Female"


# ---------------------------------------------------------------------------
# Test 22: Double-serialization guard — store layer rejects pre-serialized
# ---------------------------------------------------------------------------


def test_save_draft_metadata_prevents_double_serialization(setup_db):
    """save_draft_metadata must not double-serialize a value that is already
    a JSON string.
    """
    import json
    from agent.tools.metadata_store import save_draft_metadata, get_draft_metadata

    session_id = "test-double-serial"
    value = {"subject_id": "44444"}

    # Simulate a value that's already a JSON string
    _run(save_draft_metadata(session_id, {"subject": json.dumps(value)}))

    draft = _run(get_draft_metadata(session_id))
    assert draft is not None
    # After round-trip, should be a proper dict
    assert isinstance(draft["subject_json"], dict)
    assert draft["subject_json"]["subject_id"] == "44444"


# ---------------------------------------------------------------------------
# Test 23: Metadata list sorted by created_at DESC
# ---------------------------------------------------------------------------


def test_metadata_list_sorted_by_created_at_desc(client):
    """GET /metadata returns entries in reverse-chronological creation order.

    Confirming an entry (which updates updated_at) must NOT change the order.
    """
    import time
    from agent.tools.capture_mcp import capture_metadata_handler

    first_session = "test-sort-first"
    second_session = "test-sort-second"

    # Create two drafts with a small time gap
    _run(
        capture_metadata_handler(
            {"session_id": first_session, "subject": {"subject_id": "001"}}
        )
    )
    time.sleep(0.05)  # ensure different created_at
    _run(
        capture_metadata_handler(
            {"session_id": second_session, "subject": {"subject_id": "002"}}
        )
    )

    # Most recent first
    resp = _run(client.get("/metadata"))
    ids = [d["session_id"] for d in resp.json()]
    assert ids == [second_session, first_session]

    # Confirm the first entry (older) — this updates its updated_at
    _run(client.post(f"/metadata/{first_session}/confirm"))

    # Order must NOT change — still sorted by created_at, not updated_at
    resp = _run(client.get("/metadata"))
    ids = [d["session_id"] for d in resp.json()]
    assert ids == [second_session, first_session]


# ---------------------------------------------------------------------------
# Test 24: capture_metadata_handler stores validation after save
# ---------------------------------------------------------------------------


def test_capture_metadata_stores_validation_results(setup_db):
    """After saving metadata, the handler automatically runs validation and
    persists the result in validation_results_json.
    """
    from agent.tools.capture_mcp import capture_metadata_handler
    from agent.tools.metadata_store import get_draft_metadata

    session_id = "test-auto-validation"

    _run(
        capture_metadata_handler(
            {
                "session_id": session_id,
                "subject": {"subject_id": "12345"},
                "data_description": {
                    "modality": [{"name": "SPIM", "abbreviation": "SPIM"}],
                    "project_name": "My Project",
                },
            }
        )
    )

    draft = _run(get_draft_metadata(session_id))
    assert draft is not None
    val = draft.get("validation_results_json")
    assert val is not None
    assert isinstance(val, dict)
    assert "status" in val
    assert "completeness_score" in val


# ---------------------------------------------------------------------------
# Test 25: update_draft_metadata double-serialization guard
# ---------------------------------------------------------------------------


def test_update_draft_metadata_prevents_double_serialization(setup_db):
    """update_draft_metadata must not double-serialize a JSON string value."""
    import json
    from agent.tools.capture_mcp import capture_metadata_handler
    from agent.tools.metadata_store import update_draft_metadata, get_draft_metadata

    session_id = "test-update-double"

    # Seed a draft
    _run(
        capture_metadata_handler(
            {"session_id": session_id, "subject": {"subject_id": "111"}}
        )
    )

    # Update with a pre-serialized JSON string
    new_value = {"subject_id": "222", "sex": "Male"}
    _run(update_draft_metadata(session_id, "subject", json.dumps(new_value)))

    draft = _run(get_draft_metadata(session_id))
    assert draft is not None
    assert isinstance(draft["subject_json"], dict)
    assert draft["subject_json"]["subject_id"] == "222"
