"""Pure, bounded redaction for diagnostic text only."""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

_DIAGNOSTIC_TEXT_LIMIT = 240
_URL_RE = re.compile(r"(?:https?:)?//[^\s\"'<>]+", re.IGNORECASE)


def redact_url(url: str) -> str:
    """Remove query material from a pstatic CDN URL without changing other URLs."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    host = parts.hostname
    if host is None or (host != "pstatic.net" and not host.endswith(".pstatic.net")):
        return url
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))


def redact_text(value: str, *, max_length: int = _DIAGNOSTIC_TEXT_LIMIT) -> str:
    """Bound free diagnostic text while retaining a useful prefix."""
    if max_length < 1:
        raise ValueError("max_length must be positive")
    if len(value) <= max_length:
        return value
    return value[: max_length - 1] + "…"


def redact_diagnostic(value: object, *, max_length: int = _DIAGNOSTIC_TEXT_LIMIT) -> str:
    """Strip pstatic signing queries and bound an unstructured diagnostic value."""
    text = str(value)
    return redact_text(
        _URL_RE.sub(lambda match: redact_url(match.group(0)), text), max_length=max_length
    )
