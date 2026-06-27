from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .errors import CliError


def read_input_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    source = Path(path).expanduser()
    try:
        return source.read_text(encoding="utf-8")
    except OSError as exc:
        raise CliError(
            f"could not read JSON input {path!r}: {exc}", error_type="not_found"
        ) from exc


def read_json_input(path: str) -> Any:
    try:
        return json.loads(read_input_text(path))
    except json.JSONDecodeError as exc:
        source = "stdin" if path == "-" else path
        raise CliError(
            f"invalid JSON in {source}: {exc.msg}", error_type="validation_error"
        ) from exc


def read_json_object(path: str) -> dict[str, Any]:
    payload = read_json_input(path)
    if not isinstance(payload, dict):
        raise CliError("JSON input must be an object", error_type="validation_error")
    return payload
