"""SQL table definitions for the metadata capture system."""

DRAFT_METADATA_TABLE = """
CREATE TABLE IF NOT EXISTS draft_metadata (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'validated', 'confirmed', 'error')),
    subject_json TEXT,
    procedures_json TEXT,
    data_description_json TEXT,
    instrument_json TEXT,
    acquisition_json TEXT,
    session_json TEXT,
    processing_json TEXT,
    quality_control_json TEXT,
    rig_json TEXT,
    validation_results_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

CONVERSATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_draft_session ON draft_metadata(session_id);
CREATE INDEX IF NOT EXISTS idx_draft_status ON draft_metadata(status);
CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id);
"""

ALL_TABLES = [DRAFT_METADATA_TABLE, CONVERSATIONS_TABLE, CREATE_INDEXES]
