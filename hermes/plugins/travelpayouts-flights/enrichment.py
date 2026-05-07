# enrichment.py
"""Pipeline: enrich raw FlightPrice data with human-readable names from caches.

Adapted from bot/modules/flights/web_handlers.py:
  - _duration_min()
  - _resolve_airport_name()
  - _build_segment()
  - _build_booking_url() (partial — Aviasales fallback separate)
  - _flight_to_out()
"""
from __future__ import annotations

import os
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from .cache import get_airlines_cache, get_airports_cache, get_cities_cache, get_planes_cache
from .formatters import format_time, format_date, format_duration, format_transfer, format_price, format_transfers_count
from .models import FlightPrice, FlightSegment
from .schemas_enriched import FlightOut, LegOut, SegmentOut, TransferOut

# Aviasales base URL for fallback booking links
_AVIASALES_BASE = "https://www.aviasales.ru"


def duration_min(dep: str, arr: str) -> int:
    """Minutes between two ISO datetime strings."""
    try:
        d = datetime.fromisoformat(dep.replace("Z", "+00:00"))
        a = datetime.fromisoformat(arr.replace("Z", "+00:00"))
        return max(0, int((a - d).total_seconds()) // 60)
    except (ValueError, TypeError):
        return 0


def resolve_airport_name(code: str, airports_cache, cities_cache) -> str:
    """Resolve airport IATA code to 'City (CODE)'.

    Chain: airport_code → Airport → city_code → City → city.name.
    Fallback: IATA code if resolution fails.
    """
    airport = airports_cache.get_by_code(code)
    if not airport:
        return code
    city = cities_cache.get_by_code(airport.city_code)
    if city:
        return f"{city.name} ({code})"
    if airport.name:
        return f"{airport.name} ({code})"
    return code


def build_segment(
    seg: FlightSegment,
    airlines_cache,
    airports_cache,
    cities_cache,
    planes_cache,
) -> SegmentOut:
    """Enrich a FlightSegment into SegmentOut with human-readable names."""
    legs = [
        LegOut(
            origin=leg.origin,
            destination=leg.destination,
            origin_name=resolve_airport_name(leg.origin, airports_cache, cities_cache),
            destination_name=resolve_airport_name(leg.destination, airports_cache, cities_cache),
            flight_number=leg.flight_number,
            carrier=leg.operating_carrier,
            carrier_name=airlines_cache.get_name(leg.operating_carrier),
            departure_at=leg.departure_at,
            arrival_at=leg.arrival_at,
            departure_formatted=format_time(leg.departure_at),
            arrival_formatted=format_time(leg.arrival_at),
            aircraft_code=leg.aircraft_code,
            aircraft_name=planes_cache.get_name(leg.aircraft_code),
            duration_min=duration_min(leg.departure_at, leg.arrival_at),
        )
        for leg in seg.flight_legs
    ]
    transfers = [
        TransferOut(
            airport=t.at,
            airport_name=resolve_airport_name(t.at, airports_cache, cities_cache),
            country_code=t.country_code,
            duration_min=t.duration_seconds // 60,
            night_transfer=t.night_transfer,
            visa_required=t.visa_required,
            formatted=format_transfer(
                airport_name=resolve_airport_name(t.at, airports_cache, cities_cache),
                duration_min=t.duration_seconds // 60,
                night_transfer=t.night_transfer,
                visa_required=t.visa_required,
            ),
        )
        for t in seg.transfers
    ]
    seg_duration = duration_min(seg.departure_at, seg.arrival_at)
    return SegmentOut(
        departure_at=seg.departure_at,
        arrival_at=seg.arrival_at,
        duration_min=seg_duration,
        duration_formatted=format_duration(seg_duration),
        transfers_count=len(seg.transfers),
        legs=legs,
        transfers=transfers,
        departure_formatted=f"{format_time(seg.departure_at)}, {format_date(seg.departure_at)}",
        arrival_formatted=f"{format_time(seg.arrival_at)}, {format_date(seg.arrival_at)}",
    )


def build_aviasales_fallback_url(origin: str, destination: str, depart_date, return_date=None) -> str:
    """Build an Aviasales partner link from IATA codes and dates.

    Adapted from formatters.py: _build_aviasales_url().
    Format: https://www.aviasales.ru/search/{origin}{DDMM}{destination}{DDMM}{trip_type}
    """
    dep_str = depart_date.strftime("%d%m")
    trip_type = "1" if return_date is None else ""
    if return_date:
        ret_str = return_date.strftime("%d%m")
        path = f"{origin}{dep_str}{destination}{ret_str}{trip_type}"
    else:
        path = f"{origin}{dep_str}{destination}1"

    url = f"{_AVIASALES_BASE}/search/{path}"
    marker = os.getenv("TRAVELPAYOUTS_MARKER")
    if marker:
        url += f"?marker={marker}"
    return url


def flight_to_out(
    flight: FlightPrice,
    currency: str,
    airlines_cache=None,
    airports_cache=None,
    cities_cache=None,
    planes_cache=None,
    marker: str | None = None,
) -> FlightOut:
    """Enrich a FlightPrice into FlightOut with human-readable names and booking URL.

    Caches are lazily loaded if not provided.
    """
    # Lazy-load caches if not passed
    if airlines_cache is None:
        airlines_cache = get_airlines_cache()
    if airports_cache is None:
        airports_cache = get_airports_cache()
    if cities_cache is None:
        cities_cache = get_cities_cache()
    if planes_cache is None:
        planes_cache = get_planes_cache()

    outbound = build_segment(flight.outbound_segment, airlines_cache, airports_cache, cities_cache, planes_cache) if flight.outbound_segment else None
    inbound = build_segment(flight.return_segment, airlines_cache, airports_cache, cities_cache, planes_cache) if flight.return_segment else None

    # Booking URL: ticket_link (with marker) or Aviasales fallback
    booking_url = _resolve_booking_url(flight, marker)

    result = FlightOut(
        price=flight.price,
        currency=currency,
        airline=flight.airline,
        airline_name=airlines_cache.get_name(flight.airline) if flight.airline else None,
        transfers=flight.transfers,
        departure_at=flight.departure_at or "",
        arrival_at=outbound.arrival_at if outbound else None,
        duration_min=flight.duration,
        outbound=outbound,
        inbound=inbound,
        booking_url=booking_url,
        transfers_formatted=format_transfers_count(flight.transfers),
        duration_formatted=format_duration(flight.duration) if flight.duration else "",
        price_formatted=format_price(flight.price, currency),
    )
    return result


def _resolve_booking_url(flight: FlightPrice, marker: str | None = None) -> str:
    """Resolve booking URL: ticket_link with marker, or Aviasales fallback."""
    if flight.ticket_link:
        link = str(flight.ticket_link).strip()
        if link.startswith("http://") or link.startswith("https://"):
            url = link
        else:
            url = urljoin(_AVIASALES_BASE, link)
    else:
        return build_aviasales_fallback_url(
            flight.origin, flight.destination, flight.depart_date, flight.return_date
        )

    # Append marker if not already present
    if marker:
        parsed = urlparse(url)
        query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        lower_keys = {key.lower() for key, _ in query_pairs}
        if "marker" not in lower_keys:
            query_pairs.append(("marker", marker))
        url = urlunparse(parsed._replace(query=urlencode(query_pairs, doseq=True)))
    return url