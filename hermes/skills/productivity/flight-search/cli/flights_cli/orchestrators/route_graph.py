from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any

from ..config import (
    ASIA_DESTINATION_CODES,
    ASIA_OCEANIA_COUNTRIES,
    DEFAULT_COVERAGE_CONTROL_LIMIT,
    DOMESTIC_RU_HUBS,
    PRIORITY_ASIA_HUB,
    PRIORITY_MOSCOW_GATEWAY,
    PRIORITY_PRIMARY_HUB,
    PRIORITY_ROUTE_CARRIERS,
    PRIORITY_SECONDARY_HUB,
)
from ..domain.airports import airport_scope_summary
from ..domain.hubs import resolve_route_hubs, resolve_routing_strategy
from ..errors import CliError
from ..store import Store


@dataclass(frozen=True)
class RouteGraphContext:
    routing_strategy: str
    routing_profile: str
    hubs: list[str]
    hub_source: str
    airport_scope: dict[str, Any]
    coverage_mode: str
    coverage_limits: dict[str, Any]


def geo_routing_profile(destination: Any, destination_airports: list[str]) -> str:
    codes = {str(destination.code or "").upper(), *(code.upper() for code in destination_airports)}
    country = str(destination.country_code or "").upper()
    if country in ASIA_OCEANIA_COUNTRIES or codes & ASIA_DESTINATION_CODES:
        return "asia-oceania"
    return "default"


def route_families_for_strategy(routing_strategy: str, routing_profile: str) -> list[dict[str, Any]]:
    if routing_strategy == "ru-priority":
        families = [
            {
                "id": "direct_control",
                "priority": 0,
                "condition": "check direct exact-airport legs when live assembly runs; cache empty results",
                "preferred_carriers": list(PRIORITY_ROUTE_CARRIERS),
            },
        ]
        if routing_profile == "asia-oceania":
            families.append(
                {
                    "id": "svo_asia",
                    "priority": 1,
                    "hub": PRIORITY_ASIA_HUB,
                    "condition": "Asia/Oceania destination: check SVO as an independent hub, not only as an IST fallback",
                    "preferred_carriers": list(PRIORITY_ROUTE_CARRIERS),
                }
            )
        families += [
            {
                "id": "ist_direct",
                "priority": 2 if routing_profile == "asia-oceania" else 1,
                "hub": PRIORITY_PRIMARY_HUB,
                "condition": "check first; use origin->IST direct when available",
                "preferred_carriers": list(PRIORITY_ROUTE_CARRIERS),
            },
            {
                "id": "moscow_gateway_control",
                "priority": 3 if routing_profile == "asia-oceania" else 2,
                "hub": PRIORITY_PRIMARY_HUB,
                "via": [PRIORITY_MOSCOW_GATEWAY],
                "condition": "Moscow/SVO control; compare even when direct or primary-hub options exist",
                "required_carriers": ["SU"],
                "preferred_carriers": list(PRIORITY_ROUTE_CARRIERS),
            },
            {
                "id": "dxb_direct",
                "priority": 4 if routing_profile == "asia-oceania" else 3,
                "hub": PRIORITY_SECONDARY_HUB,
                "condition": "check only if direct/SVO/IST priority routes do not produce a usable assembled pair; do not expand origin->DXB through Moscow",
                "preferred_carriers": list(PRIORITY_ROUTE_CARRIERS),
            },
        ]
        return families
    if routing_strategy == "domestic-ru":
        return [
            {
                "id": "domestic_ru",
                "priority": 0,
                "condition": "Russian domestic route: exact-airport direct controls first; Moscow-airport fallback only, no international hubs by default.",
                "preferred_carriers": [],
            }
        ]
    return []


def route_segment_spec(
    direction: str,
    leg: str,
    dep_date: Any,
    origin_code: str,
    dest_code: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "direction": direction,
        "leg": leg,
        "origin": origin_code,
        "destination": dest_code,
        "date": dep_date.isoformat() if hasattr(dep_date, "isoformat") else str(dep_date),
        **extra,
    }


def route_segment_key(spec: dict[str, Any], *, include_date: bool) -> tuple[str, ...]:
    key = (
        str(spec.get("direction") or ""),
        str(spec.get("leg") or ""),
        str(spec.get("origin") or "").upper(),
        str(spec.get("destination") or "").upper(),
    )
    if include_date:
        return (*key, str(spec.get("date") or ""))
    return key


def airport_country(store: Store, code: str) -> str | None:
    airport = store.airport_by_code.get(str(code or "").upper())
    if airport and airport.get("country_code"):
        return str(airport.get("country_code") or "").upper()
    city = store.city_by_code.get(str(code or "").upper())
    if city and city.get("country_code"):
        return str(city.get("country_code") or "").upper()
    return None


def all_airports_in_country(store: Store, airports: list[str], country: str) -> bool:
    if not airports:
        return False
    target = country.upper()
    return all(airport_country(store, code) == target for code in airports)


def is_domestic_ru_route(store: Store, origin: Any, destination: Any, origin_airports: list[str], destination_airports: list[str]) -> bool:
    origin_country = str(origin.country_code or "").upper() or None
    destination_country = str(destination.country_code or "").upper() or None
    if origin_country == "RU" and destination_country == "RU":
        return True
    return all_airports_in_country(store, origin_airports, "RU") and all_airports_in_country(store, destination_airports, "RU")


def coverage_mode_from_args(args: argparse.Namespace) -> str:
    raw = str(getattr(args, "coverage_mode", "targeted") or "targeted").strip().lower()
    if raw not in {"standard", "targeted", "full"}:
        raise CliError("coverage mode must be one of standard, targeted, full", error_type="validation_error")
    return raw


def coverage_control_limit_from_args(args: argparse.Namespace) -> int:
    raw = getattr(args, "coverage_control_limit", DEFAULT_COVERAGE_CONTROL_LIMIT)
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise CliError("coverage-control-limit must be an integer", error_type="validation_error") from exc
    if value < 0:
        raise CliError("coverage-control-limit must be non-negative", error_type="validation_error")
    return value


def requested_coverage_controls_from_args(args: argparse.Namespace) -> list[str]:
    return [str(item).strip() for item in (getattr(args, "coverage_control", None) or []) if str(item).strip()]


def coverage_limits(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "live_fanout": "bounded_by_max_segment_searches",
        "max_segment_searches": getattr(args, "max_segment_searches", None),
        "coverage_control_limit": coverage_control_limit_from_args(args),
        "requested_controls": requested_coverage_controls_from_args(args),
        "cache_phase": "out_of_scope",
    }


def resolve_route_graph_context(
    args: argparse.Namespace,
    store: Store,
    origin: Any,
    destination: Any,
    origin_airports: list[str],
    destination_airports: list[str],
) -> RouteGraphContext:
    raw_routing_strategy = str(getattr(args, "routing_strategy", None) or "auto").strip().lower()
    domestic_ru = is_domestic_ru_route(store, origin, destination, origin_airports, destination_airports)
    if raw_routing_strategy == "auto" and domestic_ru and not getattr(args, "hub", None):
        routing_strategy = "domestic-ru"
    else:
        try:
            routing_strategy = resolve_routing_strategy(raw_routing_strategy, getattr(args, "hub", None))
        except ValueError as exc:
            raise CliError(str(exc), error_type="validation_error") from exc

    hubs, hub_source = resolve_route_hubs(getattr(args, "hub", None))
    routing_profile = geo_routing_profile(destination, destination_airports)
    if routing_strategy == "ru-priority":
        hubs = [PRIORITY_PRIMARY_HUB, PRIORITY_SECONDARY_HUB]
        if routing_profile == "asia-oceania":
            hubs = [PRIORITY_ASIA_HUB, PRIORITY_PRIMARY_HUB, PRIORITY_SECONDARY_HUB]
        hub_source = "strategy"
    elif routing_strategy == "domestic-ru":
        hubs = [hub for hub in DOMESTIC_RU_HUBS if hub not in set(origin_airports) | set(destination_airports)]
        if not hubs:
            hubs = [PRIORITY_MOSCOW_GATEWAY]
        hub_source = "domestic-ru"

    return RouteGraphContext(
        routing_strategy=routing_strategy,
        routing_profile=routing_profile,
        hubs=hubs,
        hub_source=hub_source,
        airport_scope={
            "origin": airport_scope_summary(origin, origin_airports, getattr(args, "origin_airport", None), role="origin"),
            "destination": airport_scope_summary(destination, destination_airports, getattr(args, "destination_airport", None), role="destination"),
        },
        coverage_mode=coverage_mode_from_args(args),
        coverage_limits=coverage_limits(args),
    )


def route_graph_from_segments(
    *,
    routing_strategy: str,
    routing_profile: str,
    hubs: list[str],
    origin_airports: list[str],
    destination_airports: list[str],
    segments: list[dict[str, Any]],
) -> dict[str, Any]:
    nodes = sorted(
        set(origin_airports)
        | set(destination_airports)
        | set(hubs)
        | {str(segment.get("origin") or "").upper() for segment in segments if segment.get("origin")}
        | {str(segment.get("destination") or "").upper() for segment in segments if segment.get("destination")}
    )
    edges = []
    for index, segment in enumerate(segments, 1):
        edges.append(
            {
                "id": f"edge-{index}",
                "direction": segment.get("direction"),
                "leg": segment.get("leg"),
                "origin": segment.get("origin"),
                "destination": segment.get("destination"),
                "date": segment.get("date"),
                "route_family": segment.get("route_family"),
                "priority": segment.get("priority"),
                "coverage_control": segment.get("coverage_control"),
            }
        )
    return {
        "strategy": routing_strategy,
        "routing_profile": routing_profile,
        "nodes": nodes,
        "hubs": hubs,
        "edges": edges,
        "families": sorted({str(segment.get("route_family")) for segment in segments if segment.get("route_family")}),
    }


def _control_key(control: dict[str, Any]) -> tuple[Any, ...]:
    return (
        control.get("type"),
        control.get("direction"),
        control.get("origin"),
        control.get("destination"),
        control.get("date"),
        control.get("carrier"),
    )


def _requested_carriers(requested_controls: list[str] | None) -> list[str]:
    carriers: list[str] = []
    for item in requested_controls or []:
        raw = str(item).strip()
        if not raw:
            continue
        lower = raw.lower()
        carrier = ""
        if lower.startswith("carrier_aggregate:"):
            carrier = raw.split(":", 1)[1]
        elif lower.startswith("carrier_aggregate="):
            carrier = raw.split("=", 1)[1]
        if carrier:
            code = carrier.strip().upper()
            if code and code not in carriers:
                carriers.append(code)
    return carriers


def _prioritized_carriers(preferred_carriers: list[str] | None, requested_controls: list[str] | None) -> list[str]:
    carriers: list[str] = []
    for code in _requested_carriers(requested_controls) + list(preferred_carriers or PRIORITY_ROUTE_CARRIERS):
        normalized = str(code).strip().upper()
        if normalized and normalized not in carriers:
            carriers.append(normalized)
    return carriers


def coverage_controls_for_plan(
    *,
    coverage_mode: str,
    origin_code: str,
    destination_code: str,
    origin_airports: list[str],
    destination_airports: list[str],
    depart: Any,
    ret: Any,
    preferred_carriers: list[str] | None = None,
    requested_controls: list[str] | None = None,
    coverage_control_limit: int | None = None,
) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    def add(control: dict[str, Any]) -> None:
        key = _control_key(control)
        if key in seen:
            return
        seen.add(key)
        controls.append(control)

    directions = [("outbound", origin_code, destination_code, depart)]
    if ret is not None:
        directions.append(("return", destination_code, origin_code, ret))

    if coverage_mode in {"standard", "targeted", "full"}:
        for direction, _origin_city, _dest_city, date_value in directions:
            source_airports = origin_airports if direction == "outbound" else destination_airports
            target_airports = destination_airports if direction == "outbound" else origin_airports
            for origin in source_airports:
                for destination in target_airports:
                    add(
                        {
                            "type": "exact_airport_direct",
                            "direction": direction,
                            "origin": origin,
                            "destination": destination,
                            "date": date_value.isoformat() if hasattr(date_value, "isoformat") else str(date_value),
                            "negative_evidence": "provider_empty_only_not_route_absence",
                        }
                    )

    if coverage_mode in {"targeted", "full"}:
        for direction, route_origin, route_destination, date_value in directions:
            add(
                {
                    "type": "full_route_aggregate",
                    "direction": direction,
                    "origin": route_origin,
                    "destination": route_destination,
                    "date": date_value.isoformat() if hasattr(date_value, "isoformat") else str(date_value),
                    "negative_evidence": "aggregate_empty_only_not_route_absence",
                }
            )
            for carrier in _prioritized_carriers(preferred_carriers, requested_controls):
                add(
                    {
                        "type": "carrier_aggregate",
                        "direction": direction,
                        "origin": route_origin,
                        "destination": route_destination,
                        "date": date_value.isoformat() if hasattr(date_value, "isoformat") else str(date_value),
                        "carrier": str(carrier).upper(),
                        "negative_evidence": "carrier_probe_empty_only_not_carrier_absence",
                    }
                )

    if coverage_mode == "full":
        for direction, route_origin, route_destination, date_value in directions:
            add(
                {
                    "type": "city_pair_direct",
                    "direction": direction,
                    "origin": route_origin,
                    "destination": route_destination,
                    "date": date_value.isoformat() if hasattr(date_value, "isoformat") else str(date_value),
                    "negative_evidence": "city_code_empty_only_not_route_absence",
                }
            )
    if coverage_control_limit is not None:
        controls = controls[: max(0, int(coverage_control_limit))]
    return controls
