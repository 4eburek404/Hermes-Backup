from __future__ import annotations

import argparse
import sys
from typing import Any

from .. import __skill_name__, __skill_version__, __version__
from ..command_surface import (
    CATALOG_AUTO_REFRESH_COMMANDS,
    CATALOG_READ_COMMANDS,
    CATALOG_REFRESH_COMMANDS,
    LIVE_PROVIDER_COMMANDS,
    PRIMARY_ROUTE_COMMAND,
    TARGETED_PROBE_COMMANDS,
)
from ..config import DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS, DEFAULT_ROUTE_HUB_NOTES, DEFAULT_ROUTE_HUBS, RISK_PROFILES
from ..domain.airports import explain_airport
from ..providers.route_intel import svx_route_index_path
from ..providers.static_catalog import active_catalog_manifest, catalog_staleness, download_static_catalog, parse_ttl_seconds
from ..store import Store, city_to_output
from ..version_manifest import load_version_manifest, manifest_mismatches, manifest_path, source_skill_path

def command_doctor(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    cache_files = {}
    for name in [
        "countries.json",
        "cities_ru.json",
        "cities_en.json",
        "airports_en.json",
        "airports_ru.json",
        "airlines_en.json",
        "airlines_ru.json",
        "alliances.json",
        "planes.json",
        "catalog_manifest.json",
    ]:
        path = store.cache_dir / name
        cache_files[name] = {"exists": path.exists(), "path": str(path)}
    route_index_path = svx_route_index_path(store.cache_dir / "route_intel")
    max_age_seconds = parse_ttl_seconds(args.catalog_max_age)
    skill_path = source_skill_path()
    manifest = load_version_manifest(skill_path)
    return {
        "version": __version__,
        "cli": {"name": "flights-cli", "version": __version__},
        "skill": {"name": __skill_name__, "version": __skill_version__},
        "version_manifest": {
            "path": str(manifest_path(skill_path)),
            "exists": bool(manifest),
            "mismatches": manifest_mismatches(manifest),
        },
        "python": sys.executable,
        "offline_first": True,
        "cache_dir": str(store.cache_dir),
        "cache_dir_exists": store.cache_dir.exists(),
        "cache_files": cache_files,
        "route_intel_cache": {
            "svx_official_route_index": {
                "exists": route_index_path.exists(),
                "path": str(route_index_path),
            }
        },
        "cache_counts": store.cache_counts(),
        "catalog_auto_refresh_policy": {
            "mode": args.catalog_refresh,
            "max_age": args.catalog_max_age,
            "max_age_seconds": max_age_seconds,
            "timeout": args.catalog_refresh_timeout,
            "applies_to": list(CATALOG_AUTO_REFRESH_COMMANDS),
            "auto_refresh_commands": list(CATALOG_AUTO_REFRESH_COMMANDS),
            "catalog_read_commands": list(CATALOG_READ_COMMANDS),
            "manual_refresh_commands": list(CATALOG_REFRESH_COMMANDS),
            "explicit_refresh_command": "maint catalog refresh",
        },
        "catalog_staleness": catalog_staleness(store.cache_dir, max_age_seconds=max_age_seconds),
        "runtime_evidence_policy": {
            "live_cache": {
                "status_values": ["live", "cache_hit", "stale_cache_used", "disabled", "unknown"],
                "default_ttl_seconds": DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS,
            },
            "request_deduplication": {
                "scope": "in_process_identical_segment_probes",
                "network_calls_for_duplicates": False,
            },
            "retry_policy": {
                "active_retry": False,
                "retry_after_is_classified_only": True,
            },
            "failure_classification": {
                "preserves_original_error_type": True,
                "classes": ["rate_limited", "timeout", "provider_unavailable", "blocked_response", "parse_error", "upstream_error"],
            },
            "live_network_checks_in_doctor": False,
        },
        "default_route_hubs": [
            {"code": hub, "note": DEFAULT_ROUTE_HUB_NOTES.get(hub)}
            for hub in DEFAULT_ROUTE_HUBS
        ],
        "safety": {
            "booking_or_purchase": False,
            "docker_touched": False,
            "primary_route_command": PRIMARY_ROUTE_COMMAND,
            "targeted_probe_commands": list(TARGETED_PROBE_COMMANDS),
            "live_provider_commands": list(LIVE_PROVIDER_COMMANDS),
        },
        "risk_profiles": {
            name: {
                "description": config["description"],
                "rank_order": config["rank_order"],
                "ideal_same_min": config["ideal_same_min"],
                "ideal_same_max": config["ideal_same_max"],
            }
            for name, config in RISK_PROFILES.items()
        },
    }


def command_cities_search(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    return {
        "query": args.query,
        "cities": [city_to_output(store, city) for city in store.search_cities(args.query, args.limit)],
    }


def command_airports_explain(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    return {"airports": [explain_airport(store, code) for code in args.code]}


def command_catalog_update(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    return download_static_catalog(
        store.cache_dir,
        names=args.only,
        timeout=args.timeout,
        dry_run=args.dry_run,
    )


def command_catalog_manifest(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    max_age_seconds = parse_ttl_seconds(args.catalog_max_age)
    manifest = active_catalog_manifest(store.load_manifest())
    return {
        "cache_dir": str(store.cache_dir),
        "manifest": manifest,
        "cache_counts": store.cache_counts(),
        "catalog_staleness": catalog_staleness(store.cache_dir, max_age_seconds=max_age_seconds),
    }
