from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .errors import CliError

def read_input_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise CliError(f"could not read {path}: {exc}", error_type="io_error") from exc


def read_json_file(path: str) -> Any:
    try:
        return json.loads(read_input_text(path))
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid JSON input {path}: {exc}", error_type="validation_error") from exc
