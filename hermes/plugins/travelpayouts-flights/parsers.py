"""Parse Travelpayouts GraphQL responses into local flight models."""
from __future__ import annotations

from datetime import date
from typing import Any

from .models import FlightLeg, FlightPrice, FlightSegment, Transfer


def _time_only(iso_dt: str) -> str:
    if "T" in (iso_dt or ""):
        return iso_dt.split("T", 1)[1][:5]
    return ""


def _date_from_iso_datetime(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value.split("T", 1)[0])


def parse_segment(segment_data: dict[str, Any]) -> FlightSegment:
    return FlightSegment(
        departure_at=str(segment_data.get("departure_at") or ""),
        arrival_at=str(segment_data.get("arrival_at") or ""),
        flight_legs=[FlightLeg.from_dict(leg) for leg in segment_data.get("flight_legs", []) if isinstance(leg, dict)],
        transfers=[Transfer.from_dict(t) for t in segment_data.get("transfers", []) if isinstance(t, dict)],
    )


def parse_graphql_flight(flight_data: dict[str, Any], origin: str, destination: str) -> FlightPrice:
    departure_at = str(flight_data.get("departure_at") or "")
    return_at = flight_data.get("return_at")
    depart_date = _date_from_iso_datetime(departure_at)
    if depart_date is None:
        raise ValueError("missing departure_at")
    return_date = _date_from_iso_datetime(return_at) if return_at else None

    segments_data = flight_data.get("segments") or []
    if not isinstance(segments_data, list):
        segments_data = []
    outbound_segment = parse_segment(segments_data[0]) if segments_data else None
    return_segment = parse_segment(segments_data[1]) if len(segments_data) > 1 else None

    flight_number = None
    if outbound_segment and outbound_segment.flight_legs:
        fn_str = outbound_segment.flight_legs[0].flight_number
        digits = "".join(filter(str.isdigit, fn_str))
        flight_number = int(digits) if digits else None

    return FlightPrice(
        origin=origin,
        destination=destination,
        depart_date=depart_date,
        return_date=return_date,
        price=int(float(flight_data.get("value") or 0)),
        airline=flight_data.get("main_airline"),
        flight_number=flight_number,
        transfers=int(flight_data.get("number_of_changes") or 0),
        departure_at=departure_at,
        return_at=str(return_at) if return_at else None,
        expires_at=None,
        trip_duration=flight_data.get("trip_duration"),
        duration=flight_data.get("duration"),
        ticket_link=flight_data.get("ticket_link"),
        outbound_segment=outbound_segment,
        return_segment=return_segment,
    )


def flight_dedup_key(flight: FlightPrice) -> str:
    parts: list[str] = []
    if flight.outbound_segment:
        for leg in flight.outbound_segment.flight_legs:
            parts.append(f"{leg.flight_number}_{_time_only(leg.departure_at)}_{_time_only(leg.arrival_at)}")
    if flight.return_segment:
        for leg in flight.return_segment.flight_legs:
            parts.append(f"{leg.flight_number}_{_time_only(leg.departure_at)}_{_time_only(leg.arrival_at)}")
    return "|".join(parts) if parts else flight.departure_at or ""
