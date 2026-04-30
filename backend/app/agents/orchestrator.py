"""Orchestrator graph — supervisor pattern with memory specialist sub-agent.


    START → supervisor → (transfer_to_memory_agent called) → memory_agent → supervisor → END
                       → (responds directly)                              → END

- **supervisor**:     Entry point for every turn. Binds ``transfer_to_memory_agent``
                      on the first pass to let the LLM signal a memory lookup. On
                      the second pass (after memory_agent runs) it uses a plain model
                      (no tools) with the retrieved context injected as a system
                      message, guaranteeing no re-delegation loop.

- **memory_agent**:   Searches long-term memory directly (no extra LLM call) and
                      adds a ToolMessage + ``memory_context`` update to state.
"""

import logging

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langchain_core.messages import HumanMessage, ToolMessage

from app.agents.state import AxonState
from app.agents.subagents.memory_agent import memory_agent_node
from app.agents.supervisor import HANDOFF_TOOL_NAME, supervisor_node

logger = logging.getLogger(__name__)


def _should_continue(state: AxonState) -> str:
    """Route to memory_agent if the supervisor called the handoff tool, else stop.

    Only inspects messages from the *current* turn (after the last HumanMessage)
    so that ToolMessages from previous turns don't block future memory lookups.
    """
    messages = state["messages"]
    # Scope to the current turn: find the last HumanMessage index.
    last_human_idx = next(
        (i for i in range(len(messages) - 1, -1, -1) if isinstance(messages[i], HumanMessage)),
        -1,
    )
    current_turn = messages[last_human_idx + 1:]

    # If memory_agent already ran this turn, stop to prevent re-delegation.
    if any(isinstance(m, ToolMessage) for m in current_turn):
        return END

    last = messages[-1]
    if getattr(last, "tool_calls", None):
        for tc in last.tool_calls:
            if tc["name"] == HANDOFF_TOOL_NAME:
                return "memory_agent"
    return END


def _build_graph() -> CompiledStateGraph:
    """Build and compile the orchestrator graph with supervisor pattern."""
    builder = StateGraph(AxonState)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("memory_agent", memory_agent_node)
    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        _should_continue,
        {"memory_agent": "memory_agent", END: END},
    )
    # After memory_agent finishes, return to supervisor for the final response.
    builder.add_edge("memory_agent", "supervisor")
    return builder.compile()


# Compiled graph — exported singleton consumed by the chat service.
graph: CompiledStateGraph = _build_graph()
