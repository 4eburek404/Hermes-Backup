from __future__ import annotations

from typing import Any

from ..config import DEFAULT_CURRENCY
from ..domain.carriers import carrier_from_flight_number
from ..domain.normalize import price_value
from ..domain.stop_policy import connection_count_for_segments


def normalize_segment_flight(flight: dict[str, Any]) -> dict[str, Any] | None:
    origin = str(flight.get("origin") or "").upper()
    destination = str(flight.get("destination") or "").upper()
    if not origin or not destination:
        return None
    flight_number = str(flight.get("flight_number") or "")
    operating = str(flight.get("operating_carrier") or "").upper()
    marketing = str(flight.get("marketing_carrier") or "").upper()
    carrier = operating or marketing or carrier_from_flight_number(flight_number)
    return {
        "origin": origin,
        "destination": destination,
        "departure_terminal": str(flight.get("departure_terminal") or "").strip()
        or None,
        "arrival_terminal": str(flight.get("arrival_terminal") or "").strip() or None,
        "departure_at": str(flight.get("departure_at") or ""),
        "arrival_at": str(flight.get("arrival_at") or ""),
        "carrier": carrier,
        "flight_number": flight_number or None,
        "marketing_carrier": marketing or None,
        "operating_carrier": operating or None,
        "carrier_name": str(flight.get("carrier_name") or "").strip() or None,
        "aircraft_code": flight.get("aircraft"),
        "duration_min": flight.get("duration"),
    }


def provider_offer_to_segment_offer(
    offer: dict[str, Any],
    *,
    provider_prefix: str,
    source_label: str,
    direction: str,
    leg: str,
    query_origin: str,
    query_destination: str,
    query_date: str,
    currency: str,
    index: int,
) -> dict[str, Any] | None:
    raw_flights = offer.get("segments")
    if not isinstance(raw_flights, list) or not raw_flights:
        return None
    segments: list[dict[str, Any]] = []
    for flight in raw_flights:
        if not isinstance(flight, dict):
            continue
        normalized = normalize_segment_flight(flight)
        if normalized is not None:
            segments.append(normalized)
    if not segments:
        return None
    offer_id = f"{provider_prefix}:{direction}:{leg}:{query_origin}-{query_destination}:{query_date}:{offer.get('id') or index}"
    currency_value = (
        offer.get("currency") if isinstance(offer.get("currency"), str) else currency
    )
    return {
        "id": offer_id,
        "direction": direction,
        "leg": leg,
        "query_origin": query_origin,
        "query_destination": query_destination,
        "query_date": query_date,
        "origin": segments[0]["origin"],
        "destination": segments[-1]["destination"],
        "departure_airport": segments[0]["origin"],
        "arrival_airport": segments[-1]["destination"],
        "departure_at": segments[0]["departure_at"],
        "arrival_at": segments[-1]["arrival_at"],
        "price": price_value({"price": offer.get("price")}),
        "currency": currency_value,
        "carrier": segments[0].get("carrier"),
        "main_airline": segments[0].get("carrier"),
        "changes": offer.get("number_of_changes"),
        "duration_min": offer.get("duration"),
        "source": source_label,
        "segments": segments,
        "transfers": [],
        "internal_connection_count": connection_count_for_segments(segments),
        **{
            key: offer.get(key)
            for key in (
                "ticketing_model",
                "self_transfer",
                "self_transfer_note",
                "self_transfer_source",
            )
            if key in offer
        },
    }


def provider_result_to_segment_result(
    result: dict[str, Any],
    *,
    direction: str,
    leg: str,
    source_key: str,
    source_label: str,
    provider_prefix: str,
    raw_count_key: str,
) -> dict[str, Any]:
    query_origin = str(result.get("origin") or "").upper()
    query_destination = str(result.get("destination") or "").upper()
    query_date = str(result.get("depart_date") or "")
    currency = str(result.get("currency") or DEFAULT_CURRENCY).upper()
    offers = []
    parse_errors = 0
    for index, offer in enumerate(result.get("offers") or []):
        if not isinstance(offer, dict):
            parse_errors += 1
            continue
        normalized = provider_offer_to_segment_offer(
            offer,
            provider_prefix=provider_prefix,
            source_label=source_label,
            direction=direction,
            leg=leg,
            query_origin=query_origin,
            query_destination=query_destination,
            query_date=query_date,
            currency=currency,
            index=index,
        )
        if normalized is None:
            parse_errors += 1
            continue
        offers.append(normalized)
    return {
        "direction": direction,
        "leg": leg,
        "query": {
            "origin": query_origin,
            "destination": query_destination,
            "date": query_date,
            "currency": currency,
        },
        "source_key": source_key,
        "source": result.get("source"),
        "source_url": result.get("source_url"),
        "raw_count": result.get(raw_count_key),
        "unique_flight_count": result.get("unique_flight_count"),
        "parse_errors": parse_errors,
        "offers": offers,
    }
