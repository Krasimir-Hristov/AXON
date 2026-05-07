"""AxonState — single source of truth for graph state shared across all nodes."""

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AxonState(TypedDict):
    """State container for the AXON LangGraph orchestrator.

    Fields:
        messages: Conversation history. The `add_messages` reducer appends
            new messages returned by each node instead of overwriting the list.
        user_id: Authenticated Supabase user UUID — derived from the validated
            JWT, never trusted from request payload.
        model_id: OpenRouter model identifier requested by the client. Reserved
            for per-request model switching in a later phase; currently the
            orchestrator uses settings.llm_model.
        memory_context: Snippets retrieved from long-term memory (Phase 5+).
            Kept as an empty list for now to avoid TypedDict churn later.
    """

    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    model_id: str
    memory_context: list[str]
    memory_threshold: float
    memory_limit: int
