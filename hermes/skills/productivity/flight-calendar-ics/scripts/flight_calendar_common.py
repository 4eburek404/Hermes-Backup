#!/usr/bin/env python3
"""Shared local helpers for flight-calendar-ics scripts.

This module owns cross-cutting helper logic that must stay identical across the
agent-facing CLI and direct compatibility helpers. It intentionally contains no
carrier-specific parsing, network access, or stdout/stderr behavior.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Any

FailureHandler = Callable[[str], Any]


def secure_write_text(path: Path, text: str, *, dir_mode: int = 0o700, file_mode: int = 0o600) -> None:
    """Write private skill artifacts with owner-only permissions."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=dir_mode)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, file_mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    finally:
        try:
            os.chmod(path, file_mode)
        except FileNotFoundError:
            pass


def parse_tz_overrides(items: list[str], *, fail: FailureHandler | None = None) -> dict[str, str]:
    """Parse repeated CODE=Area/City timezone overrides."""
    out: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            _reject_timezone_override(item, fail=fail)
        code, tzid = item.split("=", 1)
        code = code.strip().upper()
        tzid = tzid.strip()
        if not code or not tzid:
            _reject_timezone_override(item, fail=fail)
        out[code] = tzid
    return out


def _reject_timezone_override(item: str, *, fail: FailureHandler | None) -> None:
    message = f"bad --tz value {item!r}; use CODE=Area/City"
    if fail is not None:
        fail(message)
    raise ValueError(message)
