#!/usr/bin/env python3
"""Shared Travelpayouts source and airport-timezone catalog contract."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SCHEMA_VERSION = "airport-timezones.v1"
CANONICAL_SOURCE_URL = "https://api.travelpayouts.com/data/en/airports.json"
SOURCE_DESCRIPTION = "Compact derived airport catalog; only code -> time_zone is retained."
IATA_RE = re.compile(r"^[A-Z]{3}$")
FetchSource = Callable[[str], bytes]


class CatalogUpdateFailure(ValueError):
    """A source download, extraction, or candidate validation failure."""


def fetch_source(url: str = CANONICAL_SOURCE_URL) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Hermes flight-calendar-ics airport catalog updater/1.0",
            "Accept-Encoding": "identity",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise CatalogUpdateFailure(f"{url} returned HTTP {status}")
            return response.read()
    except CatalogUpdateFailure:
        raise
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        raise CatalogUpdateFailure(
            f"download failed for {url}: {type(exc).__name__}"
        ) from exc


def _normalize_code(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_timezone(value: Any) -> str:
    return str(value or "").strip()


def parse_source(raw: bytes, *, url: str) -> list[Any]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CatalogUpdateFailure(f"invalid JSON from {url}: {type(exc).__name__}") from exc
    if not isinstance(data, list):
        raise CatalogUpdateFailure(f"upstream root from {url} must be a JSON array")
    return data


def extract_airport_timezones(
    records: list[Any], *, url: str
) -> tuple[dict[str, str], dict[str, Any]]:
    timezones: dict[str, str] = {}
    excluded = Counter()
    airport_records = 0
    flightable_true = 0
    flightable_false = 0
    flightable_missing_or_null = 0

    for index, item in enumerate(records):
        if not isinstance(item, dict):
            excluded["<non-object>"] += 1
            continue
        if item.get("iata_type") != "airport":
            excluded[str(item.get("iata_type") or "<missing>")] += 1
            continue

        airport_records += 1
        if item.get("flightable") is True:
            flightable_true += 1
        elif item.get("flightable") is False:
            flightable_false += 1
        else:
            flightable_missing_or_null += 1

        code = _normalize_code(item.get("code"))
        if not IATA_RE.fullmatch(code):
            continue
        timezone = _normalize_timezone(item.get("time_zone"))
        if not timezone:
            continue
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise CatalogUpdateFailure(
                f"{url} record {index} has unknown IANA timezone {timezone!r}"
            ) from exc
        timezones[code] = timezone

    return dict(sorted(timezones.items())), {
        "records": len(records),
        "airport_records": airport_records,
        "airports_retained": len(timezones),
        "flightable_true": flightable_true,
        "flightable_false": flightable_false,
        "flightable_missing_or_null": flightable_missing_or_null,
        "non_airport_by_type": dict(sorted(excluded.items())),
    }


def validate_catalog_document(document: dict[str, Any]) -> None:
    if document.get("schema_version") != SCHEMA_VERSION:
        raise CatalogUpdateFailure("catalog has unsupported schema_version")
    timezones = document.get("timezones")
    if not isinstance(timezones, dict):
        raise CatalogUpdateFailure("catalog has no timezones object")
    for code, timezone in timezones.items():
        if not isinstance(code, str) or not IATA_RE.fullmatch(code):
            raise CatalogUpdateFailure(f"catalog has invalid airport code {code!r}")
        if not isinstance(timezone, str) or not timezone:
            raise CatalogUpdateFailure(f"catalog has empty timezone for {code}")
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise CatalogUpdateFailure(
                f"catalog has unknown IANA timezone {timezone!r} for {code}"
            ) from exc


def build_catalog_document(raw: bytes, *, url: str = CANONICAL_SOURCE_URL) -> dict[str, Any]:
    records = parse_source(raw, url=url)
    timezones, stats = extract_airport_timezones(records, url=url)
    document = {
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE_DESCRIPTION,
        "source_files": [
            {
                "url": url,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "records": stats["records"],
                "airports_retained": stats["airports_retained"],
            }
        ],
        "timezones": timezones,
    }
    validate_catalog_document(document)
    return document


def serialize_catalog(document: dict[str, Any]) -> bytes:
    validate_catalog_document(document)
    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def atomic_write_bytes(path: Path, content: bytes) -> None:
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
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
