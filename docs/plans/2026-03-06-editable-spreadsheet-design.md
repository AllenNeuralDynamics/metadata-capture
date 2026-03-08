# Editable Spreadsheet Artifacts — Design

**Date:** 2026-03-06
**Branch:** `feat/spreadsheet-artifacts`
**Driver:** Colleague feedback — "if species rows were dropdowns and I could easily choose from species controlled vocabs from the schema… or if I could double-click on the genotype string field and edit it there."

## Goal

Make agent-generated `table` artifacts editable in the spreadsheet modal, with edits writing back to the source `metadata_records` (not the artifact blob). Enum-constrained columns (species, sex, modality) render as dropdowns populated from the AIND schema.

## Non-goals

- Editing uploaded CSV/XLSX files (no source record to write back to)
- Add/delete rows, multi-select, undo stack, column reordering
- Per-cell validation hints beyond what `PUT /records/{id}` already returns

## Architecture

Artifacts are **views**, not sources of truth. A table artifact rendered from subject records is a snapshot; editing a cell routes to the underlying record via the existing `PUT /records/{record_id}` endpoint. The artifact's `content_json` is never mutated — re-opening it shows the original snapshot unless the agent regenerates it.

**Row→record binding** is by convention: the agent includes a `record_id` column in tables derived from records. The frontend detects this column, hides/mutes it visually, and uses its value as the routing key. Tables without it stay read-only — no migration, graceful degradation.

**Column→enum binding** is by name: a new `GET /schema/enums` endpoint returns `{species: [...], sex: [...], modality: [...]}`. Frontend case-insensitive-matches column headers against these keys. Brittleness is mitigated by the agent generating the column names from schema field names.

```
┌──────────────────┐  click cell      ┌────────────────────┐
│ SpreadsheetViewer│ ──────────────▶  │ EditableCell       │
│  (selection,     │                  │  draft/isSaving/   │
│   formula bar,   │  ◀────────────── │  error state       │
│   col resize)    │  commit(r,c,v)   │  machine           │
└────────┬─────────┘                  └────────────────────┘
         │ onCellCommit(recordId, field, value)
         ▼
┌──────────────────┐     PUT /records/{id}    ┌────────────────┐
│ ArtifactModal    │ ───────────────────────▶ │ agent/server.py│
│  (detect         │                          │  (merge, re-   │
│   record_id,     │  ◀─────────────────────  │  validate,     │
│   fetch enums)   │  {data_json, validation} │  save)         │
└──────────────────┘                          └────────────────┘
```

## Reference implementations

### `apps/user-content-renderer/components/renderers/shared/TableView.tsx` (251 lines)
Claude.ai's read-only spreadsheet viewer. Provides:
- Excel visual language: A/B/C column letters, row numbers, formula bar
- `cursor-cell`, sticky top+left headers, `tableLayout: fixed`
- Selection: single-click → `bg-blue-50 outline-2 outline-blue-500`
- Column resize: drag handle at header right edge, document-level `mousemove`/`mouseup`

### `apps/claude-ai/components/KnowledgeBases/.../EditableField.tsx`
The inline-edit state machine:
- Four states: `isEditing`, `draft`, `isSaving`, `error`
- Display mode: `role="button"`, click/Enter/Space → edit
- Edit mode: `autoFocus` input, blur/Enter commits, Esc cancels
- **No-change short-circuit:** `if (trimmed === value) return` — skip network
- **On save error:** stay in edit mode with inline error — user retries or Esc's out (does NOT silently revert)
- `useEffect` resyncs `draft` from prop when `!isEditing` (concurrent update safety)

## UI & edit mechanics

### Visual shell (port TableView, keep sand palette)
- Column-letter row (A, B, C…) above existing field-name header
- Formula bar: full content of selected cell (solves existing `truncate` tooltip problem)
- Selection ring: `outline-2 outline-brand` (terracotta, not blue)
- Column resize: port TableView's drag-handle pattern
- Skip `@grid-is/mondrian-react` (formula evaluation — not needed)

### `EditableCell` (port EditableField state machine + enum mode)
Three render modes, chosen per column:

| Mode | Applies when | Behavior |
|---|---|---|
| **text** | column in `KNOWN_FIELDS` for the artifact's record type, not in enums | Click = select. Click-again/type/Enter → `autoFocus <input>`. Blur/Enter = commit. Esc = revert. |
| **enum** | column name matches a key in `/schema/enums` | Click = select. Click-again → inline `<select>`, blur commits (single-action). |
| **read-only** | `record_id` column, or column not in `KNOWN_FIELDS` | Selectable (formula bar shows content) but never edits. Muted cursor. Safety rail against writing garbage fields. |

Commit = `onCellCommit(recordId, field, value) => Promise<void>`. On error: stay in edit, show error below cell. On success: optional brief green pulse. If returned `validation_json` has a warning for that field: amber underline + tooltip.

## Contracts

### Backend: `GET /schema/enums`
```python
@app.get("/schema/enums")
async def get_schema_enums() -> dict[str, list[str]]:
    from .schema_info import VALID_SPECIES, VALID_SEX, VALID_MODALITIES
    return {
        "species": sorted(VALID_SPECIES),
        "sex": sorted(VALID_SEX),
        "modality": sorted(VALID_MODALITIES),
    }
```
Module-load cached. Returns empty lists if `aind-data-schema` not installed (existing `SCHEMA_AVAILABLE` fallback).

### Backend: `PUT /records/{record_id}` — unchanged
Already takes `{data: {...}}`, merges, re-validates via `validate_record`, returns updated record with `validation_json`.

### System prompt addition
Under `render_artifact` tool guidance:
> When rendering a table derived from metadata records, include a `record_id` column as the first column so the user can edit cells in-app.

### Frontend: `SpreadsheetViewer` new props
```ts
interface SpreadsheetViewerProps {
  columns: string[];
  rows: (string | number | null)[][];
  totalRows?: number;
  sheetName?: string | null;
  // NEW — all optional, absence = current read-only behavior
  enums?: Record<string, string[]>;           // column name → valid values
  editableColumns?: Set<string>;              // which columns accept text edits
  recordIdColumn?: number;                    // index of record_id column (hidden)
  onCellCommit?: (recordId: string, column: string, value: string) => Promise<void>;
}
```

### Frontend: `ArtifactModal` wiring
On artifact load, if `artifact_type === 'table'`:
1. Find `record_id` in `content.columns` (case-insensitive). Absent → read-only, done.
2. Fetch `GET /schema/enums` (once, memoized).
3. Pass `recordIdColumn`, `enums`, and `onCellCommit` to `SpreadsheetViewer`.
4. `onCellCommit`: fetch the record, shallow-merge `{[column]: value}` into `data`, `PUT /records/{id}`. Throw on non-2xx (lets `EditableCell` show the error).

## Files

| File | Change | Est. lines |
|---|---|---|
| `agent/server.py` | `GET /schema/enums` | +15 |
| `agent/prompts/system_prompt.py` | `record_id` column instruction | +5 |
| `frontend/app/lib/api.ts` | `fetchSchemaEnums()`, `updateRecordField()` | +25 |
| `frontend/app/components/SpreadsheetViewer.tsx` | Selection, formula bar, `EditableCell`, resize | ~+250 |
| `frontend/app/components/ArtifactModal.tsx` | Detect editability, wire commit | +40 |

## Testing

- `evals/tasks/validation/test_schema_enums.py` — endpoint non-empty, values match `schema_info.VALID_*`
- `verify-in-chrome`: open artifact → edit species dropdown → confirm `PUT` fires + dashboard reflects
- Manual edge cases: no-change commit (no network), Esc revert, 404 on PUT (stays in edit with error)

## Open questions

- **`editableColumns` source:** where does the frontend get `KNOWN_FIELDS[record_type]`? Options: (a) extend `/schema/enums` to also return `known_fields`, (b) the agent embeds `record_type` in the artifact title/metadata and frontend fetches per-type, (c) YAGNI — anything that's not `record_id` and not an enum is text-editable for now, let server-side validation catch garbage. **Leaning (c)** — the `PUT /records/{id}` already validates unknown fields and returns warnings.
- **Stale snapshot:** after editing, the artifact still shows old values on reopen. Acceptable for MVP (agent can regenerate), but worth a "data may be stale — regenerate?" banner later.
