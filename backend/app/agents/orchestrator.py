"""Orchestrator graph — supervisor pattern with memory and YouTube sub-agents.


    START → supervisor → (transfer_to_memory_agent called)  → memory_agent      → supervisor → END
                       → (transfer_to_youtube_agent called) → youtube_agent     → supervisor → END
                       → (save_video_transcript called)     → save_transcript   → supervisor → END
                       → (responds directly)                                   → END

- **supervisor**:        Entry point for every turn. Binds all handoff tools on the
                         first pass. On the second pass (after any sub-agent runs) it
                         uses a plain model (no tools), guaranteeing no re-delegation.

- **memory_agent**:      Searches long-term memory directly (no LLM) and adds a
                         ToolMessage + ``memory_context`` update to state.

- **youtube_agent**:     Fetches YouTube transcript + metadata, runs hierarchical LLM
                         summarization, and returns a ToolMessage with a JSON payload
                         + ``youtube_context`` update to state.

- **save_transcript**:   Reads ``youtube_context`` from state, persists the video
                         payload to ``video_transcripts``, and cross-indexes the
                         summary in ``memory_entries``.
"""

import logging

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langchain_core.messages import HumanMessage, ToolMessage

from app.agents.state import AxonState
from app.agents.subagents.memory_agent import memory_agent_node
from app.agents.subagents.youtube_agent import (
    YOUTUBE_HANDOFF_TOOL_NAME,
    youtube_agent_node,
)
from app.agents.supervisor import HANDOFF_TOOL_NAME, supervisor_node
from app.features.youtube.tool import SAVE_TRANSCRIPT_TOOL_NAME, save_transcript_node

logger = logging.getLogger(__name__)


def _should_continue(state: AxonState) -> str:
    """Route to the appropriate sub-agent or END after the supervisor runs.

    Scopes the ToolMessage check to the current turn (after the last
    HumanMessage) so historical ToolMessages from prior turns never block
    future sub-agent lookups.
    """
    messages = state["messages"]
    # Find the boundary of the current turn.
    last_human_idx = next(
        (
            i
            for i in range(len(messages) - 1, -1, -1)
            if isinstance(messages[i], HumanMessage)
        ),
        -1,
    )
    current_turn = messages[last_human_idx + 1 :]

    # If any sub-agent already ran this turn, stop — prevents re-delegation.
    if any(isinstance(m, ToolMessage) for m in current_turn):
        return END

    last = messages[-1]
    if getattr(last, "tool_calls", None):
        for tc in last.tool_calls:
            if tc["name"] == HANDOFF_TOOL_NAME:
                return "memory_agent"
            if tc["name"] == YOUTUBE_HANDOFF_TOOL_NAME:
                return "youtube_agent"
            if tc["name"] == SAVE_TRANSCRIPT_TOOL_NAME:
                return "save_transcript"
    return END


def _build_graph() -> CompiledStateGraph:
    """Build and compile the orchestrator graph with supervisor pattern."""
    builder = StateGraph(AxonState)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("memory_agent", memory_agent_node)
    builder.add_node("youtube_agent", youtube_agent_node)
    builder.add_node("save_transcript", save_transcript_node)
    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        _should_continue,
        {
            "memory_agent": "memory_agent",
            "youtube_agent": "youtube_agent",
            "save_transcript": "save_transcript",
            END: END,
        },
    )
    # All sub-agents loop back to supervisor for the final response.
    builder.add_edge("memory_agent", "supervisor")
    builder.add_edge("youtube_agent", "supervisor")
    builder.add_edge("save_transcript", "supervisor")
    return builder.compile()


# Compiled graph — exported singleton consumed by the chat service.
graph: CompiledStateGraph = _build_graph()
