"""Small shared helpers."""

from __future__ import annotations

import re

_PHONE_RE = re.compile(r"^\+?[1-9]\d{6,14}$")
_PHONE_NOISE_RE = re.compile(r"[\s\-().]")
_SEARCH_NOISE_RE = re.compile(r"[,()*%\\]")


def normalize_phone(raw: str) -> str:
    """Normalize a phone number and raise ``ValueError`` when it is invalid.

    Accepts ``+91 98450 11223``, ``9845011223``, ``(98450)-11223`` ...
    """
    value = _PHONE_NOISE_RE.sub("", (raw or "").strip())
    if value.startswith("00"):
        value = "+" + value[2:]
    if not _PHONE_RE.match(value):
        raise ValueError(
            "Invalid phone number. Use 7-15 digits, optionally prefixed with '+'."
        )
    return value


def sanitize_search_term(raw: str) -> str:
    """Strip PostgREST filter control characters from a free-text search term."""
    return _SEARCH_NOISE_RE.sub("", raw).strip()


def first_or_none(rows: list[dict] | None) -> dict | None:
    return rows[0] if rows else None
