from __future__ import annotations

from typing import Any, Mapping, cast

from ...domain.carriers import carrier_from_flight_number
from ...domain.provider_offer_filter import MAX_MODEL_CONNECTIONS
from ...domain.stop_metrics import offer_stop_metrics
from ...ports.providers import EvidenceType, ProviderCapabilities, ProbeType

_CACHE_EVIDENCE_STATUSES = {"cache_hit", "stale_cache_used"}


def segment_probe_type_from_query(
    query: Mapping[str, Any], capabilities: ProviderCapabilities
) -> ProbeType:
    probe_type = query.get("probe_type")
    if probe_type in capabilities.probe_types:
        return cast(ProbeType, probe_type)
    leg = str(query.get("leg") or "")
    return "segment_direct" if "direct" in leg else "segment_hub_leg"


def evidence_type_for_offer_count(
    *, offer_count: int, cache_status: str
) -> EvidenceType:
    if offer_count > 0:
        return (
            "positive_cached_hint"
            if cache_status in _CACHE_EVIDENCE_STATUSES
            else "positive_live_evidence"
        )
    return (
        "negative_cache_absence"
        if cache_status in _CACHE_EVIDENCE_STATUSES
        else "negative_provider_empty"
    )


def aggregate_offer_summary(offer: dict[str, Any]) -> dict[str, Any]:
    raw_segments = [
        flight for flight in (offer.get("segments") or []) if isinstance(flight, dict)
    ]
    carriers: set[str] = set()
    segments = []
    for flight in raw_segments:
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
                "carrier_name": flight.get("carrier_name"),
                "origin": flight.get("origin"),
                "destination": flight.get("destination"),
                "departure_terminal": flight.get("departure_terminal"),
                "arrival_terminal": flight.get("arrival_terminal"),
                "departure_at": flight.get("departure_at"),
                "arrival_at": flight.get("arrival_at"),
            }
        )
    airport_mismatches = []
    for previous, current in zip(segments, segments[1:]):
        previous_arrival = str(previous.get("destination") or "").upper()
        current_departure = str(current.get("origin") or "").upper()
        if (
            previous_arrival
            and current_departure
            and previous_arrival != current_departure
        ):
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
        "reportable_by_stop_policy": stop_metrics["max_connections_per_journey"]
        <= MAX_MODEL_CONNECTIONS,
        "duration_min": offer.get("duration"),
        "flight_numbers": offer.get("flight_numbers")
        or [
            segment.get("flight_number")
            for segment in segments
            if segment.get("flight_number")
        ],
        "carriers": sorted(carriers),
        "segments": segments,
        "airport_mismatch_count": len(airport_mismatches),
        "airport_mismatches": airport_mismatches,
        "ticketing_note": "Provider-assembled route offer; verify single-PNR/protection, baggage, and final fare on the booking screen.",
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
