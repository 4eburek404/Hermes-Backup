"""Small error types for the compact flight-calendar-ics CLI."""
from __future__ import annotations

from typing import Any


class CliFailure(Exception):
    """Expected CLI failure that should become a short machine-readable error."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "validation_error",
        exit_code: int = 2,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code
        self.details = details or {}
