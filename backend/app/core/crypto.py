"""Symmetric encryption for memory content at rest.

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the `cryptography` library —
audited, simple API, sufficient for protecting personal memory entries.

The key is loaded once at module import; an invalid or missing key fails
fast at startup rather than at first encrypt call.
"""

import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger(__name__)


def _build_fernet() -> Fernet:
    try:
        return Fernet(settings.encryption_key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        # NEVER log the key itself (OWASP A09).
        raise RuntimeError(
            "ENCRYPTION_KEY is invalid — must be a urlsafe-base64 32-byte Fernet key. "
            "Generate one with: "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        ) from exc


_fernet: Fernet = _build_fernet()


def encrypt(plaintext: str) -> str:
    """Encrypt UTF-8 text. Returns urlsafe-base64 ciphertext suitable for TEXT columns."""
    return _fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    """Decrypt a Fernet token produced by `encrypt`. Raises on tampering or wrong key."""
    try:
        return _fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # Don't leak ciphertext to logs.
        logger.exception("Failed to decrypt memory entry — token invalid or key mismatch")
        raise
