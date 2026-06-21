from __future__ import annotations

from typing import Any


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(str(value).replace(" ", "").replace(",", "")))
    except (TypeError, ValueError):
        return None


def provider_offer_business_key(offer: dict[str, Any]) -> tuple[int, int, int, int, str, str]:
    connections = _int_or_none(offer.get("connection_count"))
    if connections is None:
        connections = _int_or_none(offer.get("number_of_changes"))
    if connections is None:
        segments = offer.get("segments") if isinstance(offer.get("segments"), list) else []
        connections = max(0, len(segments) - 1) if segments else 10**6

    airport_mismatch = _int_or_none(offer.get("airport_mismatch_count"))
    duration = _int_or_none(offer.get("duration"))
    price = _int_or_none(offer.get("price"))
    flight_numbers = "-".join(str(item) for item in (offer.get("flight_numbers") or []) if item)
    stable_id = flight_numbers or str(offer.get("id") or "")
    return (
        connections,
        airport_mismatch if airport_mismatch is not None else 0,
        duration if duration is not None else 10**9,
        price if price is not None else 10**12,
        str(offer.get("departure_at") or ""),
        stable_id,
    )
