from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from ..config import RISK_PROFILES
from .normalize import clamp_score, normalize_profile

RouteIndex = dict[str, dict[str, list[dict[str, Any]]]]


def route_airline(route: dict[str, Any]) -> str | None:
    code = str(route.get("airline_iata") or "").upper()
    return code or None


def build_route_index(routes: list[dict[str, Any]]) -> RouteIndex:
    index: RouteIndex = defaultdict(lambda: defaultdict(list))
    for route in routes:
        origin = str(route.get("departure_airport_iata") or "").upper()
        destination = str(route.get("arrival_airport_iata") or "").upper()
        if not origin or not destination or origin == destination:
            continue
        transfers = route.get("transfers")
        if transfers not in (None, 0):
            continue
        index[origin][destination].append(route)
    return {origin: dict(destinations) for origin, destinations in index.items()}


def airport_coordinates(store: Store, code: str) -> tuple[float, float] | None:
    airport = store.airport_by_code.get(code.upper())
    if not airport:
        return None
    coordinates = airport.get("coordinates")
    if not isinstance(coordinates, dict):
        return None
    lat = coordinates.get("lat")
    lon = coordinates.get("lon")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None
    return float(lat), float(lon)


def distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    hav = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0 * 2 * math.atan2(math.sqrt(hav), math.sqrt(1 - hav))


def distance_summary(store: Store, origin: str, hub: str, destination: str) -> dict[str, Any]:
    origin_coord = airport_coordinates(store, origin)
    hub_coord = airport_coordinates(store, hub)
    dest_coord = airport_coordinates(store, destination)
    if not origin_coord or not hub_coord or not dest_coord:
        return {
            "direct_km": None,
            "via_hub_km": None,
            "detour_ratio": None,
        }
    direct = distance_km(origin_coord, dest_coord)
    via = distance_km(origin_coord, hub_coord) + distance_km(hub_coord, dest_coord)
    ratio = via / direct if direct else None
    return {
        "direct_km": round(direct),
        "via_hub_km": round(via),
        "detour_ratio": round(ratio, 3) if ratio is not None else None,
    }


def route_carriers(routes: list[dict[str, Any]]) -> list[str]:
    return sorted({carrier for route in routes if (carrier := route_airline(route))})


def lowcost_carriers(store: Store, carriers: list[str]) -> list[str]:
    lowcost: list[str] = []
    for carrier in carriers:
        airline = store.airline_by_code.get(carrier)
        if airline and airline.get("is_lowcost") is True:
            lowcost.append(carrier)
    return sorted(lowcost)


def shared_alliances(store: Store, first_leg_carriers: list[str], second_leg_carriers: list[str]) -> list[str]:
    first = {
        alliance
        for carrier in first_leg_carriers
        for alliance in store.alliances_by_airline.get(carrier, [])
    }
    second = {
        alliance
        for carrier in second_leg_carriers
        for alliance in store.alliances_by_airline.get(carrier, [])
    }
    return sorted(first & second)


def airport_quality(store: Store, code: str) -> dict[str, Any]:
    airport = store.airport_by_code.get(code.upper())
    if not airport:
        return {
            "known": False,
            "flightable": None,
            "iata_type": None,
            "time_zone": None,
            "country_code": None,
        }
    return {
        "known": True,
        "flightable": airport.get("flightable"),
        "iata_type": airport.get("iata_type"),
        "time_zone": airport.get("time_zone"),
        "country_code": airport.get("country_code"),
    }


def score_hub_candidate(
    store: Store,
    *,
    origin: str,
    hub: str,
    destination: str,
    origin_to_hub: list[dict[str, Any]],
    hub_to_destination: list[dict[str, Any]],
    profile: str,
) -> dict[str, Any]:
    profile_config = RISK_PROFILES[profile]
    first_carriers = route_carriers(origin_to_hub)
    second_carriers = route_carriers(hub_to_destination)
    all_carriers = sorted(set(first_carriers + second_carriers))
    lowcost = lowcost_carriers(store, all_carriers)
    alliances = shared_alliances(store, first_carriers, second_carriers)
    distances = distance_summary(store, origin, hub, destination)
    hub_quality = airport_quality(store, hub)

    score = 60
    reasons: list[str] = []
    route_evidence = len(origin_to_hub) + len(hub_to_destination)
    evidence_bonus = min(18, route_evidence * 2)
    score += evidence_bonus
    reasons.append(f"route evidence across both legs: {route_evidence}")

    if hub_quality["flightable"] is True and hub_quality["iata_type"] == "airport":
        score += 8
        reasons.append("hub is a flightable airport")
    elif hub_quality["known"] is False:
        score -= 8
        reasons.append("hub metadata is missing")
    else:
        score -= 12
        reasons.append("hub is not clearly a flightable airport")

    ratio = distances.get("detour_ratio")
    if isinstance(ratio, float):
        if ratio <= 1.25:
            score += 8
            reasons.append("low geographic detour")
        elif ratio <= 1.65:
            score -= int((ratio - 1.25) * 20)
            reasons.append("moderate geographic detour")
        else:
            score -= min(35, int((ratio - 1.0) * 22))
            reasons.append("large geographic detour")

    if alliances:
        score += 8
        reasons.append(f"shared alliance evidence: {', '.join(alliances)}")

    if lowcost:
        lowcost_penalty = int(profile_config["lowcost_penalty"])
        score -= lowcost_penalty * (2 if set(all_carriers) == set(lowcost) else 1)
        reasons.append(f"low-cost carrier evidence: {', '.join(lowcost)}")

    unpreferred = profile_config.get("unpreferred_airport_penalty", {})
    if isinstance(unpreferred, dict) and hub in unpreferred:
        score -= int(unpreferred[hub])
        reasons.append(f"profile airport penalty for {hub}")

    return {
        "hub": hub,
        "score": clamp_score(score),
        "best_pair": {
            "origin": origin,
            "destination": destination,
        },
        "distance": distances,
        "evidence": {
            "origin_to_hub_routes": len(origin_to_hub),
            "hub_to_destination_routes": len(hub_to_destination),
            "origin_to_hub_carriers": first_carriers,
            "hub_to_destination_carriers": second_carriers,
            "codeshare_routes": sum(1 for route in origin_to_hub + hub_to_destination if route.get("codeshare") is True),
            "planes": sorted(
                {
                    str(plane)
                    for route in origin_to_hub + hub_to_destination
                    for plane in (route.get("planes") if isinstance(route.get("planes"), list) else [])
                    if plane
                }
            ),
        },
        "quality": {
            "hub": hub_quality,
            "lowcost_carriers": lowcost,
            "shared_alliances": alliances,
        },
        "reasons": reasons,
    }


def find_route_graph_candidates(
    store: Store,
    origin_airports: list[str],
    destination_airports: list[str],
    *,
    profile: str,
    max_hubs: int,
) -> dict[str, Any]:
    routes = store.routes
    if not routes:
        return {
            "available": False,
            "source": "routes.json",
            "source_note": "routes.json is absent from the local cache",
            "direct": [],
            "one_stop_hubs": [],
        }

    normalized_profile = normalize_profile(profile)
    index = build_route_index(routes)
    direct: list[dict[str, Any]] = []
    hub_candidates: dict[str, dict[str, Any]] = {}

    for origin in origin_airports:
        for destination in destination_airports:
            direct_routes = index.get(origin, {}).get(destination, [])
            if direct_routes:
                direct.append(
                    {
                        "origin": origin,
                        "destination": destination,
                        "route_count": len(direct_routes),
                        "carriers": route_carriers(direct_routes),
                    }
                )

            origin_edges = index.get(origin, {})
            for hub, first_leg_routes in origin_edges.items():
                if hub in set(origin_airports) or hub in set(destination_airports):
                    continue
                second_leg_routes = index.get(hub, {}).get(destination, [])
                if not second_leg_routes:
                    continue
                candidate = score_hub_candidate(
                    store,
                    origin=origin,
                    hub=hub,
                    destination=destination,
                    origin_to_hub=first_leg_routes,
                    hub_to_destination=second_leg_routes,
                    profile=normalized_profile,
                )
                existing = hub_candidates.get(hub)
                if existing is None or candidate["score"] > existing["score"]:
                    hub_candidates[hub] = candidate

    hubs = sorted(
        hub_candidates.values(),
        key=lambda item: (
            -int(item["score"]),
            item["distance"].get("detour_ratio") if item["distance"].get("detour_ratio") is not None else 999,
            item["hub"],
        ),
    )
    if max_hubs > 0:
        hubs = hubs[:max_hubs]
    return {
        "available": True,
        "source": "routes.json",
        "source_note": "routes.json is a historical topology prior, not a current schedule source.",
        "direct": sorted(direct, key=lambda item: (item["origin"], item["destination"])),
        "one_stop_hubs": hubs,
    }
