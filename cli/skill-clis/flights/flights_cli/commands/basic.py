from __future__ import annotations

import argparse
import sys
from typing import Any

from .. import __version__
from ..config import PLUGIN_PATH, RISK_PROFILES
from ..domain.airports import explain_airport
from ..env import auth_presence
from ..store import Store, city_to_output

def command_doctor(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    cache_files = {}
    for name in ["cities_ru.json", "airports.json", "airlines.json", "planes.json"]:
        path = store.cache_dir / name
        cache_files[name] = {"exists": path.exists(), "path": str(path)}
    return {
        "version": __version__,
        "python": sys.executable,
        "offline_first": True,
        "live_api_default": False,
        "hermes_plugin_path": str(PLUGIN_PATH),
        "hermes_plugin_exists": PLUGIN_PATH.exists(),
        "cache_dir": str(store.cache_dir),
        "cache_dir_exists": store.cache_dir.exists(),
        "cache_files": cache_files,
        "cache_counts": store.cache_counts(),
        "auth": {
            "travelpayouts_token": auth_presence("TRAVELPAYOUTS_TOKEN"),
            "travelpayouts_marker": auth_presence("TRAVELPAYOUTS_MARKER"),
        },
        "safety": {
            "booking_or_purchase": False,
            "docker_touched": False,
            "travelpayouts_live_requires": "request search --live",
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
