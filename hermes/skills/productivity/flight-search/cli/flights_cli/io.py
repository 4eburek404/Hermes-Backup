from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .errors import CliError


class _DuplicateJsonKey(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _reject_non_finite(value: str) -> None:
    raise ValueError(f"non-finite JSON number {value}")


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
        return json.loads(
            read_input_text(path),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite,
        )
    except _DuplicateJsonKey as exc:
        source = "stdin" if path == "-" else path
        raise CliError(
            f"duplicate JSON key in {source}: {exc}",
            error_type="validation_error",
        ) from exc
    except json.JSONDecodeError as exc:
        source = "stdin" if path == "-" else path
        raise CliError(
            f"invalid JSON in {source}: {exc.msg}", error_type="validation_error"
        ) from exc
    except ValueError as exc:
        source = "stdin" if path == "-" else path
        raise CliError(
            f"invalid JSON in {source}: {exc}", error_type="validation_error"
        ) from exc


def read_json_object(path: str) -> dict[str, Any]:
    payload = read_json_input(path)
    if not isinstance(payload, dict):
        raise CliError("JSON input must be an object", error_type="validation_error")
    return payload
