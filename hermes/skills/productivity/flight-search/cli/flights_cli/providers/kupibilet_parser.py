from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..config import CARRIER_RE, KUPIBILET_FRONTEND_SEARCH_URL
from ..domain.carriers import carrier_from_flight_number
from ..domain.connection_policy import (
    airport_mismatch_violations,
    chronology_violations,
    missing_segment_time_violations,
)
from ..domain.normalize import normalize_airport_scope, price_value
from ..domain.offer_order import provider_offer_business_key
from ..domain.stop_policy import connection_count_for_segments
from ..errors import CliError


def kupibilet_price_amount(variant: dict[str, Any]) -> int | None:
    price = variant.get("price")
    if isinstance(price, dict):
        return price_value({"price": price.get("amount")})
    return price_value({"price": price})


def kupibilet_variant_currency(variant: dict[str, Any], default_currency: str) -> str:
    price = variant.get("price")
    if isinstance(price, dict) and isinstance(price.get("currency"), str):
        return price["currency"].upper()
    return default_currency


def kupibilet_flight_number(flight: dict[str, Any]) -> str:
    carrier = str(
        flight.get("marketing_carrier") or flight.get("operating_carrier") or ""
    ).upper()
    number = str(flight.get("transport_number") or flight.get("number") or "").strip()
    if carrier and number.upper().startswith(carrier):
        remainder = number[len(carrier) :].lstrip()
        if remainder[:1].isdigit():
            number = remainder
    return f"{carrier}{number}" if carrier or number else ""


def kupibilet_flight_carriers(flight: dict[str, Any]) -> set[str]:
    carriers: set[str] = set()
    for key in ("marketing_carrier", "operating_carrier"):
        value = flight.get(key)
        if isinstance(value, str) and value.strip():
            code = value.strip().upper()
            if CARRIER_RE.match(code):
                carriers.add(code)
    flight_number = kupibilet_flight_number(flight)
    carrier = carrier_from_flight_number(flight_number)
    if carrier:
        carriers.add(carrier)
    return carriers


def kupibilet_variant_flight_ids(variant: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for segment in variant.get("segments", []):
        if isinstance(segment, dict) and isinstance(segment.get("flights"), list):
            ids.extend(str(item) for item in segment["flights"] if item)
    return ids


def normalize_kupibilet_flight(raw: dict[str, Any]) -> dict[str, Any]:
    flight_number = kupibilet_flight_number(raw)
    return {
        "flight_number": flight_number,
        "marketing_carrier": str(raw.get("marketing_carrier") or "").upper(),
        "operating_carrier": str(raw.get("operating_carrier") or "").upper(),
        "origin": str(raw.get("departure") or "").upper(),
        "destination": str(raw.get("arrival") or "").upper(),
        "departure_terminal": str(raw.get("departure_terminal") or "").strip() or None,
        "arrival_terminal": str(raw.get("arrival_terminal") or "").strip() or None,
        "departure_at": str(raw.get("departure_datetime") or ""),
        "arrival_at": str(raw.get("arrival_datetime") or ""),
        "aircraft": raw.get("equipment"),
        "duration": raw.get("duration"),
        "transport_kind": raw.get("transport_kind"),
        "is_charter": raw.get("is_charter"),
    }


def kupibilet_total_duration(raw_flights: list[dict[str, Any]]) -> int | None:
    total = 0
    seen = False
    for flight in raw_flights:
        raw_duration = flight.get("duration")
        if raw_duration is None:
            continue
        try:
            duration = int(float(raw_duration))
        except (TypeError, ValueError):
            continue
        total += max(0, duration)
        seen = True
    return total if seen else None


def kupibilet_offer_key(flights: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(
        f"{flight.get('flight_number')}:{flight.get('departure_at')}:{flight.get('arrival_at')}"
        for flight in flights
    )


def parse_kupibilet_frontend_search(
    raw: dict[str, Any],
    *,
    origin: str,
    destination: str,
    depart_date: str,
    currency: str,
    only_carriers: list[str] | None = None,
    origin_airports: list[str] | None = None,
    destination_airports: list[str] | None = None,
    direct_only: bool = False,
    limit: int = 20,
) -> dict[str, Any]:
    variants = raw.get("variants") if isinstance(raw, dict) else None
    flights_by_id = raw.get("flights") if isinstance(raw, dict) else None
    if not isinstance(variants, list) or not isinstance(flights_by_id, dict):
        raise CliError(
            "Kupibilet response does not contain variants/flights maps",
            error_type="upstream_error",
        )

    carrier_filter = {
        code.strip().upper() for code in (only_carriers or []) if code.strip()
    }
    normalized_origin_airports = normalize_airport_scope(
        origin_airports, "origin-airport"
    )
    normalized_destination_airports = normalize_airport_scope(
        destination_airports, "destination-airport"
    )
    origin_scope = set(normalized_origin_airports)
    destination_scope = set(normalized_destination_airports)
    deduped: dict[tuple[str, ...], dict[str, Any]] = {}
    skipped = defaultdict(int)

    for index, variant in enumerate(variants):
        if not isinstance(variant, dict):
            skipped["bad_variant"] += 1
            continue
        flight_ids = kupibilet_variant_flight_ids(variant)
        if not flight_ids:
            skipped["no_flights"] += 1
            continue
        raw_flights = []
        for flight_id in flight_ids:
            raw_flight = flights_by_id.get(flight_id)
            if isinstance(raw_flight, dict):
                raw_flights.append(raw_flight)
        if len(raw_flights) != len(flight_ids):
            skipped["missing_flight_details"] += 1
            continue
        if any(flight.get("transport_kind") != "airplane" for flight in raw_flights):
            skipped["non_airplane"] += 1
            continue
        if direct_only and len(raw_flights) != 1:
            skipped["not_direct"] += 1
            continue
        if carrier_filter and not all(
            kupibilet_flight_carriers(flight) & carrier_filter for flight in raw_flights
        ):
            skipped["carrier"] += 1
            continue

        normalized_flights = [
            normalize_kupibilet_flight(flight) for flight in raw_flights
        ]
        actual_origin = str(normalized_flights[0].get("origin") or "").upper()
        actual_destination = str(
            normalized_flights[-1].get("destination") or ""
        ).upper()
        if not actual_origin or not actual_destination:
            skipped["missing_airport"] += 1
            continue
        if origin_scope and actual_origin not in origin_scope:
            skipped["origin_out_of_scope"] += 1
            continue
        if destination_scope and actual_destination not in destination_scope:
            skipped["destination_out_of_scope"] += 1
            continue
        key = kupibilet_offer_key(normalized_flights)
        if not key:
            skipped["empty_key"] += 1
            continue
        amount = kupibilet_price_amount(variant)
        offer = {
            "id": str(variant.get("id") or f"kupibilet:{index}"),
            "price": amount,
            "currency": kupibilet_variant_currency(variant, currency),
            "number_of_changes": connection_count_for_segments(normalized_flights),
            "duration": kupibilet_total_duration(raw_flights),
            "departure_at": normalized_flights[0]["departure_at"],
            "arrival_at": normalized_flights[-1]["arrival_at"],
            "origin": normalized_flights[0]["origin"],
            "destination": normalized_flights[-1]["destination"],
            "flight_numbers": [
                flight["flight_number"] for flight in normalized_flights
            ],
            "marketing_carriers": sorted(
                {
                    flight["marketing_carrier"]
                    for flight in normalized_flights
                    if flight["marketing_carrier"]
                }
            ),
            "operating_carriers": sorted(
                {
                    flight["operating_carrier"]
                    for flight in normalized_flights
                    if flight["operating_carrier"]
                }
            ),
            "segments": normalized_flights,
        }
        missing_times = missing_segment_time_violations(offer)
        if missing_times:
            skipped[str(missing_times[0]["reason"])] += 1
            continue
        reversed_segments = [
            violation
            for violation in chronology_violations(offer)
            if violation.get("reason") == "segment_arrival_before_departure"
        ]
        if reversed_segments:
            skipped[str(reversed_segments[0]["reason"])] += 1
            continue
        previous = deduped.get(key)
        previous_price = previous.get("price") if previous else None
        if previous is None or (
            amount is not None and (previous_price is None or amount < previous_price)
        ):
            deduped[key] = offer

    normalized_offers = list(deduped.values())
    continuous_offers = [
        offer for offer in normalized_offers if not airport_mismatch_violations(offer)
    ]
    suppressed_airport_change_count = len(normalized_offers) - len(continuous_offers)
    offers = sorted(continuous_offers, key=provider_offer_business_key)[: max(0, limit)]
    return {
        "origin": origin,
        "destination": destination,
        "depart_date": depart_date,
        "currency": currency,
        "source": "Kupibilet frontend_search (live aggregate)",
        "source_url": KUPIBILET_FRONTEND_SEARCH_URL,
        "note": "Live aggregate source, not official aeroflot.ru; recheck final fare and seat availability before ticketing.",
        "filters": {
            "only_carriers": sorted(carrier_filter),
            "origin_airports": normalized_origin_airports,
            "destination_airports": normalized_destination_airports,
            "direct_only": direct_only,
            "dedupe": "flight_numbers+times",
        },
        "raw_variant_count": len(variants),
        "skipped": dict(skipped),
        "offer_count": len(offers),
        "unique_flight_count": len(continuous_offers),
        "raw_offer_count": len(normalized_offers),
        "suppressed_airport_change_count": suppressed_airport_change_count,
        "offers": offers,
    }


__all__ = [
    "kupibilet_flight_carriers",
    "kupibilet_flight_number",
    "kupibilet_offer_key",
    "kupibilet_price_amount",
    "kupibilet_total_duration",
    "kupibilet_variant_currency",
    "kupibilet_variant_flight_ids",
    "normalize_kupibilet_flight",
    "parse_kupibilet_frontend_search",
]
