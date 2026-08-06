"""Security helpers for user-facing error payloads."""

from __future__ import annotations

import re
from collections.abc import Sequence

_RED_ACTIONS: Sequence[tuple[str, str]] = (
    (r"\b(api[_-]?key|secret|token|password|credential|auth|authorization)=[^\s,;\"']+", "[REDACTED]"),
    (r"(?i)(/Users/[^\s'\"]+)", "[PATH_REDACTED]"),
    (r"(?i)(/home/[^\s'\"]+)", "[PATH_REDACTED]"),
)


def sanitize_error_message(message: object, *, max_length: int = 240) -> str:
    """Return a short user-safe message without leaking secrets or secrets-like values."""

    text = str(message).strip()
    if not text:
        return "operation failed"

    safe = text
    for pattern, replacement in _RED_ACTIONS:
        safe = re.sub(pattern, replacement, safe)

    if len(safe) <= max_length:
        return safe

    return safe[: max_length - 3].rstrip() + "..."


def user_facing_exception_message(error: BaseException | str | object) -> str:
    """Normalize exception detail for public API responses or logs shown to users."""

    return sanitize_error_message(error)
