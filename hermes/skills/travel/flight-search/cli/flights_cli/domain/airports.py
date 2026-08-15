from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..config import (
    AIRPORT_TO_GROUP,
    MULTI_AIRPORT_GROUPS,
    SINGLE_AIRPORT_NOTES,
)
from ..domain.normalize import normalize_airport_scope, normalize_iata
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
        }
        notes.append(group["note"])
    if normalized in SINGLE_AIRPORT_NOTES:
        notes.append(SINGLE_AIRPORT_NOTES[normalized])
    return data


def explicit_or_resolved_airports(
    location: Location,
    explicit: list[str] | None,
    *,
    role: str,
    max_airports: int,
) -> list[str]:
    if explicit:
        return normalize_airport_scope(explicit, f"{role}-airport")
    airports = normalize_airport_scope(list(location.airports or []), f"{role}-airport")
    if not airports and location.kind in {"airport", "iata"}:
        airports = [normalize_iata(location.code, f"{role}-airport")]
    if not airports:
        raise CliError(
            f"no flightable airports found for {location.input!r}",
            error_type="not_found",
        )
    return airports[: max(1, max_airports)]


def airport_scope_summary(
    location: Location, airports: list[str], explicit: list[str] | None, *, role: str
) -> dict[str, Any]:
    normalized_airports = [str(code).upper() for code in airports]
    if explicit:
        scope = "explicit_airports"
        note = f"{role} airport scope was explicitly constrained."
    elif location.kind == "city":
        scope = "city_airports"
        note = f"{role} resolved from the static catalog's flightable airports."
    elif len(normalized_airports) == 1:
        scope = "single_airport"
        note = f"{role} resolved to a single flightable airport."
    else:
        scope = "city_airports"
        note = f"{role} resolved from the static airport catalog."
    summary = {
        "role": role,
        "input": location.input,
        "code": location.code,
        "kind": location.kind,
        "scope": scope,
        "airports": normalized_airports,
        "primary": normalized_airports[0] if normalized_airports else None,
        "excluded_by_default": [],
        "note": note,
    }
    return summary
