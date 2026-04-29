"""LangGraph tool — semantic search over the user's long-term memory.

Exposes `search_memory(query)` to the orchestrator. The user_id is read from
graph state via `ToolRuntime` so the LLM cannot spoof it through the tool args.
"""

import hashlib
import logging

from langchain.tools import ToolRuntime, tool

from app.features.memory import service

logger = logging.getLogger(__name__)


def _redact_user_id(user_id: str) -> str:
    """Return a short, non-reversible identifier suitable for log lines.

    Supabase user IDs are UUIDs, which are arguably PII when correlated with
    other tables. We log a truncated SHA-256 instead — still useful for
    grouping log entries from the same user when debugging, but cannot be
    joined back to a specific account from logs alone.
    """
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]


@tool
async def search_memory(query: str, runtime: ToolRuntime) -> str:
    """Search the user's long-term memory for facts and context relevant to `query`.

    Use this when the user references something personal, prior preferences,
    files they uploaded, or details that may have been stored earlier. Returns
    a newline-separated list of relevant memory snippets, or a message saying
    nothing was found.
    """
    user_id = runtime.state.get("user_id")
    if not user_id:
        logger.error("search_memory invoked without user_id in state")
        return "Memory unavailable for this session."

    try:
        results = await service.search_memories(
            user_id=user_id,
            query=query,
            threshold=0.6,
            limit=5,
        )
    except Exception:  # noqa: BLE001 — never let tool errors bubble into the LLM as a 500
        logger.exception(
            "search_memory failed (user_hash=%s)", _redact_user_id(user_id)
        )
        return "Memory search temporarily unavailable."

    if not results:
        return "No relevant memories found."

    # Trim each snippet so a few large file chunks can't blow past the model's
    # context window (search returns up to 5 results × potentially several
    # thousand chars each from uploaded files).
    _SNIPPET_MAX = 500
    lines: list[str] = []
    for r in results:
        snippet = r.content[:_SNIPPET_MAX]
        if len(r.content) > _SNIPPET_MAX:
            snippet += "…"
        lines.append(f"- {snippet}")
    return "\n".join(lines)
