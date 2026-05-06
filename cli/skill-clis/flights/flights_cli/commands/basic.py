from __future__ import annotations

import argparse
import sys
from typing import Any

from .. import __version__
from ..config import DEFAULT_ROUTE_HUB_NOTES, DEFAULT_ROUTE_HUBS, PLUGIN_PATH, RISK_PROFILES
from ..domain.airports import explain_airport
from ..env import auth_presence
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
    max_age_seconds = parse_ttl_seconds(args.catalog_max_age)
    return {
        "version": __version__,
        "python": sys.executable,
        "offline_first": True,
        "cached_fetch_default": False,
        "hermes_plugin_path": str(PLUGIN_PATH),
        "hermes_plugin_exists": PLUGIN_PATH.exists(),
        "cache_dir": str(store.cache_dir),
        "cache_dir_exists": store.cache_dir.exists(),
        "cache_files": cache_files,
        "cache_counts": store.cache_counts(),
        "catalog_auto_refresh_policy": {
            "mode": args.catalog_refresh,
            "max_age": args.catalog_max_age,
            "max_age_seconds": max_age_seconds,
            "timeout": args.catalog_refresh_timeout,
            "applies_to": ["cities search", "airports explain", "route plan", "route kb-assemble", "metrics workflow"],
        },
        "catalog_staleness": catalog_staleness(store.cache_dir, max_age_seconds=max_age_seconds),
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
            "travelpayouts_cached_fetch_requires": "request ... --fetch",
            "live_provider_commands": ["kb-search", "u6-prices", "route kb-assemble"],
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
