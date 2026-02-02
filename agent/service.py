"""Core agent service that wraps the Claude Code SDK for metadata capture."""

import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import (
    AssistantMessage,
    ResultMessage,
    StreamEvent,
)

from .prompts.system_prompt import SYSTEM_PROMPT
from .tools.capture_mcp import capture_server
from .tools.metadata_store import (
    confirm_metadata,
    get_conversation_history,
    get_draft_metadata,
    list_all_drafts,
    save_conversation_turn,
)

logger = logging.getLogger(__name__)

# Path to the AIND MCP server for schema context
MCP_SERVER_DIR = Path(__file__).resolve().parent.parent / "aind-metadata-mcp"


def _build_options() -> ClaudeAgentOptions:
    """Build the ClaudeAgentOptions for the metadata agent."""
    # MCP tool names are prefixed with "mcp__<server-name>__"
    aind_mcp_tools = [
        "mcp__aind-metadata-mcp__get_records",
        "mcp__aind-metadata-mcp__count_records",
        "mcp__aind-metadata-mcp__aggregation_retrieval",
        "mcp__aind-metadata-mcp__get_project_names",
        "mcp__aind-metadata-mcp__get_modality_types",
        "mcp__aind-metadata-mcp__get_subject_example",
        "mcp__aind-metadata-mcp__get_procedures_example",
        "mcp__aind-metadata-mcp__get_data_description_example",
        "mcp__aind-metadata-mcp__get_session_example",
        "mcp__aind-metadata-mcp__get_instrument_example",
        "mcp__aind-metadata-mcp__get_acquisition_example",
        "mcp__aind-metadata-mcp__get_processing_example",
        "mcp__aind-metadata-mcp__get_quality_control_example",
        "mcp__aind-metadata-mcp__get_rig_example",
        "mcp__aind-metadata-mcp__get_top_level_nodes",
        "mcp__aind-metadata-mcp__get_additional_schema_help",
        "mcp__aind-metadata-mcp__get_summary",
        "mcp__aind-metadata-mcp__flatten_records",
        "mcp__aind-metadata-mcp__identify_nwb_contents_in_code_ocean",
        "mcp__aind-metadata-mcp__identify_nwb_contents_with_s3_link",
    ]

    # Capture tool for metadata extraction
    capture_tool = "mcp__capture__capture_metadata"

    # Combine all MCP servers
    mcp_servers: dict[str, Any] = {
        "capture": capture_server,
    }

    # Add AIND MCP server if available
    mcp_config_path = MCP_SERVER_DIR / "mcp_config.json"
    if mcp_config_path.exists():
        import shutil

        mcp_command = shutil.which("aind-metadata-mcp") or "aind-metadata-mcp"
        logger.info("Registering AIND MCP server: %s", mcp_command)
        mcp_servers["aind-metadata-mcp"] = {
            "type": "stdio",
            "command": mcp_command,
        }

    opts = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        allowed_tools=["Bash", "Read", "Glob", "Grep", "WebFetch", "WebSearch", capture_tool] + aind_mcp_tools,
        max_turns=5,
        model="claude-opus-4-5-20251101",
        mcp_servers=mcp_servers,
        include_partial_messages=True,
    )

    return opts


def _format_conversation_context(history: list[dict[str, Any]], user_message: str) -> str:
    """Format conversation history + new message into a prompt string."""
    parts: list[str] = []

    if history:
        parts.append("Previous conversation:")
        for turn in history[-10:]:  # Keep last 10 turns for context
            role = turn["role"].upper()
            parts.append(f"{role}: {turn['content']}")
        parts.append("")

    parts.append(f"USER: {user_message}")
    return "\n".join(parts)


async def _create_message_stream(prompt: str):
    """Create an async generator for streaming input to the SDK.

    Custom MCP tools require streaming input mode.
    """
    yield {
        "type": "user",
        "message": {
            "role": "user",
            "content": prompt,
        },
    }


async def chat(session_id: str, user_message: str) -> AsyncIterator[dict[str, Any]]:
    """Process a chat message and stream the agent's response.

    Yields dicts with keys:
    - {"content": str} for text chunks
    - {"session_id": str} sent once at the start
    - {"done": True} when complete

    Parameters
    ----------
    session_id : str
        The session identifier for conversation tracking.
    user_message : str
        The user's message.
    """
    # Save the user's message
    await save_conversation_turn(session_id, "user", user_message)

    # Send session_id first
    yield {"session_id": session_id}

    # Build conversation context
    history = await get_conversation_history(session_id)
    # Exclude the message we just saved (it's the last one)
    prior_history = history[:-1] if history else []
    prompt = _format_conversation_context(prior_history, user_message)

    # Add context about current draft and session_id for the capture tool
    draft = await get_draft_metadata(session_id)
    if draft:
        draft_summary = {k: v for k, v in draft.items() if v is not None and k not in ("id", "created_at", "updated_at")}
        prompt += f"\n\nCurrent draft metadata for this session:\n{json.dumps(draft_summary, indent=2, default=str)}"

    # Add session_id context for the capture_metadata tool
    prompt += f"\n\nIMPORTANT: When calling capture_metadata, always use session_id=\"{session_id}\""

    # Run the agent with streaming input (required for custom MCP tools)
    options = _build_options()
    full_response: list[str] = []

    try:
        async for message in query(prompt=_create_message_stream(prompt), options=options):
            if isinstance(message, StreamEvent):
                event = message.event
                event_type = event.get("type")

                if event_type == "content_block_start":
                    block = event.get("content_block", {})
                    block_type = block.get("type")
                    if block_type == "thinking":
                        yield {"thinking_start": True}
                    elif block_type == "tool_use":
                        yield {"tool_use_start": {"name": block.get("name", ""), "id": block.get("id", "")}}

                elif event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    delta_type = delta.get("type")
                    if delta_type == "text_delta":
                        text = delta["text"]
                        full_response.append(text)
                        yield {"content": text}
                    elif delta_type == "thinking_delta":
                        yield {"thinking": delta.get("thinking", "")}
                    elif delta_type == "input_json_delta":
                        yield {"tool_use_input": delta.get("partial_json", "")}

                elif event_type == "content_block_stop":
                    yield {"block_stop": True}

            elif isinstance(message, AssistantMessage):
                # Complete message — skip since we already streamed deltas
                pass
            elif isinstance(message, ResultMessage):
                # Final result — the capture_metadata tool handles persistence
                pass
    except Exception as exc:
        logger.exception("Agent query failed for session %s: %s", session_id, exc)
        error_msg = "I encountered an error processing your request. Please try again."
        full_response.append(error_msg)
        yield {"content": error_msg}

    # Save the assistant's complete response
    assistant_text = "".join(full_response)
    if assistant_text.strip():
        await save_conversation_turn(session_id, "assistant", assistant_text)

    # Note: Metadata extraction now happens via the capture_metadata tool
    # which Claude calls directly during the conversation

    yield {"done": True}


async def get_session_messages(session_id: str) -> list[dict[str, Any]]:
    """Get conversation history for a session."""
    return await get_conversation_history(session_id)


async def get_all_drafts(status_filter: str | None = None) -> list[dict[str, Any]]:
    """List all draft metadata entries."""
    return await list_all_drafts(status_filter)


async def confirm_draft(session_id: str) -> dict[str, Any] | None:
    """Confirm the draft metadata for a session."""
    return await confirm_metadata(session_id)


async def get_sessions() -> list[dict[str, Any]]:
    """Get all sessions with their message counts."""
    from .db.database import get_db

    db = await get_db()
    cursor = await db.execute(
        """
        SELECT
            session_id,
            MIN(created_at) as created_at,
            MAX(created_at) as last_active,
            COUNT(*) as message_count,
            (
                SELECT content FROM conversations c2
                WHERE c2.session_id = conversations.session_id
                  AND c2.role = 'user'
                ORDER BY c2.created_at ASC
                LIMIT 1
            ) as first_message
        FROM conversations
        GROUP BY session_id
        ORDER BY MAX(created_at) DESC
        """
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]
