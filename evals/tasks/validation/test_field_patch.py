"""Tests for the field-aware PATCH endpoint and supporting APIs.

The PATCH endpoint exists because `species` is stored as a nested dict
{name, registry, registry_identifier} but surfaced in artifact tables as a
flat string. A naive PUT would clobber the dict with a bare string via
update_record's shallow merge. PATCH reconstructs the full dict server-side
so the frontend can just send the display value.

Run from metadata-capture/:
    python3 -m pytest evals/tasks/validation/test_field_patch.py -v
"""

import asyncio
import json
import os

import pytest
from httpx import ASGITransport, AsyncClient


_loop = asyncio.new_event_loop()


def _run(coro):
    return _loop.run_until_complete(coro)


@pytest.fixture()
def setup_db(tmp_path):
    async def _setup():
        os.environ["METADATA_DB_DIR"] = str(tmp_path)
        import agent.db.database as db_mod
        db_mod._db_connection = None
        db_mod.DB_DIR = tmp_path
        db_mod.DB_PATH = tmp_path / "metadata.db"
        from agent.db.database import init_db
        await init_db()

    _run(_setup())
    yield

    async def _teardown():
        from agent.db.database import close_db
        await close_db()

    _run(_teardown())


@pytest.fixture()
def client(setup_db):
    from agent.server import app
    transport = ASGITransport(app=app)
    c = AsyncClient(transport=transport, base_url="http://testserver")
    yield c
    _run(c.aclose())


def _create_subject(session_id: str, data: dict) -> str:
    """Create a subject record via the capture handler, return its record_id."""
    from agent.tools.capture_mcp import capture_metadata_handler
    result = _run(capture_metadata_handler({
        "session_id": session_id,
        "record_type": "subject",
        "data": data,
    }))
    return json.loads(result["content"][0]["text"])["record_id"]


# ---------------------------------------------------------------------------
# PATCH /records/{id}/field — the data-corruption fix
# ---------------------------------------------------------------------------


def test_patch_species_preserves_dict_shape(client):
    """The core P0: species must stay a dict after PATCH, not become a string."""
    rid = _create_subject("t-species", {
        "subject_id": "100",
        "species": {"name": "Mus musculus", "registry": "NCBI", "registry_identifier": "txid10090"},
    })

    resp = _run(client.patch(f"/records/{rid}/field", json={"field": "species", "value": "Rattus norvegicus"}))
    assert resp.status_code == 200

    species = resp.json()["data_json"]["species"]
    assert isinstance(species, dict), f"species corrupted to {type(species).__name__}: {species!r}"
    assert species["name"] == "Rattus norvegicus"


def test_patch_species_reconstructs_registry_when_known(client):
    """If the value is in SPECIES_REGISTRY, registry info is auto-populated."""
    from agent.schema_info import SPECIES_REGISTRY
    if not SPECIES_REGISTRY:
        pytest.skip("aind-data-schema not installed — SPECIES_REGISTRY empty")

    rid = _create_subject("t-registry", {"subject_id": "101"})
    known_name = next(iter(SPECIES_REGISTRY))

    resp = _run(client.patch(f"/records/{rid}/field", json={"field": "species", "value": known_name}))
    assert resp.status_code == 200

    species = resp.json()["data_json"]["species"]
    assert species["name"] == known_name
    assert "registry_identifier" in species
    assert species["registry_identifier"] == SPECIES_REGISTRY[known_name]["registry_identifier"]


def test_patch_species_unknown_value_still_dict(client):
    """Unknown species names don't get registry info, but don't corrupt either."""
    rid = _create_subject("t-unknown", {"subject_id": "102"})

    resp = _run(client.patch(f"/records/{rid}/field", json={"field": "species", "value": "Made-up species"}))
    assert resp.status_code == 200

    species = resp.json()["data_json"]["species"]
    assert species == {"name": "Made-up species"}


def test_patch_sex_stores_flat_string(client):
    """sex is a flat field — no shape mapping needed."""
    rid = _create_subject("t-sex", {"subject_id": "103", "sex": "Male"})

    resp = _run(client.patch(f"/records/{rid}/field", json={"field": "sex", "value": "Female"}))
    assert resp.status_code == 200
    assert resp.json()["data_json"]["sex"] == "Female"


def test_patch_unknown_field_rejected_with_400(client):
    """Unlike PUT (which warn-and-stores), PATCH refuses unknown fields."""
    from agent.schema_info import KNOWN_FIELDS
    if not KNOWN_FIELDS.get("subject"):
        pytest.skip("aind-data-schema not installed — no known-field list to check against")

    rid = _create_subject("t-reject", {"subject_id": "104"})

    resp = _run(client.patch(f"/records/{rid}/field", json={"field": "made_up_field", "value": "x"}))
    assert resp.status_code == 400
    assert "made_up_field" in resp.json()["detail"]


def test_patch_nonexistent_record_404(client):
    resp = _run(client.patch("/records/not-a-real-id/field", json={"field": "sex", "value": "Male"}))
    assert resp.status_code == 404


def test_patch_preserves_other_fields(client):
    """Shallow merge at update_record should leave sibling fields intact."""
    rid = _create_subject("t-preserve", {"subject_id": "105", "sex": "Male", "genotype": "wt"})

    resp = _run(client.patch(f"/records/{rid}/field", json={"field": "sex", "value": "Female"}))
    assert resp.status_code == 200

    data = resp.json()["data_json"]
    assert data["sex"] == "Female"
    assert data["subject_id"] == "105"
    assert data["genotype"] == "wt"


# ---------------------------------------------------------------------------
# GET /schema/enums
# ---------------------------------------------------------------------------


def test_schema_enums_returns_species_and_sex(client):
    resp = _run(client.get("/schema/enums"))
    assert resp.status_code == 200

    enums = resp.json()
    assert set(enums.keys()) == {"species", "sex"}  # modality deliberately absent
    assert "Male" in enums["sex"]
    assert "Female" in enums["sex"]
    assert len(enums["species"]) > 0
    assert enums["species"] == sorted(enums["species"])  # sorted for stable UI


# ---------------------------------------------------------------------------
# GET /records?ids=a,b,c — batch fetch for the overlay
# ---------------------------------------------------------------------------


def test_list_records_ids_filter(client):
    rid_a = _create_subject("t-ids", {"subject_id": "A"})
    rid_b = _create_subject("t-ids", {"subject_id": "B"})
    _create_subject("t-ids", {"subject_id": "C"})  # not in the filter

    resp = _run(client.get(f"/records?ids={rid_a},{rid_b}"))
    assert resp.status_code == 200

    records = resp.json()
    assert {r["id"] for r in records} == {rid_a, rid_b}


def test_list_records_ids_filter_missing_id_omitted(client):
    """Nonexistent IDs are simply absent — no error. Overlay treats missing as read-only."""
    rid = _create_subject("t-missing", {"subject_id": "X"})

    resp = _run(client.get(f"/records?ids={rid},hallucinated-uuid"))
    assert resp.status_code == 200

    records = resp.json()
    assert len(records) == 1
    assert records[0]["id"] == rid


def test_list_records_ids_empty_string_ignored(client):
    """Trailing commas / empty segments don't break the query."""
    rid = _create_subject("t-empty", {"subject_id": "Y"})

    resp = _run(client.get(f"/records?ids={rid},,"))
    assert resp.status_code == 200
    assert len(resp.json()) == 1
