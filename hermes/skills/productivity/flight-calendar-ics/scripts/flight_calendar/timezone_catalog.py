#!/usr/bin/env python3
"""Minimal airport timezone catalog support for flight-calendar-ics.

The bundled asset is a compact derived catalog with a single field needed for
calendar correctness: IATA airport code -> IANA timezone. It is not a copy of
any full airport reference dictionary; only ``code -> time_zone`` is retained.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "airport-timezones.v1"
RAW_AIRPORT_FILENAMES = ("airports_en.json", "airports_ru.json", "airports.json")
SKILL_DIR = Path(__file__).resolve().parents[2]
CATALOG_PATH = SKILL_DIR / "data" / "airport-timezones.json"
IATA_RE = re.compile(r"^[A-Z0-9]{3}$")


def _normalize_code(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_timezone(value: Any) -> str:
    return str(value or "").strip()


def _looks_like_iata_timezone(code: str, timezone: str) -> bool:
    return bool(
        IATA_RE.fullmatch(code) and "/" in timezone and not timezone.startswith("/")
    )


def extract_airport_timezones(
    source_dir: Path,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Extract only IATA -> IANA timezone entries from raw airport JSON files.

    Source precedence is airports_en.json, airports_ru.json, then airports.json.
    Later files can replace earlier values if localized catalogs differ.
    """
    timezones: dict[str, str] = {}
    source_files: list[dict[str, Any]] = []
    for filename in RAW_AIRPORT_FILENAMES:
        path = source_dir / filename
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"{path} must contain a JSON array")
        added_or_updated = 0
        for item in data:
            if not isinstance(item, dict):
                continue
            code = _normalize_code(item.get("code"))
            timezone = _normalize_timezone(
                item.get("time_zone") or item.get("timezone")
            )
            if _looks_like_iata_timezone(code, timezone):
                if timezones.get(code) != timezone:
                    added_or_updated += 1
                timezones[code] = timezone
        source_files.append(
            {
                "filename": filename,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "records": len(data),
                "timezone_updates": added_or_updated,
            }
        )
    return dict(sorted(timezones.items())), source_files


def build_catalog_document(source_dir: Path) -> dict[str, Any]:
    timezones, source_files = extract_airport_timezones(source_dir)
    return {
        "schema_version": SCHEMA_VERSION,
        "source": "Compact derived airport catalog; only code -> time_zone is retained.",
        "source_files": source_files,
        "timezones": timezones,
    }


def write_catalog_document(
    source_dir: Path, output_path: Path = CATALOG_PATH
) -> dict[str, Any]:
    document = build_catalog_document(source_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return document


def load_catalog_document(catalog_path: Path | None = None) -> dict[str, Any]:
    path = catalog_path or CATALOG_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"{path} has unsupported schema_version {data.get('schema_version')!r}"
        )
    timezones = data.get("timezones")
    if not isinstance(timezones, dict):
        raise ValueError(f"{path} has no timezones object")
    return data


def load_airport_timezones(catalog_path: Path | None = None) -> dict[str, str]:
    document = load_catalog_document(catalog_path)
    timezones: dict[str, str] = {}
    for code, timezone in document["timezones"].items():
        norm_code = _normalize_code(code)
        norm_tz = _normalize_timezone(timezone)
        if _looks_like_iata_timezone(norm_code, norm_tz):
            timezones[norm_code] = norm_tz
    return timezones


def build_timezone_map(
    overrides: dict[str, str] | None = None, *, catalog_path: Path | None = None
) -> dict[str, str]:
    """Build timezone map: bundled catalog < explicit overrides.

    There is intentionally no local/manual fallback map here. If an airport is
    missing from the bundled asset, regenerate the asset from the raw airport
    cache or pass a deliberate explicit override supplied by the user/operator.
    """
    timezone_map = load_airport_timezones(catalog_path)
    for code, timezone in (overrides or {}).items():
        norm_code = _normalize_code(code)
        norm_tz = _normalize_timezone(timezone)
        if norm_code and norm_tz:
            timezone_map[norm_code] = norm_tz
    return timezone_map


def catalog_metadata(catalog_path: Path | None = None) -> dict[str, Any]:
    document = load_catalog_document(catalog_path)
    return {
        "schema_version": document.get("schema_version"),
        "path": str(catalog_path or CATALOG_PATH),
        "timezones_count": len(document.get("timezones") or {}),
        "source_files": document.get("source_files") or [],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build or inspect the flight-calendar-ics airport timezone asset."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser(
        "build", help="Extract code -> time_zone from raw airport JSON cache files"
    )
    build.add_argument(
        "--source-dir",
        required=True,
        type=Path,
        help="Directory containing airports_en.json, airports_ru.json, airports.json",
    )
    build.add_argument(
        "--output",
        type=Path,
        default=CATALOG_PATH,
        help="Output airport-timezones.json path",
    )

    inspect = sub.add_parser(
        "inspect", help="Print metadata for the bundled timezone asset"
    )
    inspect.add_argument(
        "--catalog", type=Path, default=CATALOG_PATH, help="Catalog asset path"
    )

    args = parser.parse_args(argv)
    if args.command == "build":
        document = write_catalog_document(args.source_dir, args.output)
        result = {
            "ok": True,
            "output": str(args.output),
            "timezones_count": len(document["timezones"]),
            "source_files": document["source_files"],
        }
    else:
        result = {"ok": True, **catalog_metadata(args.catalog)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
