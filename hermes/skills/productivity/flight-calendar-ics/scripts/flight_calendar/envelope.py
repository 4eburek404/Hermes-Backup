"""JSON envelope helpers for the flight-calendar-ics CLI."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from flight_calendar.contracts import SCHEMA_VERSION
from flight_calendar.common import secure_write_text


class CliFailure(Exception):
    """Expected CLI failure that should become a machine-readable error."""

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


def add_step(process: list[dict[str, Any]], step: str, status: str = "ok", **data: Any) -> None:
    item: dict[str, Any] = {"step": step, "status": status}
    if data:
        item.update(data)
    process.append(item)


def envelope(
    *,
    ok: bool,
    command: str,
    process: list[dict[str, Any]],
    data: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    obj: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "command": command,
        "process": process,
    }
    if ok:
        obj["data"] = data or {}
    else:
        obj["error"] = error or {"code": "unknown_error", "message": "unknown error"}
    return obj


def emit_json(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def emit_human(obj: dict[str, Any]) -> None:
    if obj["ok"]:
        data = obj.get("data") or {}
        print(f"OK: {obj['command']}")
        if "segments_count" in data:
            print(f"segments: {data['segments_count']}")
        if data.get("ics_path"):
            print(f"ics: {data['ics_path']}")
        if data.get("json_path"):
            print(f"json: {data['json_path']}")
    else:
        err = obj.get("error") or {}
        print(f"ERROR: {err.get('message', 'unknown error')}", file=sys.stderr)


def write_envelope_artifact_if_requested(data: dict[str, Any], obj: dict[str, Any]) -> None:
    envelope_path = data.get("envelope_path")
    if envelope_path:
        secure_write_text(Path(envelope_path), json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
