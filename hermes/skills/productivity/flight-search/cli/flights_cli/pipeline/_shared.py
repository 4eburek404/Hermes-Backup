# pipeline/_shared.py
"""Shared pipeline helpers — single canonical home for deduplicated utilities."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..domain.vocabulary import MarketClass


def as_tuple(value: Any) -> tuple[Any, ...]:
    """Normalise a value to a tuple: None→(), list→tuple, scalar→1-tuple."""
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return (value,)


def is_direct_only(options: Mapping[str, Any]) -> bool:
    """True when the user explicitly requested direct flights only."""
    return (
        options.get("max_connections") == 0
        and options.get("tier2_max_connections") == 0
    )


def classify_market(origin_country: str | None, destination_country: str | None) -> str:
    """Classify a route market from two resolved country codes.

    Returns one of: ru_domestic, ru_touching_international, global_non_ru, structurally_constrained.
    """
    if origin_country == "RU" and destination_country == "RU":
        return MarketClass.RU_DOMESTIC
    if origin_country == "RU" or destination_country == "RU":
        return MarketClass.RU_TOUCHING_INTERNATIONAL
    if origin_country and destination_country:
        return MarketClass.GLOBAL_NON_RU
    return MarketClass.STRUCTURALLY_CONSTRAINED


def resolve_country_code(store: Any, code: str) -> str | None:
    """Resolve an airport/city code to an ISO-3166 alpha-2 country code.

    Lookup order:
    1. store.resolve_location(code) — canonical Location with country_code.
    2. store.airport_by_code dict fallback.
    3. store.city_by_code dict fallback.
    """
    normalized = str(code or "").upper()
    # 1. Canonical resolve_location path
    try:
        location = store.resolve_location(normalized)
    except Exception:
        location = None
    if location is not None and getattr(location, "country_code", None):
        return str(location.country_code or "").upper() or None
    # 2. Airport dict fallback
    airport = getattr(store, "airport_by_code", {}).get(normalized)
    if airport and airport.get("country_code"):
        return str(airport.get("country_code") or "").upper()
    # 3. City dict fallback
    city = getattr(store, "city_by_code", {}).get(normalized)
    if city and city.get("country_code"):
        return str(city.get("country_code") or "").upper()
    return None
