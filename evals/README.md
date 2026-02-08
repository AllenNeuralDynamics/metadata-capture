# AIND Metadata Capture — Eval Suite

Evaluation suite for the metadata capture agent. Covers tool handler tests, registry validation, conversational quality, and end-to-end pipeline tests.

## Quick Start

```bash
# From metadata-capture/ directory

# Run all non-LLM tests (fast, no API calls)
python3 -m pytest evals/ -x -q --ignore=evals/tasks/extraction/

# Run agent extraction tests (requires ANTHROPIC_API_KEY)
python3 -m pytest evals/tasks/extraction/ -v -m llm

# Run conversation tests (requires ANTHROPIC_API_KEY)
python3 -m pytest evals/tasks/conversation/ -v -m llm

# Run registry tests (requires network access)
python3 -m pytest evals/tasks/validation/ -v -m network
```

## Suites

### 1. Extraction (43 tests) — Agent Accuracy

Runs the full agent on scientist input and verifies correct fields are saved to SQLite. Requires `ANTHROPIC_API_KEY`.

Covers:
- Subject extraction (ID, species, sex)
- Modality detection (two-photon, ecephys, etc.)
- Session timing, rig IDs
- Procedures, coordinates, protocols
- False positive checks (shouldn't extract from irrelevant text)

**Grader:** Deterministic field matching against SQLite.

### 2. Conversation (11 tests) — LLM Judge

Tests the full `chat()` function and grades responses with an LLM rubric (Sonnet 4.5). Requires `ANTHROPIC_API_KEY`.

| Scenario | What's graded |
|----------|---------------|
| Basic metadata capture | Extraction accuracy, asks for missing fields |
| Multi-turn progressive | Fields accumulate correctly across turns |
| Ambiguous modality | Asks clarifying questions |
| Protocol + coordinates | Captures multiple fields from one message |
| Validation: invalid sex | Flags invalid value, suggests corrections |
| Validation: invalid modality | Flags xray as invalid, lists valid options |
| Validation: clean pass | No false alarms when all fields are valid |
| Registry: genotype lookup | Shares MGI/NCBI results for alleles |
| Registry: plasmid lookup | Shares Addgene results for injection materials |
| Registry: session (no lookup) | Avoids irrelevant registry mentions |
| Unknown fields flagged | Warns about non-schema fields |
| Context: modality → data_description | Creates correct record type |

**Grader:** `graders/llm_judge.py::grade_conversation` — rubric-based scoring (1-5) on accuracy, completeness, proactiveness, tone. Pass threshold: average >= 3.5.

### 3. Validation (8 tests) — Network

Tests the external registry lookup tools against live APIs. Requires network access.

| Registry | Tests |
|----------|-------|
| Addgene | Numeric lookup, name search, nonexistent ID |
| NCBI Gene | Symbol lookup (GCaMP6f), ID lookup, not found |
| MGI | Gene lookup (Ai14), ID lookup |

### 4. End-to-End (5 tests) — Integration

Tests the full HTTP pipeline: API → agent → extraction → SQLite → retrieval. Uses httpx AsyncClient with ASGI transport (no running server needed).

| Test | What's verified |
|------|-----------------|
| Health check | GET /health returns ok |
| Chat creates draft | POST /chat → GET /metadata shows draft |
| Fields persist | Extracted fields stored in DB correctly |
| Session isolation | Different session_ids have separate drafts |
| Confirm draft | POST confirm changes status |

### 5. Agent (10 tests) — End-to-End Agent Evals

Sends prompts to the live agent via `/chat` SSE, then grades both the DB outcome (deterministic) and the response text (LLM judge). Requires `ANTHROPIC_API_KEY` and network access.

```bash
python3 -m pytest evals/tasks/agent/ -v -m llm
```

| Category | Tests | What's verified |
|----------|-------|-----------------|
| Schema validation | 4 | Agent flags invalid sex/modality, maps SLAP→slap2, stays silent on clean records |
| Registry lookups | 3 | Agent shares MGI/NCBI results for genotypes, Addgene for plasmids, skips for sessions |
| Context-aware | 3 | Modality → data_description, subject reuse across messages, unknown field warnings |

**Graders:** Deterministic DB state checks (record exists, correct type/fields) + LLM rubric scoring on response quality.

## Structure

```
evals/
├── conftest.py                 # Shared fixtures (DB, agent client, cleanup)
├── graders/
│   ├── deterministic.py        # Field match, absence check, partial credit
│   └── llm_judge.py            # LLM-as-judge with rubric scoring
├── tasks/
│   ├── agent/
│   │   └── test_agent_evals.py # End-to-end agent evals (10 tests, LLM + deterministic)
│   ├── extraction/
│   │   ├── cases.yaml              # ~40 extraction test cases
│   │   └── test_agent_extraction.py # Agent accuracy tests (LLM)
│   ├── conversation/
│   │   ├── cases.yaml          # 11 LLM-graded cases
│   │   └── test_conversation.py
│   ├── validation/
│   │   ├── cases.yaml          # 8 registry cases
│   │   └── test_validation.py
│   └── end_to_end/
│       ├── cases.yaml          # 5 pipeline cases
│       └── test_e2e.py
├── runner.py                   # CLI harness (trials, grading, aggregation)
├── report.py                   # pass@k, pass^k, avg_score metrics
└── __main__.py                 # Entry point for python -m evals.runner
```

## Metrics

| Metric | Description |
|--------|-------------|
| pass@1 | % of tasks passing on first try |
| pass@k | At least 1 pass in k trials |
| pass^k | All k trials pass (consistency) |
| avg_score | Average partial credit score |
