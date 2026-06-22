"""Private output bundle helpers for flight-calendar-ics."""
from __future__ import annotations

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
        path.mkdir(parents=True, exist_ok=True)
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


def require_readable_mode(path: Path) -> None:
    try:
        mode = file_mode(path)
    except FileNotFoundError as exc:
        raise CliFailure(f"expected artifact does not exist: {path}") from exc
    if not (int(mode, 8) & 0o444):
        raise CliFailure(f"artifact {path} has mode {mode}; not readable")


def _extract_vevent_blocks(ics_text: str) -> list[str]:
    """Extract text content within each VEVENT block."""
    blocks: list[str] = []
    in_vevent = False
    current: list[str] = []
    for line in ics_text.splitlines():
        if line.strip() == "BEGIN:VEVENT":
            in_vevent = True
            current = [line]
        elif line.strip() == "END:VEVENT" and in_vevent:
            current.append(line)
            blocks.append("\n".join(current))
            in_vevent = False
            current = []
        elif in_vevent:
            current.append(line)
    return blocks


def verify_bundle_artifacts(paths: dict[str, Path], segments_count: int, process: list[dict[str, Any]]) -> dict[str, Any]:
    require_readable_mode(paths["json"])
    require_readable_mode(paths["ics"])
    ics_text = paths["ics"].read_text(encoding="utf-8")
    ics_render.validate_ics_text(ics_text, segments_count)
    event_count = ics_text.count("BEGIN:VEVENT")
    # Verify DTSTART/DTEND only inside VEVENT blocks. Flight events must use
    # absolute UTC timestamps; floating or TZID-qualified local times are not
    # allowed because clients disagree on how to resolve them.
    vevent_blocks = _extract_vevent_blocks(ics_text)
    bad_lines: list[str] = []
    for block in vevent_blocks:
        for line in block.splitlines():
            if line.startswith(("DTSTART", "DTEND")):
                if not (line.startswith(("DTSTART:", "DTEND:")) and line.endswith("Z")):
                    bad_lines.append(line)
    if bad_lines:
        raise CliFailure(f"generated ICS VEVENT DTSTART/DTEND lines must be absolute UTC Z timestamps: {bad_lines[:3]}")
    add_step(process, "verify_bundle", segments_count=segments_count)
    return {
        "ok": True,
        "event_count": event_count,
        "vevent_dt_count": sum(
            sum(1 for line in block.splitlines() if line.startswith(("DTSTART", "DTEND")))
            for block in vevent_blocks
        ),
        "placeholder_free": True,
        "private_modes": {"json": file_mode(paths["json"]), "ics": file_mode(paths["ics"])},
    }
