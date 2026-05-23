from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..config import (
    AIRPORT_TO_GROUP,
    CITY_AIRPORTS_EXCLUDED_BY_DEFAULT,
    DUBAI_DEFAULT_AIRPORTS,
    DUBAI_EXCLUDED_BY_DEFAULT,
    MULTI_AIRPORT_GROUPS,
    PREFERRED_AIRPORT_TIERS,
    SINGLE_AIRPORT_NOTES,
    SPECIAL_CITY_AIRPORTS,
)
from ..domain.normalize import normalize_iata
from ..errors import CliError

if TYPE_CHECKING:
    from ..store import Location, Store

def airport_group(code: str) -> dict[str, Any] | None:
    group_key = AIRPORT_TO_GROUP.get(code.upper())
    if not group_key:
        return None
    group = MULTI_AIRPORT_GROUPS[group_key].copy()
    group["key"] = group_key
    return group


def explain_airport(store: Store, code: str) -> dict[str, Any]:
    normalized = normalize_iata(code)
    airport = store.airport_by_code.get(normalized)
    city_code = str(airport.get("city_code") or "") if airport else None
    group = airport_group(normalized)
    data = {
        "code": normalized,
        "known": bool(airport),
        "name": store.airport_name(normalized),
        "city_code": city_code,
        "city_name": store.city_name(city_code or "") if city_code else None,
        "country_code": airport.get("country_code") if airport else None,
        "iata_type": airport.get("iata_type") if airport else None,
        "flightable": airport.get("flightable") if airport else None,
        "group": None,
        "notes": [],
    }
    notes = data["notes"]
    if group:
        data["group"] = {
            "key": group["key"],
            "label": group["label"],
            "airports": group["airports"],
            "cross_transfer_min": group["cross_transfer_min"],
            "min_cross_connection_min": group["min_cross_connection_min"],
        }
        notes.append(group["note"])
    if normalized in SINGLE_AIRPORT_NOTES:
        notes.append(SINGLE_AIRPORT_NOTES[normalized])
    return data


def is_dubai_city_location(location: Location) -> bool:
    text = str(location.input or "").strip().lower()
    return (
        location.kind == "city"
        and str(location.country_code or "").upper() == "AE"
        and str(location.code or "").upper() == "DXB"
        and text not in {"dxb", "dwc", "shj"}
    )


def preferred_airport_tiers_for_city(city_code: str | None) -> list[dict[str, Any]]:
    tiers = PREFERRED_AIRPORT_TIERS.get(str(city_code or "").upper(), [])
    return [
        {
            "tier": int(tier["tier"]),
            "airports": [str(code).upper() for code in tier.get("airports", [])],
            "role": str(tier.get("role") or "preferred"),
        }
        for tier in tiers
    ]


def preferred_airports_for_city(city_code: str | None) -> list[str]:
    airports: list[str] = []
    for tier in preferred_airport_tiers_for_city(city_code):
        for code in tier["airports"]:
            if code not in airports:
                airports.append(code)
    return airports


def airport_priority_metadata(code: str) -> dict[str, Any] | None:
    normalized = str(code or "").upper()
    for city_code, tiers in PREFERRED_AIRPORT_TIERS.items():
        for tier in tiers:
            airports = [str(item).upper() for item in tier.get("airports", [])]
            if normalized in airports:
                return {
                    "city_code": city_code,
                    "tier": int(tier["tier"]),
                    "role": str(tier.get("role") or "preferred"),
                }
    return None


def explicit_or_resolved_airports(
    store: Store,
    location: Location,
    explicit: list[str] | None,
    *,
    role: str,
    max_airports: int,
) -> list[str]:
    if explicit:
        return [normalize_iata(code, f"{role}-airport") for code in explicit]
    if is_dubai_city_location(location) and role in {"origin", "destination"}:
        return list(DUBAI_DEFAULT_AIRPORTS)[: max(1, max_airports)]
    airports = list(location.airports or [])
    location_code = str(location.code or "").upper()
    preferred_airports = preferred_airports_for_city(location_code)
    if preferred_airports and role in {"origin", "destination"}:
        airports = preferred_airports
    elif location_code in SPECIAL_CITY_AIRPORTS and role in {"origin", "destination"}:
        airports = SPECIAL_CITY_AIRPORTS[location_code]
    if not airports and location.kind in {"airport", "iata"}:
        airports = [location.code]
    if not airports:
        raise CliError(f"no flightable airports found for {location.input!r}", error_type="not_found")
    return airports[:max(1, max_airports)]


def airport_scope_summary(location: Location, airports: list[str], explicit: list[str] | None, *, role: str) -> dict[str, Any]:
    normalized_airports = [str(code).upper() for code in airports]
    location_code = str(location.code or "").upper()
    preferred_tiers = preferred_airport_tiers_for_city(location_code) if not explicit else []
    if explicit:
        scope = "explicit_or_single_airport"
        excluded: list[str] = []
        note = f"{role} airport scope was explicitly constrained."
    elif preferred_tiers:
        scope = "preferred_city_airports"
        excluded = [code for code in CITY_AIRPORTS_EXCLUDED_BY_DEFAULT.get(location_code, []) if code not in normalized_airports]
        note = f"{role} resolved to preferred city-airport tiers; excluded airports are not searched by default."
    elif is_dubai_city_location(location):
        scope = "dubai_default"
        excluded = [code for code in DUBAI_EXCLUDED_BY_DEFAULT if code not in normalized_airports]
        note = "Dubai defaults to DXB primary + DWC secondary; SHJ is Sharjah and is excluded unless explicitly requested or returned by a provider."
    elif len(normalized_airports) == 1:
        scope = "explicit_or_single_airport"
        excluded = [code for code in CITY_AIRPORTS_EXCLUDED_BY_DEFAULT.get(location_code, []) if code not in normalized_airports]
        note = f"{role} resolved to a single flightable airport."
    else:
        scope = "city_airports"
        excluded = [code for code in CITY_AIRPORTS_EXCLUDED_BY_DEFAULT.get(location_code, []) if code not in normalized_airports]
        note = f"{role} resolved to the city's flightable airports within max-airports-per-city."
    summary = {
        "role": role,
        "input": location.input,
        "code": location.code,
        "kind": location.kind,
        "scope": scope,
        "airports": normalized_airports,
        "primary": normalized_airports[0] if normalized_airports else None,
        "excluded_by_default": excluded,
        "note": note,
    }
    if preferred_tiers:
        summary["preferred_airport_tiers"] = preferred_tiers
    return summary


def airport_pair_risk(origin: str, destination: str) -> dict[str, Any]:
    origin_group = airport_group(origin)
    dest_group = airport_group(destination)
    same_group = bool(origin_group and dest_group and origin_group["key"] == dest_group["key"])
    notes: list[str] = []
    if origin != destination and same_group:
        notes.append(f"{origin} and {destination} are separate airports in {origin_group['label']}.")
    if destination in SINGLE_AIRPORT_NOTES:
        notes.append(SINGLE_AIRPORT_NOTES[destination])
    return {
        "origin_group": origin_group["label"] if origin_group else None,
        "destination_group": dest_group["label"] if dest_group else None,
        "same_multi_airport_system": same_group,
        "notes": notes,
    }
