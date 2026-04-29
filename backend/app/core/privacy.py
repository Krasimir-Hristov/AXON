"""PII masking using Microsoft Presidio.

The Presidio AnalyzerEngine is a heavy CPU-bound NLP pipeline (loads spaCy
en_core_web_sm). We construct ONE singleton at first use and dispatch every
call through `asyncio.to_thread` so the FastAPI event loop is never blocked.

Public API:
    await mask_pii(text) -> str
"""

import asyncio
import logging
from threading import Lock

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

logger = logging.getLogger(__name__)

# Entities we mask. Keep this conservative — over-masking destroys semantic
# meaning needed for embeddings to remain useful.
_ENTITIES: list[str] = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "IBAN_CODE",
    "IP_ADDRESS",
    "LOCATION",
    "US_SSN",
]

_analyzer: AnalyzerEngine | None = None
_anonymizer: AnonymizerEngine | None = None
_init_lock = Lock()


def _get_engines() -> tuple[AnalyzerEngine, AnonymizerEngine]:
    """Lazy thread-safe init of Presidio engines (sync — called inside to_thread)."""
    global _analyzer, _anonymizer  # noqa: PLW0603 — intentional module-level singleton
    if _analyzer is not None and _anonymizer is not None:
        return _analyzer, _anonymizer
    with _init_lock:
        if _analyzer is None or _anonymizer is None:
            logger.info("Initialising Presidio engines (loads spaCy en_core_web_sm)")
            _analyzer = AnalyzerEngine()
            _anonymizer = AnonymizerEngine()
        return _analyzer, _anonymizer


def _mask_sync(text: str) -> str:
    analyzer, anonymizer = _get_engines()
    results = analyzer.analyze(text=text, entities=_ENTITIES, language="en")
    if not results:
        return text
    anonymized = anonymizer.anonymize(text=text, analyzer_results=results)
    return anonymized.text


async def mask_pii(text: str) -> str:
    """Replace detected PII with placeholders like <PERSON>, <EMAIL_ADDRESS>.

    Offloaded to a worker thread so the event loop stays responsive — Presidio
    is sync CPU-bound (~50-200ms per call after the first).
    """
    if not text:
        return text
    return await asyncio.to_thread(_mask_sync, text)
