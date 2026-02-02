"""MCP server for metadata capture tool.

This module provides an in-process MCP server with a capture_metadata tool
that Claude can call directly during conversation to save extracted metadata.
"""

import json
import logging
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from .metadata_store import (
    get_draft_metadata,
    save_draft_metadata,
    update_draft_metadata,
)
from ..validation import validate_metadata

logger = logging.getLogger(__name__)


async def capture_metadata_handler(args: dict[str, Any]) -> dict[str, Any]:
    """Core logic for saving metadata fields to the draft.

    This function is separated from the @tool decorator to allow direct testing.
    """
    session_id = args.get("session_id")
    if not session_id:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Error: session_id is required",
                }
            ]
        }

    # Collect non-null metadata fields
    metadata_fields = [
        "subject",
        "data_description",
        "session",
        "procedures",
        "instrument",
        "acquisition",
        "processing",
        "quality_control",
        "rig",
    ]

    metadata: dict[str, Any] = {}
    for field in metadata_fields:
        value = args.get(field)
        if value is not None:
            # MCP tool args may arrive as JSON strings instead of parsed dicts;
            # ensure we always store Python dicts.
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except (json.JSONDecodeError, ValueError):
                    pass
            metadata[field] = value

    if not metadata:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "No metadata fields provided. Include at least one of: subject, data_description, session, procedures, instrument, acquisition, processing, quality_control, rig",
                }
            ]
        }

    try:
        # Get or create draft
        draft = await get_draft_metadata(session_id)

        if draft is None:
            # Create new draft
            await save_draft_metadata(session_id, metadata)
            logger.info("Created new draft for session %s with fields: %s", session_id, list(metadata.keys()))
        else:
            # Merge with existing draft
            for field, value in metadata.items():
                existing = draft.get(f"{field}_json")
                if isinstance(existing, dict) and isinstance(value, dict):
                    # Deep merge dicts
                    merged = {**existing, **value}
                    await update_draft_metadata(session_id, field, merged)
                else:
                    await update_draft_metadata(session_id, field, value)
            logger.info("Updated draft for session %s with fields: %s", session_id, list(metadata.keys()))

        # Run validation after update.
        # get_draft_metadata returns keys like "subject_json"; the validator
        # expects bare keys like "subject", so strip the "_json" suffix.
        updated_draft = await get_draft_metadata(session_id)
        if updated_draft:
            bare_metadata = {
                k.replace("_json", ""): v
                for k, v in updated_draft.items()
                if k.endswith("_json") and k != "validation_results_json" and v is not None
            }
            validation_result = validate_metadata(bare_metadata)
            await update_draft_metadata(session_id, "validation_results", validation_result.to_dict())

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "status": "saved",
                            "session_id": session_id,
                            "fields_saved": list(metadata.keys()),
                            "message": f"Successfully saved {len(metadata)} metadata field(s)",
                        }
                    ),
                }
            ]
        }

    except Exception as e:
        logger.exception("Failed to save metadata for session %s", session_id)
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "status": "error",
                            "error": str(e),
                        }
                    ),
                }
            ]
        }


# Create the decorated tool that wraps the handler
@tool(
    "capture_metadata",
    """Save extracted metadata fields from the scientist's input.

Call this tool whenever you identify metadata from the conversation. You can call it
multiple times as more information is provided. Fields are merged with existing data.

The session_id must match the current conversation session.

Example call:
    capture_metadata(
        session_id="abc123",
        subject={"subject_id": "4528", "species": {"name": "Mus musculus"}},
        data_description={"modality": [{"name": "Planar optical physiology", "abbreviation": "pophys"}]}
    )
""",
    {
        "session_id": str,
        "subject": dict,
        "data_description": dict,
        "session": dict,
        "procedures": dict,
        "instrument": dict,
        "acquisition": dict,
        "processing": dict,
        "quality_control": dict,
        "rig": dict,
    },
)
async def capture_metadata(args: dict[str, Any]) -> dict[str, Any]:
    """MCP tool wrapper for capture_metadata_handler."""
    return await capture_metadata_handler(args)


# Create the MCP server
capture_server = create_sdk_mcp_server(
    name="capture",
    version="1.0.0",
    tools=[capture_metadata],
)
