#!/usr/bin/env python3
"""Download and atomically update the bundled airport timezone catalog."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flight_calendar.timezone_catalog import CATALOG_PATH, SCHEMA_VERSION

SOURCE_URLS = (
    "https://api.travelpayouts.com/data/en/airports.json",
    "https://api.travelpayouts.com/data/ru/airports.json",
    "https://api.travelpayouts.com/data/airports.json",
)
IATA_RE = re.compile(r"^[A-Z0-9]{3}$")
SOURCE_DESCRIPTION = (
    "Compact derived airport catalog; only code -> time_zone is retained."
)


class UpdateFailure(ValueError):
    """A download or candidate validation failure."""


def _normalize_code(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_timezone(value: Any) -> str:
    return str(value or "").strip()


def _looks_like_iata_timezone(code: str, timezone: str) -> bool:
    return bool(
        IATA_RE.fullmatch(code) and "/" in timezone and not timezone.startswith("/")
    )


def _fetch_source(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Hermes flight-calendar-ics airport catalog updater/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise UpdateFailure(f"{url} returned HTTP {status}")
            return response.read()
    except UpdateFailure:
        raise
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        raise UpdateFailure(f"download failed for {url}: {type(exc).__name__}") from exc


def _read_upstream_array(path: Path, url: str) -> list[Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateFailure(f"invalid JSON from {url}: {type(exc).__name__}") from exc
    if not isinstance(data, list):
        raise UpdateFailure(f"upstream root from {url} must be a JSON array")
    return data


def _extract_timezones(
    records: list[Any], *, url: str
) -> tuple[dict[str, str], int]:
    timezones: dict[str, str] = {}
    updates = 0
    for index, item in enumerate(records):
        if not isinstance(item, dict):
            continue
        code = _normalize_code(item.get("code"))
        timezone = _normalize_timezone(
            item.get("time_zone") or item.get("timezone")
        )
        if not code or not timezone or not IATA_RE.fullmatch(code):
            continue
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise UpdateFailure(
                f"{url} record {index} has unknown IANA timezone {timezone!r}"
            ) from exc
        if _looks_like_iata_timezone(code, timezone):
            if timezones.get(code) != timezone:
                updates += 1
            timezones[code] = timezone
    return timezones, updates


def _validate_candidate(document: dict[str, Any]) -> None:
    if document.get("schema_version") != SCHEMA_VERSION:
        raise UpdateFailure("candidate has unsupported schema_version")
    timezones = document.get("timezones")
    if not isinstance(timezones, dict):
        raise UpdateFailure("candidate has no timezones object")
    for code, timezone in timezones.items():
        if not isinstance(code, str) or not IATA_RE.fullmatch(code):
            raise UpdateFailure(f"candidate has invalid airport code {code!r}")
        if not isinstance(timezone, str):
            raise UpdateFailure(f"candidate has non-string timezone for {code}")
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise UpdateFailure(
                f"candidate has unknown IANA timezone {timezone!r} for {code}"
            ) from exc


def _build_candidate(work_dir: Path) -> tuple[dict[str, Any], dict[str, str]]:
    timezones: dict[str, str] = {}
    source_files: list[dict[str, Any]] = []
    source_hashes: dict[str, str] = {}

    for index, url in enumerate(SOURCE_URLS):
        raw_path = work_dir / f"source-{index}.json"
        raw = _fetch_source(url)
        raw_path.write_bytes(raw)
        source_hashes[url] = hashlib.sha256(raw).hexdigest()

    for index, url in enumerate(SOURCE_URLS):
        raw_path = work_dir / f"source-{index}.json"
        records = _read_upstream_array(raw_path, url)
        extracted, updates = _extract_timezones(records, url=url)
        for code, timezone in extracted.items():
            timezones[code] = timezone
        source_files.append(
            {
                "url": url,
                "sha256": source_hashes[url],
                "records": len(records),
                "timezone_updates": updates,
            }
        )

    document = {
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE_DESCRIPTION,
        "source_files": source_files,
        "timezones": dict(sorted(timezones.items())),
    }
    _validate_candidate(document)
    return document, source_hashes


def _serialize(document: dict[str, Any]) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


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


def _atomic_replace(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def update_catalog(output_path: Path) -> dict[str, Any]:
    old_bytes = output_path.read_bytes() if output_path.exists() else None
    old_timezones = _current_timezones(output_path)

    with tempfile.TemporaryDirectory(prefix="flight-calendar-airports.") as tmp:
        document, source_hashes = _build_candidate(Path(tmp))
    candidate_bytes = _serialize(document)
    changed = old_bytes != candidate_bytes
    counts = _diff_counts(old_timezones, document["timezones"])
    if changed:
        _atomic_replace(output_path, candidate_bytes)

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
        description="Update the bundled flight-calendar-ics airport timezone catalog."
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
    except (OSError, UpdateFailure) as exc:
        result = _error_result(exc)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
