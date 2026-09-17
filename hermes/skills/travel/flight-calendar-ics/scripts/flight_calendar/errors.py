"""Small error types for the compact flight-calendar-ics CLI."""

from __future__ import annotations



class CliFailure(Exception):
    """Expected CLI failure that should become a short machine-readable error."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
    ) -> None:
        super().__init__(message)
        self.code = code
