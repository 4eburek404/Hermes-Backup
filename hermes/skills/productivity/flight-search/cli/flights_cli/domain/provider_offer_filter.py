from __future__ import annotations

from typing import Any

MAX_MODEL_CONNECTIONS = 2


def offer_segments(offer: dict[str, Any]) -> list[dict[str, Any]]:
    segments = offer.get("flights") if isinstance(offer.get("flights"), list) else offer.get("segments")
    return [segment for segment in (segments or []) if isinstance(segment, dict)]


def offer_connection_count(offer: dict[str, Any]) -> int:
    for key in ("connection_count", "number_of_changes", "change_count"):
        if offer.get(key) is not None:
            return max(0, int(offer.get(key) or 0))
    segments = offer_segments(offer)
    return max(0, len(segments) - 1) if segments else 0


def offer_has_airport_change(offer: dict[str, Any]) -> bool:
    segments = offer_segments(offer)
    for previous, current in zip(segments, segments[1:]):
        previous_arrival = str(previous.get("destination") or "").upper()
        current_departure = str(current.get("origin") or "").upper()
        if previous_arrival and current_departure and previous_arrival != current_departure:
            return True
    return False


def filter_provider_offers(offers: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    kept: list[dict[str, Any]] = []
    stats = {
        "raw_offer_count": len(offers),
        "suppressed_three_plus_count": 0,
        "suppressed_airport_change_count": 0,
    }
    for offer in offers:
        if offer_connection_count(offer) > MAX_MODEL_CONNECTIONS:
            stats["suppressed_three_plus_count"] += 1
            continue
        if offer_has_airport_change(offer):
            stats["suppressed_airport_change_count"] += 1
            continue
        kept.append(offer)
    return kept, stats
