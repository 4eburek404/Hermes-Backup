from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .. import __version__
from ..errors import CliError

STATIC_CATALOG_SCHEMA_VERSION = "travelpayouts-static-v1"
DEFAULT_AUTO_REFRESH_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
TTL_RE = re.compile(r"^(?P<value>\d+)(?P<unit>[smhdw])?$")


@dataclass(frozen=True, slots=True)
class StaticCatalogSpec:
    name: str
    url: str
    filename: str
    stale_note: str | None = None


STATIC_CATALOG_SPECS: tuple[StaticCatalogSpec, ...] = (
    StaticCatalogSpec(
        name="countries",
        url="https://api.travelpayouts.com/data/en/countries.json",
        filename="countries.json",
    ),
    StaticCatalogSpec(
        name="cities_en",
        url="https://api.travelpayouts.com/data/en/cities.json",
        filename="cities_en.json",
    ),
    StaticCatalogSpec(
        name="cities_ru",
        url="https://api.travelpayouts.com/data/ru/cities.json",
        filename="cities_ru.json",
    ),
    StaticCatalogSpec(
        name="airports_en",
        url="https://api.travelpayouts.com/data/en/airports.json",
        filename="airports_en.json",
    ),
    StaticCatalogSpec(
        name="airports_ru",
        url="https://api.travelpayouts.com/data/ru/airports.json",
        filename="airports_ru.json",
    ),
    StaticCatalogSpec(
        name="airlines_en",
        url="https://api.travelpayouts.com/data/en/airlines.json",
        filename="airlines_en.json",
    ),
    StaticCatalogSpec(
        name="airlines_ru",
        url="https://api.travelpayouts.com/data/ru/airlines.json",
        filename="airlines_ru.json",
    ),
    StaticCatalogSpec(
        name="alliances",
        url="https://api.travelpayouts.com/data/en/alliances.json",
        filename="alliances.json",
    ),
    StaticCatalogSpec(
        name="planes",
        url="https://api.travelpayouts.com/data/planes.json",
        filename="planes.json",
        stale_note="Travelpayouts marks planes.json as not updated; use it only as metadata.",
    ),
    StaticCatalogSpec(
        name="routes",
        url="https://api.travelpayouts.com/data/routes.json",
        filename="routes.json",
        stale_note="Travelpayouts marks routes.json as not updated; use it as historical topology prior only.",
    ),
)

STATIC_CATALOG_BY_NAME = {spec.name: spec for spec in STATIC_CATALOG_SPECS}
MANIFEST_FILENAME = "catalog_manifest.json"

FetchUrl = Callable[[str, int], bytes]


def parse_ttl_seconds(value: str) -> int:
    raw = value.strip().lower()
    match = TTL_RE.match(raw)
    if not match:
        raise CliError("catalog max age must look like 12h, 7d, 2w, or 3600s", error_type="validation_error")
    amount = int(match.group("value"))
    unit = match.group("unit") or "s"
    multipliers = {
        "s": 1,
        "m": 60,
        "h": 60 * 60,
        "d": 24 * 60 * 60,
        "w": 7 * 24 * 60 * 60,
    }
    return amount * multipliers[unit]


def default_fetch_url(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": f"flights-cli/{__version__}",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:1000]
        raise CliError(f"Travelpayouts static catalog HTTP {exc.code}: {body}", error_type="upstream_error") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise CliError(f"Travelpayouts static catalog request failed: {type(exc).__name__}", error_type="upstream_error") from exc


def selected_static_specs(names: list[str] | None) -> list[StaticCatalogSpec]:
    if not names:
        return list(STATIC_CATALOG_SPECS)
    selected: list[StaticCatalogSpec] = []
    unknown: list[str] = []
    for name in names:
        spec = STATIC_CATALOG_BY_NAME.get(name)
        if spec:
            selected.append(spec)
        else:
            unknown.append(name)
    if unknown:
        raise CliError(
            f"unknown catalog item(s): {', '.join(unknown)}",
            error_type="validation_error",
            details={"available": sorted(STATIC_CATALOG_BY_NAME)},
        )
    return selected


def parse_catalog_payload(raw: bytes, spec: StaticCatalogSpec) -> tuple[Any, int]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CliError(f"{spec.name} did not return valid JSON", error_type="upstream_error") from exc
    if not isinstance(data, list):
        raise CliError(f"{spec.name} JSON must be an array", error_type="upstream_error")
    return data, len(data)


def canonical_json_bytes(data: Any) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_bytes(content)
    temp_path.replace(path)


def read_catalog_manifest(cache_dir: Path) -> dict[str, Any]:
    path = cache_dir / MANIFEST_FILENAME
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def parse_downloaded_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def catalog_staleness(
    cache_dir: Path,
    *,
    names: list[str] | None = None,
    max_age_seconds: int = DEFAULT_AUTO_REFRESH_MAX_AGE_SECONDS,
    now: datetime | None = None,
) -> dict[str, Any]:
    specs = selected_static_specs(names)
    manifest = read_catalog_manifest(cache_dir)
    entries = manifest.get("entries") if isinstance(manifest.get("entries"), dict) else {}
    checked_at = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    stale: list[dict[str, Any]] = []
    fresh: list[str] = []

    for spec in specs:
        path = cache_dir / spec.filename
        entry = entries.get(spec.name) if isinstance(entries, dict) else None
        reasons: list[str] = []
        if not path.exists():
            reasons.append("missing_file")
        if not isinstance(entry, dict):
            reasons.append("missing_manifest_entry")
        else:
            downloaded_at = parse_downloaded_at(entry.get("downloaded_at"))
            if downloaded_at is None:
                reasons.append("invalid_downloaded_at")
            else:
                age_seconds = int((checked_at - downloaded_at).total_seconds())
                if age_seconds > max_age_seconds:
                    reasons.append("expired")
            expected_sha = entry.get("sha256")
            if path.exists() and isinstance(expected_sha, str) and expected_sha:
                try:
                    actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
                except OSError:
                    actual_sha = None
                if actual_sha != expected_sha:
                    reasons.append("sha256_mismatch")
        if reasons:
            stale.append(
                {
                    "name": spec.name,
                    "filename": spec.filename,
                    "reasons": reasons,
                    "downloaded_at": entry.get("downloaded_at") if isinstance(entry, dict) else None,
                }
            )
        else:
            fresh.append(spec.name)

    return {
        "checked_at": checked_at.isoformat(),
        "max_age_seconds": max_age_seconds,
        "fresh": fresh,
        "stale": stale,
        "stale_count": len(stale),
        "checked_count": len(specs),
    }


def download_static_catalog(
    cache_dir: Path,
    *,
    names: list[str] | None = None,
    timeout: int = 30,
    dry_run: bool = False,
    fetch_url: FetchUrl = default_fetch_url,
    now: datetime | None = None,
) -> dict[str, Any]:
    specs = selected_static_specs(names)
    downloaded_at = (now or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
    planned = [
        {
            "name": spec.name,
            "url": spec.url,
            "filename": spec.filename,
            "stale_note": spec.stale_note,
        }
        for spec in specs
    ]
    if dry_run:
        return {
            "dry_run": True,
            "cache_dir": str(cache_dir),
            "planned": planned,
            "updated": [],
            "manifest": read_catalog_manifest(cache_dir),
        }

    existing_manifest = read_catalog_manifest(cache_dir)
    existing_entries = existing_manifest.get("entries") if isinstance(existing_manifest.get("entries"), dict) else {}
    entries = dict(existing_entries or {})
    updated: list[dict[str, Any]] = []

    for spec in specs:
        raw = fetch_url(spec.url, timeout)
        data, count = parse_catalog_payload(raw, spec)
        content = canonical_json_bytes(data)
        digest = hashlib.sha256(content).hexdigest()
        path = cache_dir / spec.filename
        atomic_write_bytes(path, content)
        entry = {
            "schema_version": STATIC_CATALOG_SCHEMA_VERSION,
            "downloaded_at": downloaded_at,
            "url": spec.url,
            "filename": spec.filename,
            "count": count,
            "sha256": digest,
        }
        if spec.stale_note:
            entry["stale_note"] = spec.stale_note
        entries[spec.name] = entry
        updated.append({"name": spec.name, **entry})

    manifest = {
        "schema_version": STATIC_CATALOG_SCHEMA_VERSION,
        "updated_at": downloaded_at,
        "cache_dir": str(cache_dir),
        "entries": entries,
    }
    atomic_write_bytes(cache_dir / MANIFEST_FILENAME, canonical_json_bytes(manifest))
    return {
        "dry_run": False,
        "cache_dir": str(cache_dir),
        "updated_count": len(updated),
        "updated": updated,
        "manifest": manifest,
    }


def refresh_static_catalog_if_needed(
    cache_dir: Path,
    *,
    names: list[str] | None = None,
    max_age_seconds: int = DEFAULT_AUTO_REFRESH_MAX_AGE_SECONDS,
    timeout: int = 30,
    fetch_url: FetchUrl = default_fetch_url,
    now: datetime | None = None,
    force: bool = False,
) -> dict[str, Any]:
    stale_report = catalog_staleness(cache_dir, names=names, max_age_seconds=max_age_seconds, now=now)
    stale_names = [item["name"] for item in stale_report["stale"]]
    if not force and not stale_names:
        return {
            "enabled": True,
            "refreshed": False,
            "reason": "fresh",
            "checked": stale_report,
            "update": None,
        }

    update_names = names if force else stale_names
    update = download_static_catalog(
        cache_dir,
        names=update_names,
        timeout=timeout,
        dry_run=False,
        fetch_url=fetch_url,
        now=now,
    )
    return {
        "enabled": True,
        "refreshed": True,
        "reason": "force" if force else "stale",
        "checked": stale_report,
        "update": {
            "updated_count": update["updated_count"],
            "updated": [
                {
                    "name": item["name"],
                    "filename": item["filename"],
                    "count": item["count"],
                    "downloaded_at": item["downloaded_at"],
                    "sha256": item["sha256"],
                }
                for item in update["updated"]
            ],
        },
    }
