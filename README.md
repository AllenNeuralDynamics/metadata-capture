# AIND Metadata Capture

A real-time metadata capture and validation platform for the Allen Institute for Neural Dynamics (AIND). Scientists describe their experiments in natural language; a Claude-powered agent extracts structured metadata, validates it against AIND schemas and external registries, and proactively prompts for missing information.

## Features

- **Conversational capture** — Chat interface where scientists describe experiments in plain language
- **Automatic extraction** — Agent extracts structured metadata fields (subject ID, species, modality, project, session times, protocol, coordinates, etc.) via native Claude tool calls
- **Token-by-token streaming** — Real-time SSE streaming with a stop button to abort mid-response
- **Live database validation** — Validates project names, subject IDs, and modalities against AIND's live MongoDB via MCP
- **Registry validation** — Cross-references Addgene, NCBI GenBank, and MGI databases
- **Proactive prompting** — Identifies missing required fields and asks the scientist
- **Session persistence** — Conversations survive page reloads; a sidebar lets you switch between chats
- **Inline-editable dashboard** — Click any value to edit, rename, or delete fields; add new ones with a single keystroke; schema-guided placeholders for every known field
- **Live health indicator** — Header badge polls the backend and shows Agent Online / Offline in real time

## Architecture

The system has three components:

1. **Agent backend** (`agent/`) — Python service using the Claude Agent SDK, wrapped in FastAPI. Streams token-by-token via `include_partial_messages` + `StreamEvent`. Metadata extraction happens through native Claude tool calls (`capture_metadata`). Stores drafts and conversation history in SQLite.

2. **Web frontend** (`frontend/`) — Next.js 14 app with TypeScript and Tailwind CSS. Three-pane layout: a sessions sidebar for switching chats, a token-streaming chat panel with a stop button, and a metadata sidebar with clickable cards. A separate dashboard page lets you inline-edit, rename, delete, and add metadata fields with auto-save.

3. **AIND MCP server** (`aind-metadata-mcp/`) — MCP server with 20 tools for read-only access to AIND's live metadata MongoDB (hosted at `api.allenneuraldynamics.org`). Connected to the agent via stdio transport — the agent can query project names, look up existing records, fetch example schemas, and validate metadata against production data.

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- An Anthropic API key (set as `ANTHROPIC_API_KEY` environment variable or in `metadata-capture/.env`)

### MCP Server

From the `metadata-capture/` directory, install the MCP server:

```bash
cd aind-metadata-mcp
pip install -e .
cd ..
```

This installs the `aind-metadata-mcp` package and its dependencies (`aind-data-access-api`, `fastmcp`, etc.). The agent automatically discovers and launches it via the `mcp_config.json` file.

### Backend

From the `metadata-capture/` directory, create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r agent/requirements.txt
python3 -m uvicorn agent.server:app --port 8001 --reload  # auto-reloads on save
```

The API will be available at `http://localhost:8001`. Key endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/chat` | POST | Send a message, receive token-level SSE stream |
| `/metadata` | GET | List all draft metadata entries |
| `/metadata/{id}/fields` | PUT | Update a single metadata section (inline editing) |
| `/metadata/{id}/confirm` | POST | Confirm a draft entry |
| `/sessions` | GET | List all chat sessions with message counts |
| `/sessions/{id}/messages` | GET | Full conversation history for a session |
| `/health` | GET | Health check (polled by the frontend every 5 s) |

### Frontend

From the `metadata-capture/` directory:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. The frontend connects to the backend at `localhost:8001` by default (configurable via `NEXT_PUBLIC_API_URL`).

## Example Interaction

**Scientist:** "I ran a two-photon calcium imaging session on mouse 553429 today. The project is called BrainMap. Started at 10:30 AM, ending at 2:15 PM."

**Agent extracts:**
- `subject.subject_id`: "553429"
- `subject.species.name`: "Mus musculus"
- `data_description.modality`: "pophys" (two-photon optical physiology)
- `data_description.project_name`: "BrainMap"
- `session.session_start_time`: "10:30 AM"
- `session.session_end_time`: "2:15 PM"

The agent then asks about missing required fields like sex, rig ID, and protocol.

## Evals

See [`evals/README.md`](evals/README.md) for the comprehensive evaluation suite covering extraction accuracy, conversational quality, registry validation, and end-to-end pipeline tests.

```bash
# Run all deterministic tests (no API key or network needed)
python3 -m pytest evals/ -x -q -m "not llm and not network"

# Run LLM-graded conversation tests (requires ANTHROPIC_API_KEY)
python3 -m pytest evals/tasks/conversation/ -v -m llm

# Run registry validation tests (requires network)
python3 -m pytest evals/tasks/validation/ -v -m network
```

## Project Status

- [x] Phase 1: Agent core (Claude Agent SDK + FastAPI)
- [x] Phase 2: Local storage (SQLite + CRUD tools)
- [x] Phase 3: Validation (schema validation, Addgene/NCBI/MGI registries, live AIND MongoDB via MCP)
- [x] Phase 3.5: Tool-based extraction (replaced regex with native Claude tool calls)
- [x] Phase 4: Chat interface (token streaming, stop button, sessions sidebar, session persistence)
- [x] Phase 5: Dashboard (inline edit/rename/delete/add fields, schema placeholders, auto-save)
- [x] Phase 6: Streaming & UX polish (terracotta theme, live health indicator, auto-expanding input)
- [x] Eval suite (60 tests across 5 suites)
- [ ] Auto-trigger registry lookups — when extraction finds a `protocol_id`, gene name, or plasmid reference, automatically call the Addgene/NCBI/MGI lookup functions and attach results to the draft (functions exist in `registry_lookup.py` but are not yet called from the extraction flow)
- [ ] Validation feedback loop — after `_validate_and_store()` runs, feed validation errors/warnings back into the agent's conversation context so it can proactively surface issues (e.g. "Your subject ID looks invalid") in its next response
- [ ] Deeper schema validation via `aind-data-schema` — replace hardcoded enums/formats in `validation.py` with Pydantic model validation from the `aind-data-schema` package so validation stays in sync with the real AIND schemas
- [ ] Multi-modal input (audio recordings, images of lab notebooks, documents)
- [ ] MCP write access to AIND MongoDB
- [ ] Cloud deployment
- [ ] Authentication (Allen SSO)
