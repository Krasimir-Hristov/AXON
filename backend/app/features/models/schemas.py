"""Models feature schemas — public ModelInfo and internal OpenRouter response parsing."""

from pydantic import BaseModel, Field


class ModelInfo(BaseModel):
    """Public schema returned by GET /api/v1/models."""

    id: str  # "openai/gpt-4o" — unique OpenRouter model identifier
    name: str  # "GPT-4o" — human-readable name for the UI
    provider: str  # "openai" — extracted from the id prefix before "/"
    context_length: int  # 128000 — maximum tokens in the model's context window
    category: str  # "Text", "Vision", "Image Generation", "Speech-to-Text", "Audio"


class _RawArchitecture(BaseModel):
    """Inner architecture object from OpenRouter model response."""

    # e.g. "text->text", "text+image->text", "text->image", "audio->text", "text->audio"
    modality: str = "text->text"


def _modality_to_category(modality: str) -> str:
    """Map an OpenRouter architecture.modality string to a UI category label."""
    if "->" not in modality:
        return "Text"
    inputs_raw, _, outputs_raw = modality.partition("->")
    inputs = set(inputs_raw.split("+"))
    outputs = set(outputs_raw.split("+"))
    if "audio" in outputs:
        return "Audio"
    if "image" in outputs:
        return "Image Generation"
    if "audio" in inputs:
        return "Speech-to-Text"
    if "image" in inputs:
        return "Vision"
    return "Text"


class _RawOpenRouterModel(BaseModel):
    """Internal parse schema — only the fields from OpenRouter response we need.

    Pydantic v2 ignores extra fields by default, so the 50+ other OpenRouter
    fields are silently discarded without needing explicit configuration.
    """

    id: str
    name: str
    # OpenRouter occasionally omits context_length for newer models; default to 0.
    context_length: int = 0
    architecture: _RawArchitecture = Field(default_factory=_RawArchitecture)


class _RawOpenRouterResponse(BaseModel):
    """Internal parse schema — outer envelope from OpenRouter GET /models."""

    # Empty list default: safe if OpenRouter returns an empty or malformed body.
    data: list[_RawOpenRouterModel] = Field(default_factory=list)
