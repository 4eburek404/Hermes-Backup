#!/usr/bin/env python3
"""Download and atomically update the bundled airport timezone snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from flight_calendar.timezone_catalog import CATALOG_PATH
from flight_calendar.timezone_catalog_source import (
    CANONICAL_SOURCE_URL,
    CatalogUpdateFailure,
    atomic_write_bytes,
    build_catalog_document,
    fetch_source,
    serialize_catalog,
)

SOURCE_URLS = (CANONICAL_SOURCE_URL,)


def _current_timezones(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    timezones = data.get("timezones") if isinstance(data, dict) else None
    return dict(timezones) if isinstance(timezones, dict) else {}


def _diff_counts(old: dict[str, str], new: dict[str, str]) -> dict[str, int]:
    old_codes = set(old)
    new_codes = set(new)
    return {
        "added": len(new_codes - old_codes),
        "removed": len(old_codes - new_codes),
        "timezone_changed": sum(
            old[code] != new[code] for code in old_codes & new_codes
        ),
    }


def _build_candidate(work_dir: Path) -> tuple[dict[str, Any], dict[str, str]]:
    raw = fetch_source(CANONICAL_SOURCE_URL)
    raw_path = work_dir / "source-en.json"
    raw_path.write_bytes(raw)
    document = build_catalog_document(raw, url=CANONICAL_SOURCE_URL)
    return document, {CANONICAL_SOURCE_URL: hashlib.sha256(raw).hexdigest()}


def update_catalog(output_path: Path) -> dict[str, Any]:
    old_bytes = output_path.read_bytes() if output_path.exists() else None
    old_timezones = _current_timezones(output_path)

    with tempfile.TemporaryDirectory(prefix="flight-calendar-airports.") as tmp:
        document, source_hashes = _build_candidate(Path(tmp))
    candidate_bytes = serialize_catalog(document)
    changed = old_bytes != candidate_bytes
    counts = _diff_counts(old_timezones, document["timezones"])
    if changed:
        atomic_write_bytes(output_path, candidate_bytes)

    return {
        "ok": True,
        "changed": changed,
        "timezone_count": len(document["timezones"]),
        "source_hashes": source_hashes,
        **counts,
    }


def _error_result(exc: Exception) -> dict[str, Any]:
    return {"ok": False, "changed": False, "error": {"message": str(exc)}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Update the bundled flight-calendar-ics airport timezone snapshot."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=CATALOG_PATH,
        help="Output airport-timezones.json path",
    )
    args = parser.parse_args(argv)
    try:
        result = update_catalog(args.output)
    except (OSError, CatalogUpdateFailure) as exc:
        result = _error_result(exc)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
