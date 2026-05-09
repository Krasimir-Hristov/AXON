"""YouTube LLM summarization: Pydantic schemas, chunk summaries, final summary.

All LLM output is validated through Pydantic models (YouTubeSummaryPayload,
YouTubeVideoPayload) to prevent malformed data from being persisted to state.
"""

import asyncio
import json
import logging
import re
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from app.core.config import settings

logger = logging.getLogger(__name__)

_MAX_CONCURRENT_SUMMARIES = 5

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_CHUNK_SUMMARY_SYSTEM = "You are a precise, concise summarizer."

_CHUNK_SUMMARY_USER = """\
Summarize the following section of a video transcript in 3-5 concise sentences.
Focus on key ideas, facts, and takeaways. Do NOT include filler phrases like
"This section discusses" — go straight to the content.

TRANSCRIPT SECTION:
{chunk}
"""

_FINAL_SUMMARY_USER = """\
You are creating a final summary of a YouTube video titled "{title}" by "{channel}".
Below are summaries of each transcript section.

Produce:
1. A concise overall summary (3-6 sentences) covering the main thesis and key takeaways.
2. A list of 5-8 key points (the most important ideas, facts, or conclusions).

Respond ONLY with valid JSON — no markdown fences, no extra text:
{{"summary": "...", "key_points": ["...", "...", "..."]}}

SECTION SUMMARIES:
{section_summaries}
"""

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class YouTubeSummaryPayload(BaseModel):
    """Validated schema for the LLM-generated summary fields.

    Ensures key_points is always list[str] — prevents a string value being
    turned into a char list by list(), which raw json.loads + list() would allow.
    """

    summary: str
    key_points: list[str]


class YouTubeVideoPayload(BaseModel):
    """Complete validated payload persisted to youtube_context state.

    Used in youtube_agent_node to guarantee the full JSON blob written to state
    conforms to the expected shape before serialization.
    """

    video_id: str
    youtube_url: str
    title: str
    channel: str
    duration_s: int
    summary: str
    key_points: list[str]


# ---------------------------------------------------------------------------
# Model singleton (lazy init, non-streaming)
# ---------------------------------------------------------------------------

_summary_model: Any = None


def _get_summary_model() -> Any:
    """Return (or build) the cached non-streaming summarization model."""
    global _summary_model
    if _summary_model is None:
        _summary_model = init_chat_model(
            settings.youtube_summary_model,
            model_provider="openai",
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            streaming=False,
        )
    return _summary_model


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _strip_fences(content: str) -> str:
    """Remove markdown code fences that some models wrap around JSON output."""
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```[a-z]*\n?", "", content)
        content = re.sub(r"\n?```$", "", content.strip())
    return content


# ---------------------------------------------------------------------------
# Public summarization functions
# ---------------------------------------------------------------------------


async def summarize_chunks(chunks: list[str]) -> list[str]:
    """Summarize each chunk with concurrency-limited parallel LLM calls."""
    model = _get_summary_model()
    sem = asyncio.Semaphore(_MAX_CONCURRENT_SUMMARIES)

    async def _one(chunk: str, idx: int) -> str:
        async with sem:
            try:
                resp = await model.ainvoke(
                    [
                        SystemMessage(content=_CHUNK_SUMMARY_SYSTEM),
                        HumanMessage(content=_CHUNK_SUMMARY_USER.format(chunk=chunk)),
                    ]
                )
                content = resp.content if isinstance(resp.content, str) else str(resp.content)
                logger.debug("[youtube_summarizer] chunk %d summarized (%d chars)", idx, len(content))
                return content
            except Exception:
                logger.exception("[youtube_summarizer] chunk %d summarization failed", idx)
                return ""

    results = await asyncio.gather(*[_one(c, i) for i, c in enumerate(chunks)])
    return [r for r in results if r]


async def build_final_summary(
    chunk_summaries: list[str],
    title: str,
    channel: str,
) -> tuple[str, list[str]]:
    """Combine chunk summaries into a validated (summary, key_points) via one LLM call.

    Validates the LLM JSON response through YouTubeSummaryPayload to guarantee
    key_points is always list[str] and summary is always str. Falls back to the
    first three raw chunk summaries on ValidationError or JSON parse failure so
    a corrupted LLM response is never persisted to state.
    """
    model = _get_summary_model()
    section_text = "\n\n".join(
        f"Section {i + 1}:\n{s}" for i, s in enumerate(chunk_summaries)
    )
    prompt = _FINAL_SUMMARY_USER.format(
        title=title,
        channel=channel,
        section_summaries=section_text,
    )
    try:
        resp = await model.ainvoke(
            [
                SystemMessage(content="You are a precise summarizer. Always respond with valid JSON only."),
                HumanMessage(content=prompt),
            ]
        )
        content = resp.content if isinstance(resp.content, str) else str(resp.content)
        content = _strip_fences(content)
        validated = YouTubeSummaryPayload.model_validate(json.loads(content))
        return validated.summary, validated.key_points
    except (ValidationError, json.JSONDecodeError):
        logger.exception("[youtube_summarizer] final summary validation/parse failed — falling back")
        return " ".join(chunk_summaries[:3]), []
    except Exception:
        logger.exception("[youtube_summarizer] final summary LLM call failed — falling back")
        return " ".join(chunk_summaries[:3]), []
