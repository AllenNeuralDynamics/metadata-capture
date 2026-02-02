# Agentic Metadata Capture System — Implementation Plan

## Overview
Build a real-time metadata capture and validation platform for AIND using the **Claude Agent SDK** (Python). Scientists interact via a web app; a Claude agent extracts, validates, and enriches metadata against AIND schemas and external registries. The existing `aind-metadata-mcp` server plugs in directly via MCP integration.

## MVP Scope
- **Text-based metadata capture** via conversational chat interface
- **NLP extraction** of structured metadata from free-text scientist input
- **Schema validation** against AIND's live metadata database (read-only via MCP)
- **External registry validation** (Addgene, NCBI GenBank, MGI)
- **Proactive prompting** for missing/incomplete fields
- **Dashboard** for reviewing and confirming captured metadata
- **Local SQLite** for draft metadata storage (future: AIND MongoDB write access)

Multi-modal (audio, image, video) deferred to post-MVP.

---

## Architecture

```
┌─────────────────────────────────────────────┐
│           Next.js Frontend (React)          │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐ │
│  │Chat View │  │Dashboard │  │Validation │ │
│  │(capture) │  │(review)  │  │(status)   │ │
│  └──────────┘  └──────────┘  └───────────┘ │
└──────────────────┬──────────────────────────┘
                   │ REST / SSE
┌──────────────────▼──────────────────────────┐
│       Thin API Layer (FastAPI)               │
│       Wraps Claude Agent SDK query()         │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│         Claude Agent SDK (Python)            │
│                                              │
│  ┌─────────────────────────────────────┐     │
│  │ Main Capture Agent                  │     │
│  │ - System prompt with AIND schema    │     │
│  │ - Extracts metadata from text       │     │
│  │ - Proactively prompts for gaps      │     │
│  │ - Orchestrates validation           │     │
│  └─────────────────────────────────────┘     │
│                                              │
│  Built-in tools: Read, Write, Bash, Grep,    │
│  Glob, WebSearch, WebFetch                   │
│                                              │
│  MCP: aind-metadata-mcp (21 tools)           │
│  ┌──────────────────────────────────────┐    │
│  │ get_records, aggregation_retrieval,  │    │
│  │ count_records, get_subject_example,  │    │
│  │ get_procedures_example, etc.         │    │
│  └──────────────────────────────────────┘    │
└──────────────────┬──────────────────────────┘
        ┌──────────┼──────────┐
        ▼          ▼          ▼
   ┌─────────┐ ┌────────┐ ┌────────────┐
   │SQLite   │ │AIND    │ │External    │
   │(drafts) │ │MongoDB │ │Registries  │
   │local    │ │(read)  │ │(web APIs)  │
   └─────────┘ └────────┘ └────────────┘
```

---

## Project Structure

```
metadata-capture/
├── agent/                          # Claude Agent SDK service
│   ├── server.py                   # FastAPI: POST /chat (SSE), GET/PUT /metadata, GET /sessions, GET /health
│   ├── service.py                  # Core agent: streaming query(), token-level StreamEvent handling
│   ├── validation.py               # Schema validation: required fields, enums, formats, cross-field
│   ├── prompts/
│   │   └── system_prompt.py        # AIND schema context + extraction instructions
│   ├── tools/
│   │   ├── metadata_store.py       # SQLite CRUD: save/load/update/confirm drafts
│   │   └── registry_lookup.py      # Addgene, NCBI, MGI API wrappers
│   ├── db/
│   │   ├── database.py             # Async SQLite (aiosqlite, WAL mode)
│   │   └── models.py               # DDL: draft_metadata + conversations tables
│   └── requirements.txt
│
├── frontend/                       # Next.js 14 + TypeScript + Tailwind CSS
│   ├── app/
│   │   ├── page.tsx                # Three-pane layout: sessions sidebar | chat | metadata sidebar
│   │   ├── dashboard/page.tsx      # Inline-editable metadata dashboard with schema placeholders
│   │   ├── components/
│   │   │   ├── Header.tsx          # Shared nav bar + live Agent Online/Offline health indicator
│   │   │   ├── ChatPanel.tsx       # Token-streaming chat, stop button, auto-expanding input
│   │   │   ├── SessionsSidebar.tsx # Chat history list with first-message titles
│   │   │   └── MetadataSidebar.tsx # Clickable metadata cards linking to dashboard
│   │   └── lib/api.ts              # API client: chat (SSE + AbortSignal), metadata CRUD, sessions
│   └── package.json
│
├── evals/                          # Comprehensive eval suite (see evals/README.md)
│
├── aind-metadata-mcp/              # MCP server (21 tools, moved into project)
```

---

## Implementation Phases

### Phase 1: Agent Core Setup ✅
**Files:** `agent/service.py`, `agent/server.py`, `agent/prompts/system_prompt.py`

- Claude Agent SDK with `query()` for streaming responses
- FastAPI wrapper: POST /chat (SSE), GET /metadata, PUT /metadata/{id}/fields, POST /metadata/{id}/confirm, GET /sessions/{id}/messages, GET /health
- System prompt with AIND schema context
- Model: `claude-opus-4-5-20251101`

### Phase 2: Local Storage + Custom Tools ✅
**Files:** `agent/db/`, `agent/tools/metadata_store.py`

- SQLite with async aiosqlite (WAL mode)
- Draft metadata table with 9 JSON columns per schema section
- Conversations table for multi-turn history
- CRUD tools: save/get/update/list/confirm drafts

### Phase 3: Validation Engine ✅ (partial)
**Files:** `agent/validation.py`, `agent/tools/registry_lookup.py`, `agent/tools/capture_mcp.py`

Done:
- Local schema validation: required fields, enum checks, format rules, cross-field consistency, completeness scoring
- External registry lookups: Addgene (catalog + search), NCBI E-utilities, MGI quick search
- Validation API endpoint: `GET /metadata/{session_id}/validation`
- Auto-validation after every metadata update via the `capture_metadata` tool
- Frontend validation display: progress bar, status badges, expandable errors/warnings

Not yet done:
- Automatic registry validation in extraction pipeline (functions exist but not auto-triggered)
- Deeper schema validation via `aind-data-schema` Pydantic models
- Validation feedback loop into agent conversation for proactive prompting

### Phase 3.5: Tool-Based Extraction ✅ (NEW)
**Files:** `agent/tools/capture_mcp.py`, `agent/service.py`, `agent/prompts/system_prompt.py`

Migrated from regex-based post-processing extraction to Claude-native tool calls:
- Created `capture_metadata` MCP tool that Claude calls directly during conversation
- Claude extracts metadata and persists it via tool calls (not regex scraping)
- Removed `_extract_metadata_fields()` regex function
- Updated system prompt with tool usage instructions
- Updated evals to test tool handler instead of regex patterns

### Phase 4: Frontend — Chat Interface ✅
**Files:** `frontend/app/page.tsx`, `frontend/app/components/`

- Token-by-token SSE streaming via SDK `include_partial_messages` + `StreamEvent` deltas
- Stop button aborts the stream mid-response via `AbortController`
- Auto-expanding textarea (no height cap); send button is an up-arrow icon inside the input
- Sessions sidebar lists all chats by first-message preview; click to switch, "New Chat" to start fresh
- Conversation history persists across page reloads (loaded from `GET /sessions/{id}/messages`)
- Side panel with extracted metadata fields, expandable JSON sections
- Metadata cards in the sidebar are clickable — navigate to the dashboard entry
- Auto-refresh, status badges, mobile-responsive

### Phase 5: Frontend — Dashboard ✅
**Files:** `frontend/app/dashboard/page.tsx`

- Table of all draft metadata entries with status tracking
- Expandable rows auto-expand when navigated via hash (`/dashboard#<session_id>`)
- **Inline editing**: click any value to edit it; saves on Enter or blur
- **Rename fields**: click any field label to rename the underlying key
- **Delete fields**: trash icon appears on hover; removes the key from the section
- **Add fields**: `+ Add field` row at the bottom of every section; Tab from name to value
- **Schema placeholders**: empty sections show known fields (Subject ID, Species, Sex, etc.) as "click to add" rows — no JSON editor needed
- Confirm button, filter by status, search
- Shared `Header` component with live Agent Online / Offline indicator (polls `/health` every 5 s)

### Phase 6: Streaming & UX Polish ✅
**Files:** `agent/service.py`, `frontend/app/components/ChatPanel.tsx`, `frontend/tailwind.config.ts`

- Enabled `include_partial_messages` on the SDK; yield `content_block_delta` text tokens directly
- Replaced generic blue palette with warm Anthropic-inspired light theme (sand neutrals, terracotta `#D97757` accent)
- Streaming cursor uses a blinking filled circle in the accent color

---

## Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Agent framework | Claude Agent SDK (Python) | Built-in tools, MCP integration, session management |
| MCP integration | Existing `aind-metadata-mcp` | 21 tools already built for AIND DB access |
| Frontend | Next.js 14 + TypeScript + Tailwind | App Router, SSE streaming, mobile-responsive |
| API layer | FastAPI wrapping SDK `query()` | Async streaming, Python ecosystem match |
| Local DB | SQLite via aiosqlite | Zero-config MVP, WAL mode for concurrency |
| Model | claude-opus-4-5-20251101 | Most capable for complex metadata extraction |
| Streaming | SDK `include_partial_messages` + `StreamEvent` | Token-by-token deltas without buffering full messages |
| Stop streaming | `AbortController` + `AbortSignal` on fetch | Cleanly closes SSE connection; partial response stays visible |
| Inline editing | `deepSet` / `renameKey` / `deleteKey` + PUT endpoint | Per-field granularity; auto-saves on blur, no full-page reload |
| Session titles | First user message from DB | Matches Claude desktop UX; no extra LLM call needed |
| Auth | None for MVP | Add Allen SSO later |

---

## Running the Project

```bash
# Backend (from metadata-capture/ directory)
pip install -r agent/requirements.txt
python3 -m uvicorn agent.server:app --port 8001 --reload  # auto-reloads on file save

# Frontend (from metadata-capture/frontend/ directory)
npm install
npm run dev                                                # auto-reloads on file save

# Run evals (from metadata-capture/ directory)
python3 -m pytest evals/ -x -q                                    # deterministic only
python3 -m pytest evals/tasks/conversation/ -v -m llm              # LLM-graded (needs ANTHROPIC_API_KEY)
python3 -m pytest evals/tasks/validation/ -v -m network            # registry lookups (needs network)
```

---

## Known Issues & Fixes Applied

- **Relative imports**: Must run backend from `metadata-capture/` directory, not from `agent/`
- **Tool-based extraction**: Regex extraction has been replaced with Claude tool calls. The old regex bugs (project name, session end time, protocol ID) are no longer applicable.
- **Python version**: The backend uses `X | Y` union type syntax, which requires Python 3.10+. Any Python ≥ 3.10 works — no conda needed.

---

## Future Work
- Auto-trigger registry lookups (Addgene, NCBI, MGI) when relevant fields are extracted
- Deeper schema validation via `aind-data-schema` Pydantic models
- Feed validation results back into agent conversation for proactive prompting
- Multi-modal input (audio, image, video, documents)
- MCP write access to AIND MongoDB
- Cloud deployment (Cloud Run)
- Allen SSO authentication
- Performance optimization (concurrent users, token efficiency)
