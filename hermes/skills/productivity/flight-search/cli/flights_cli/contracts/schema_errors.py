from __future__ import annotations

from typing import Any

from jsonschema.exceptions import ValidationError


def validation_error_detail(error: ValidationError) -> dict[str, Any]:
    path = "$"
    if error.absolute_path:
        path += "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.absolute_path)
    return {"path": path, "message": error.message, "validator": error.validator}
