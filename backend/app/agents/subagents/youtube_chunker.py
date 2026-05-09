"""YouTube transcript chunking: group transcript entries into fixed-size text chunks."""

from typing import Any

# ~4 chars per token — rough but reliable estimate for mixed-language transcripts.
_CHARS_PER_TOKEN = 4
_CHUNK_SIZE_CHARS = 4_000 * _CHARS_PER_TOKEN  # ≈16 000 chars per chunk


def build_chunks(transcript: list[dict[str, Any]]) -> list[str]:
    """Group transcript entries into text chunks of at most _CHUNK_SIZE_CHARS characters."""
    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for entry in transcript:
        text = entry.get("text", "").strip()
        if not text:
            continue
        if current_len + len(text) > _CHUNK_SIZE_CHARS and current_parts:
            chunks.append(" ".join(current_parts))
            current_parts = []
            current_len = 0
        current_parts.append(text)
        current_len += len(text) + 1

    if current_parts:
        chunks.append(" ".join(current_parts))

    return chunks
