"""Privacy helpers for flight-calendar-ics CLI output."""
from __future__ import annotations

import re


_REDACTION_PATTERNS: list[tuple[str, str]] = [
    (r"(?i)(pnrKey=)[^&\s]+", r"\1[REDACTED]"),
    (r"(?i)(pnr_key[\"'\s:=]+)[0-9a-f]{16,256}", r"\1[REDACTED]"),
    (r"(?i)(pnrLocator=)[^&\s]+", r"\1[REDACTED]"),
    (r"(?i)(pnr_locator[\"'\s:=]+)[A-Z0-9]{5,8}", r"\1[REDACTED]"),
    (r"(?i)(pnr=)[^&\s]+", r"\1[REDACTED]"),
    (r"(?i)(pnrNumber=)[^&\s]+", r"\1[REDACTED]"),
    (r"(?i)(lastName=)[^&\s]+", r"\1[REDACTED]"),
    (r"(?i)(rloc=)[^&\s]+", r"\1[REDACTED]"),
    (r"(?i)(last_name=)[^&\s]+", r"\1[REDACTED]"),
    (r"(?i)(filters(?:%5B|\[)locator(?:%5D|\])=)[^&\s]+", r"\1[REDACTED]"),
    (r"(?i)(filters(?:%5B|\[)passenger_lastname(?:%5D|\])=)[^&\s]+", r"\1[REDACTED]"),
    (r"(?i)(Authorization:\s*Bearer\s+)[^\s&]+", r"\1[REDACTED]"),
    (r"(?i)(#/find/)[^/\s]+/[^/\s]+(/Submit)", r"\1[REDACTED]/[REDACTED]\2"),
    (r"(?i)((?:access[-_ ]?key|access_code|finder_code)[\"'\s:=]+)[^\s&\"']+", r"\1[REDACTED]"),
    (r"(?i)([\"']secret[\"']\s*:\s*[\"'])[^\"']+([\"'])", r"\1[REDACTED]\2"),
    (r"(?i)(ticket=)\d{6,}", r"\1[REDACTED]"),
    (r"(?i)(ticket[_ -]?number[\"'\s:=]+)\d{6,}", r"\1[REDACTED]"),
    (r"\b\d{13}\b", "[REDACTED]"),
]


def redact(text: str) -> str:
    """Redact known booking credentials without trying to identify names."""
    out = text
    for pattern, repl in _REDACTION_PATTERNS:
        out = re.sub(pattern, repl, out)
    return out
