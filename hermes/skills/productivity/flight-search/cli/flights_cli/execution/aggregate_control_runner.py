from __future__ import annotations

import argparse
from typing import Any

from ..config import DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS
from ..domain.carriers import carrier_from_flight_number
from ..domain.normalize import normalize_carrier_code, parse_iso_date
from ..domain.provider_offer_filter import MAX_MODEL_CONNECTIONS, filter_provider_offers
from ..domain.stop_metrics import offer_stop_metrics
from ..errors import CliError
from ..providers.kupibilet import cached_kupibilet_search, fetch_kupibilet_search
from .cache_status import cache_status_from_result
from .failure_classifier import error_payload_from_cli_error

def aggregate_offer_summary(offer: dict[str, Any]) -> dict[str, Any]:
    flights = [flight for flight in (offer.get("flights") or []) if isinstance(flight, dict)]
    carriers: set[str] = set()
    segments = []
    for flight in flights:
        flight_number = str(flight.get("flight_number") or "")
        marketing = str(flight.get("marketing_carrier") or "").upper()
        operating = str(flight.get("operating_carrier") or "").upper()
        carrier = operating or marketing or carrier_from_flight_number(flight_number)
        if carrier:
            carriers.add(carrier)
        segments.append(
            {
                "flight_number": flight_number or None,
                "carrier": carrier or None,
                "marketing_carrier": marketing or None,
                "operating_carrier": operating or None,
                "origin": flight.get("origin"),
                "destination": flight.get("destination"),
                "departure_at": flight.get("departure_at"),
                "arrival_at": flight.get("arrival_at"),
            }
        )
    airport_mismatches = []
    for previous, current in zip(segments, segments[1:]):
        previous_arrival = str(previous.get("destination") or "").upper()
        current_departure = str(current.get("origin") or "").upper()
        if previous_arrival and current_departure and previous_arrival != current_departure:
            airport_mismatches.append(
                {
                    "arrival_airport": previous_arrival,
                    "departure_airport": current_departure,
                    "warning": "provider aggregate offer changes airport between consecutive flights; verify ground transfer and ticket protection",
                }
            )
    stop_metrics = offer_stop_metrics(offer)
    return {
        "id": offer.get("id"),
        "price": offer.get("price"),
        "currency": offer.get("currency"),
        "change_count": offer.get("number_of_changes"),
        "connection_count": stop_metrics["max_connections_per_journey"],
        "stop_tier": stop_metrics["stop_tier"],
        "reportable_by_stop_policy": stop_metrics["max_connections_per_journey"] <= MAX_MODEL_CONNECTIONS,
        "duration_min": offer.get("duration"),
        "flight_numbers": offer.get("flight_numbers") or [segment.get("flight_number") for segment in segments if segment.get("flight_number")],
        "carriers": sorted(carriers),
        "segments": segments,
        "airport_mismatch_count": len(airport_mismatches),
        "airport_mismatches": airport_mismatches,
        "ticketing_note": "Provider-assembled route offer; verify single-PNR/protection, baggage, and final fare on the booking screen.",
    }


def aggregate_control_summary(
    *,
    direction: str,
    origin: str,
    destination: str,
    depart_date: str,
    carriers: list[str],
    result: dict[str, Any],
) -> dict[str, Any]:
    offers = [offer for offer in (result.get("offers") or []) if isinstance(offer, dict)]
    filtered_offers, filter_stats = filter_provider_offers(offers)
    return {
        "direction": direction,
        "origin": origin,
        "destination": destination,
        "date": depart_date,
        "status": "ok",
        "provider": "kupibilet",
        "source": result.get("source"),
        "filters": {"direct_only": False, "only_carriers": carriers},
        "offer_count": len(filtered_offers),
        "raw_offer_count": result.get("raw_offer_count", filter_stats["raw_offer_count"]),
        "suppressed_three_plus_count": int(result.get("suppressed_three_plus_count") or 0)
        + filter_stats["suppressed_three_plus_count"],
        "suppressed_airport_change_count": int(result.get("suppressed_airport_change_count") or 0)
        + filter_stats["suppressed_airport_change_count"],
        "raw_variant_count": result.get("raw_variant_count"),
        "unique_flight_count": result.get("unique_flight_count"),
        "cache": result.get("cache", {"hit": False}),
        "cache_status": cache_status_from_result(result),
        "top_offers": [aggregate_offer_summary(offer) for offer in filtered_offers],
    }


def run_aggregate_controls(args: argparse.Namespace, plan: dict[str, Any], kupibilet_fetcher: Any = fetch_kupibilet_search) -> list[dict[str, Any]]:
    limit = max(0, int(getattr(args, "aggregate_control_limit", 0) or 0))
    if limit <= 0:
        return []

    carrier_sets: list[list[str]] = []
    base_carriers = [normalize_carrier_code(code, "only-carrier") for code in (getattr(args, "only_carrier", None) or [])]
    explicit_control_carriers = [
        [normalize_carrier_code(code, "aggregate-control-carrier")]
        for code in (getattr(args, "aggregate_control_carrier", None) or [])
    ]
    if base_carriers:
        carrier_sets.append(base_carriers)
    elif not explicit_control_carriers:
        carrier_sets.append([])
    for carriers in explicit_control_carriers:
        if carriers not in carrier_sets:
            carrier_sets.append(carriers)

    queries = [
        ("outbound", str(plan["origin"]).upper(), str(plan["destination"]).upper(), str(plan["dates"]["depart"])),
    ]
    if plan["dates"].get("return"):
        queries.append(("return", str(plan["destination"]).upper(), str(plan["origin"]).upper(), str(plan["dates"]["return"])))

    controls: list[dict[str, Any]] = []
    cache_ttl_seconds = int(getattr(args, "live_cache_ttl_seconds", DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS))
    use_live_cache = not bool(getattr(args, "no_live_cache", False))
    for direction, origin, destination, date_text in queries:
        depart_date = parse_iso_date(date_text, "aggregate-control-date")
        for carriers in carrier_sets:
            try:
                result = cached_kupibilet_search(
                    origin,
                    destination,
                    depart_date,
                    currency=str(plan["currency"]).upper(),
                    only_carriers=carriers,
                    direct_only=False,
                    limit=limit,
                    timeout=int(getattr(args, "timeout", 60)),
                    cache_ttl_seconds=cache_ttl_seconds,
                    use_cache=use_live_cache,
                    fetcher=kupibilet_fetcher,
                )
            except CliError as exc:
                controls.append(
                    {
                        "direction": direction,
                        "origin": origin,
                        "destination": destination,
                        "date": date_text,
                        "status": "error",
                        "provider": "kupibilet",
                        "filters": {"direct_only": False, "only_carriers": carriers},
                        "offer_count": 0,
                        "raw_offer_count": 0,
                        "suppressed_three_plus_count": 0,
                        "suppressed_airport_change_count": 0,
                        "cache_status": "unknown",
                        "error": error_payload_from_cli_error(exc),
                    }
                )
                continue
            controls.append(
                aggregate_control_summary(
                    direction=direction,
                    origin=origin,
                    destination=destination,
                    depart_date=date_text,
                    carriers=carriers,
                    result=result,
                )
            )
    return controls
