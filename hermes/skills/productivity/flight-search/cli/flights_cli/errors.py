from __future__ import annotations

from typing import Any

class CliError(Exception):
    def __init__(self, message: str, *, error_type: str = "error", details: Any = None):
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.details = details
