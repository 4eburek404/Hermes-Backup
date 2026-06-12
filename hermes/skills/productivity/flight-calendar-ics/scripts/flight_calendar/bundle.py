"""Private output bundle helpers for flight-calendar-ics."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from flight_calendar import ics_render
from flight_calendar.envelope import CliFailure, add_step


BUNDLE_ITINERARY_NAME = "itinerary.json"
BUNDLE_ICS_NAME = "flights.ics"
BUNDLE_ENVELOPE_NAME = "envelope.json"


def create_private_output_dir(output_dir: Path | None, process: list[dict[str, Any]]) -> Path:
    if output_dir is None:
        path = Path(tempfile.mkdtemp(prefix="flight-ics."))
    else:
        path = output_dir
        if path.exists() and not path.is_dir():
            raise CliFailure(f"output dir path exists and is not a directory: {path}", code="usage_error")
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    add_step(process, "create_output_bundle")
    return path


def bundle_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "json": output_dir / BUNDLE_ITINERARY_NAME,
        "ics": output_dir / BUNDLE_ICS_NAME,
        "envelope": output_dir / BUNDLE_ENVELOPE_NAME,
    }


def file_mode(path: Path) -> str:
    return format(path.stat().st_mode & 0o777, "03o")


def require_private_mode(path: Path, expected: str = "600") -> None:
    try:
        mode = file_mode(path)
    except FileNotFoundError as exc:
        raise CliFailure(f"expected artifact does not exist: {path}") from exc
    if mode != expected:
        raise CliFailure(f"artifact {path} has mode {mode}; expected {expected}")


def verify_bundle_artifacts(paths: dict[str, Path], segments_count: int, process: list[dict[str, Any]]) -> dict[str, Any]:
    require_private_mode(paths["json"])
    require_private_mode(paths["ics"])
    ics_text = paths["ics"].read_text(encoding="utf-8")
    ics_render.validate_ics_text(ics_text, segments_count)
    event_count = ics_text.count("BEGIN:VEVENT")
    dt_lines = [line for line in ics_text.splitlines() if line.startswith(("DTSTART", "DTEND"))]
    non_utc = [line for line in dt_lines if not line.endswith("Z")]
    if non_utc:
        raise CliFailure("generated ICS contains DTSTART/DTEND values without UTC Z suffix")
    add_step(process, "verify_bundle", segments_count=segments_count)
    return {
        "ok": True,
        "event_count": event_count,
        "utc_datetime_count": len(dt_lines),
        "placeholder_free": True,
        "private_modes": {"json": file_mode(paths["json"]), "ics": file_mode(paths["ics"])},
    }
