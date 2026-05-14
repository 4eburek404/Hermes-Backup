from __future__ import annotations

from typing import Any

from ..config import PRIORITY_MOSCOW_GATEWAY, PRIORITY_PRIMARY_HUB
from ..domain.normalize import currency_value, price_value

def segment_result_matches(result: dict[str, Any], direction: str, leg: str, origin: str, destination: str) -> bool:
    query = result.get("query") if isinstance(result.get("query"), dict) else {}
    return (
        result.get("direction") == direction
        and result.get("leg") == leg
        and str(query.get("origin") or "").upper() == origin
        and str(query.get("destination") or "").upper() == destination
    )
def combined_offer(first: dict[str, Any], second: dict[str, Any], *, direction: str, leg: str, index: int) -> dict[str, Any] | None:
    first_arrival = str(first.get("arrival_airport") or first.get("destination") or "").upper()
    second_departure = str(second.get("departure_airport") or second.get("origin") or "").upper()
    if not first_arrival or first_arrival != second_departure:
        return None
    first_segments = [segment for segment in (first.get("segments") or []) if isinstance(segment, dict)]
    second_segments = [segment for segment in (second.get("segments") or []) if isinstance(segment, dict)]
    segments = first_segments + second_segments
    if len(segments) < 2:
        return None
    price = 0
    has_price = False
    for offer in (first, second):
        value = price_value(offer)
        if value is not None:
            price += value
            has_price = True
    currency = currency_value(first) or currency_value(second)
    return {
        "id": f"synthetic:{direction}:{leg}:{segments[0]['origin']}-{segments[-1]['destination']}:{index}",
        "direction": direction,
        "leg": leg,
        "query_origin": segments[0]["origin"],
        "query_destination": segments[-1]["destination"],
        "query_date": str(first.get("query_date") or ""),
        "origin": segments[0]["origin"],
        "destination": segments[-1]["destination"],
        "departure_airport": segments[0]["origin"],
        "arrival_airport": segments[-1]["destination"],
        "departure_at": segments[0].get("departure_at"),
        "arrival_at": segments[-1].get("arrival_at"),
        "price": price if has_price else None,
        "currency": currency,
        "carrier": segments[0].get("carrier"),
        "main_airline": segments[0].get("carrier"),
        "changes": 1,
        "duration_min": None,
        "source": "Kupibilet synthesized Moscow gateway control",
        "segments": segments,
        "transfers": [],
        "internal_connection_count": max(0, len(segments) - 1),
        "synthetic": True,
        "source_offers": [
            {"id": first.get("id"), "origin": first.get("origin"), "destination": first.get("destination")},
            {"id": second.get("id"), "origin": second.get("origin"), "destination": second.get("destination")},
        ],
    }
def synthesize_moscow_gateway_control_results(
    plan: dict[str, Any],
    segment_results: list[dict[str, Any]],
    directions: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if plan.get("routing_strategy") != "ru-priority":
        return [], []

    synthetic_results: list[dict[str, Any]] = []
    synthetic_searches: list[dict[str, Any]] = []

    final_destination_airports = {str(code).upper() for code in (plan.get("destination_airports") or [])}
    if not final_destination_airports and plan.get("destination"):
        final_destination_airports.add(str(plan.get("destination")).upper())

    def synthesize(
        *,
        direction: str,
        direct_leg: str,
        first_leg: str,
        second_leg: str,
        origin: str,
        gateway: str,
        destination: str,
    ) -> None:
        # P1: Moscow is a control, not a fallback. Keep synthesized via-SVO
        # alternatives even when a direct/primary-hub probe already has offers.
        first_results = [
            result
            for result in segment_results
            if segment_result_matches(result, direction, first_leg, origin, gateway)
        ]
        second_results = [
            result
            for result in segment_results
            if segment_result_matches(result, direction, second_leg, gateway, destination)
        ]
        offers: list[dict[str, Any]] = []
        for first_result in first_results:
            for first_offer in first_result.get("offers") or []:
                if not isinstance(first_offer, dict):
                    continue
                for second_result in second_results:
                    for second_offer in second_result.get("offers") or []:
                        if not isinstance(second_offer, dict):
                            continue
                        offer = combined_offer(first_offer, second_offer, direction=direction, leg=direct_leg, index=len(offers) + 1)
                        if offer is not None:
                            offers.append(offer)
        if not offers:
            return
        query_date = str(offers[0].get("query_date") or "")
        synthetic_results.append(
            {
                "direction": direction,
                "leg": direct_leg,
                "query": {
                    "origin": origin,
                    "destination": destination,
                    "date": query_date,
                    "currency": plan["currency"],
                },
                "source_key": "synthetic_moscow_gateway_control",
                "source": "Kupibilet synthesized Moscow gateway control",
                "raw_count": len(offers),
                "parse_errors": 0,
                "offers": offers,
                "synthetic": True,
            }
        )
        synthetic_searches.append(
            {
                "direction": direction,
                "leg": direct_leg,
                "origin": origin,
                "destination": destination,
                "date": query_date,
                "status": "synthetic",
                "route_family": "moscow_gateway_control",
                "offer_count": len(offers),
                "source_legs": [first_leg, second_leg],
            }
        )

    for origin in plan.get("origin_airports") or []:
        if (directions is None or "outbound" in directions) and origin != PRIORITY_MOSCOW_GATEWAY:
            synthesize(
                direction="outbound",
                direct_leg="origin_to_hub",
                first_leg="origin_to_gateway",
                second_leg="gateway_to_hub",
                origin=origin,
                gateway=PRIORITY_MOSCOW_GATEWAY,
                destination=PRIORITY_PRIMARY_HUB,
            )
            if PRIORITY_PRIMARY_HUB in final_destination_airports:
                synthesize(
                    direction="outbound",
                    direct_leg="direct_outbound",
                    first_leg="origin_to_gateway",
                    second_leg="gateway_to_hub",
                    origin=origin,
                    gateway=PRIORITY_MOSCOW_GATEWAY,
                    destination=PRIORITY_PRIMARY_HUB,
                )
        if (directions is None or "return" in directions) and plan["dates"].get("return") and origin != PRIORITY_MOSCOW_GATEWAY:
            synthesize(
                direction="return",
                direct_leg="hub_to_origin",
                first_leg="hub_to_gateway",
                second_leg="gateway_to_origin",
                origin=PRIORITY_PRIMARY_HUB,
                gateway=PRIORITY_MOSCOW_GATEWAY,
                destination=origin,
            )
            if PRIORITY_PRIMARY_HUB in final_destination_airports:
                synthesize(
                    direction="return",
                    direct_leg="direct_return",
                    first_leg="hub_to_gateway",
                    second_leg="gateway_to_origin",
                    origin=PRIORITY_PRIMARY_HUB,
                    gateway=PRIORITY_MOSCOW_GATEWAY,
                    destination=origin,
                )

    return synthetic_results, synthetic_searches
