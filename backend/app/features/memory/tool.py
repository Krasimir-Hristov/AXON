"""LangGraph tool — semantic search over the user's long-term memory.

Exposes `search_memory(query)` to the orchestrator. The user_id is read from
graph state via `ToolRuntime` so the LLM cannot spoof it through the tool args.
"""

import logging

from langchain.tools import ToolRuntime, tool

from app.features.memory import service

logger = logging.getLogger(__name__)


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
        logger.exception("search_memory failed for user %s", user_id)
        return "Memory search temporarily unavailable."

    if not results:
        return "No relevant memories found."

    return "\n".join(f"- {r.content}" for r in results)
