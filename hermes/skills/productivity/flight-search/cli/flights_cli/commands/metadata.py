from __future__ import annotations

import argparse
from typing import Any

from ..domain.airports import explain_airport
from ..store import Store, city_to_output


def metadata_evidence_scope(source: str) -> dict[str, Any]:
    return {
        "source": source,
        "kind": "static_metadata",
        "availability_evidence": False,
        "availability_claims_allowed": False,
        "live_provider_evidence_required": True,
        "note": "Static catalog metadata can explain labels and routing scope, but cannot prove flight availability or absence.",
    }


def command_cities_search(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    return {
        "query": args.query,
        "evidence_scope": metadata_evidence_scope("cities static catalog"),
        "cities": [
            city_to_output(store, city)
            for city in store.search_cities(args.query, args.limit)
        ],
    }


def command_airports_explain(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    return {
        "evidence_scope": metadata_evidence_scope("airports static catalog"),
        "airports": [explain_airport(store, code) for code in args.code],
    }
