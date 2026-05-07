"""Memory sub-agent node — direct memory retrieval for the supervisor pattern.

Called by the orchestrator when the supervisor delegates a memory-related query.
Searches long-term memory directly (no extra LLM call needed for retrieval) and:

  1. Adds a ToolMessage to close the open ``transfer_to_memory_agent`` tool_call
     so that the message history remains valid for OpenAI-compatible models
     (every AIMessage with tool_calls must be followed by matching ToolMessages).
  2. Stores the retrieved snippets in ``state["memory_context"]`` so the
     supervisor can inject them into its system prompt on the second pass.
"""

import hashlib
import logging

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents.state import AxonState
from app.agents.supervisor import HANDOFF_TOOL_NAME
from app.features.memory import service

logger = logging.getLogger(__name__)


async def memory_agent_node(state: AxonState) -> dict:
    """Retrieve relevant memories and return them as state updates.

    Searches long-term memory for the user's last query, stores the results in
    ``memory_context``, and appends a ToolMessage that satisfies the open
    ``transfer_to_memory_agent`` tool_call emitted by the supervisor node.
    """
    # -- Determine search query from the last HumanMessage -----------------
    last_human = next(
        (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        None,
    )
    raw = last_human.content if last_human else ""
    query: str = (
        raw
        if isinstance(raw, str)
        else " ".join(p if isinstance(p, str) else (p.get("text") or "") for p in raw)
    )

    # -- Resolve the tool_call_id so the ToolMessage closes the loop -------
    tool_call_id: str | None = None
    last_msg = state["messages"][-1] if state["messages"] else None
    if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
        for tc in last_msg.tool_calls:
            if tc["name"] == HANDOFF_TOOL_NAME:
                tool_call_id = tc["id"]
                break

    # -- Search memory (direct service call, no LLM overhead) --------------
    try:
        results = await service.search_memories(
            user_id=state["user_id"],
            query=query,
            threshold=state.get("memory_threshold", 0.35),
            limit=state.get("memory_limit", 5),
        )
    except Exception:
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:8]
        logger.exception("memory_agent_node: search failed (query_hash=%s)", query_hash)
        results = []

    snippets = [r.content for r in results]

    # -- Build ToolMessage to keep message history valid -------------------
    messages: list[ToolMessage] = []
    if tool_call_id:
        content = "\n".join(snippets) if snippets else "No relevant memories found."
        messages.append(
            ToolMessage(
                content=content,
                tool_call_id=tool_call_id,
                name=HANDOFF_TOOL_NAME,
            )
        )

    return {"messages": messages, "memory_context": snippets}
