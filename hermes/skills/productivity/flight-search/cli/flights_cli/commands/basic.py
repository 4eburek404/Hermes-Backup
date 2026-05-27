from __future__ import annotations

import argparse
import sys
from typing import Any

from .. import __skill_name__, __skill_version__, __version__
from ..config import DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS, DEFAULT_ROUTE_HUB_NOTES, DEFAULT_ROUTE_HUBS, PLUGIN_PATH, RISK_PROFILES
from ..domain.airports import explain_airport
from ..env import auth_presence
from ..providers.route_intel import svx_route_index_path
from ..providers.static_catalog import active_catalog_manifest, catalog_staleness, download_static_catalog, parse_ttl_seconds
from ..store import Store, city_to_output

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
    return {
        "version": __version__,
        "cli": {"name": "flights-cli", "version": __version__},
        "skill": {"name": __skill_name__, "version": __skill_version__},
        "python": sys.executable,
        "offline_first": True,
        "hermes_plugin_path": str(PLUGIN_PATH),
        "hermes_plugin_exists": PLUGIN_PATH.exists(),
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
            "applies_to": ["cities search", "airports explain", "route plan", "route kb-assemble", "route live-assemble", "metrics workflow"],
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
        "auth": {
            "travelpayouts_token": auth_presence("TRAVELPAYOUTS_TOKEN"),
            "travelpayouts_marker": auth_presence("TRAVELPAYOUTS_MARKER"),
        },
        "safety": {
            "booking_or_purchase": False,
            "docker_touched": False,
            "travelpayouts_usage": "static_catalog_only",
            "travelpayouts_price_search_enabled": False,
            "live_provider_commands": ["kb-search", "kb-roundtrip", "fli-search", "fli-dates", "route kb-assemble", "route live-assemble"],
            "legacy_debug_commands": [],
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
