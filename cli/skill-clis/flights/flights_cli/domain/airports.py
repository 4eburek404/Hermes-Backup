from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..config import AIRPORT_TO_GROUP, MULTI_AIRPORT_GROUPS, SINGLE_AIRPORT_NOTES, SPECIAL_CITY_AIRPORTS
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
    airports = list(location.airports or [])
    if location.code in SPECIAL_CITY_AIRPORTS and role in {"origin", "destination"}:
        airports = SPECIAL_CITY_AIRPORTS[location.code]
    if not airports and location.kind in {"airport", "iata"}:
        airports = [location.code]
    if not airports:
        raise CliError(f"no flightable airports found for {location.input!r}", error_type="not_found")
    return airports[:max(1, max_airports)]


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
