from __future__ import annotations

import re
from typing import Any

from ..config import CARRIER_RE

def carrier_from_flight_number(flight_number: str) -> str | None:
    compact = re.sub(r"[^A-Z0-9]", "", str(flight_number or "").upper())
    if len(compact) >= 3 and compact[:2].isalnum() and compact[2].isdigit() and any(ch.isalpha() for ch in compact[:2]):
        return compact[:2]
    prefix = "".join(ch for ch in compact if ch.isalpha())
    return prefix if CARRIER_RE.match(prefix) else None


def carrier_from_leg(leg: dict[str, Any]) -> str | None:
    for key in ("operating_carrier", "carrier", "airline", "main_airline"):
        value = leg.get(key)
        if isinstance(value, str) and value.strip():
            code = value.strip().upper()
            if CARRIER_RE.match(code):
                return code
    return carrier_from_flight_number(str(leg.get("flight_number") or ""))


def segment_carriers(segment: dict[str, Any]) -> set[str]:
    carriers: set[str] = set()
    for key in ("carrier", "airline", "operating_carrier", "main_airline"):
        value = segment.get(key)
        if isinstance(value, str) and value.strip():
            code = value.strip().upper()
            if CARRIER_RE.match(code):
                carriers.add(code)
    flight_number = segment.get("flight_number")
    if isinstance(flight_number, str):
        code = carrier_from_flight_number(flight_number)
        if code:
            carriers.add(code)
    return carriers


def itinerary_carriers(segments: list[dict[str, Any]]) -> set[str]:
    carriers: set[str] = set()
    for segment in segments:
        carriers.update(segment_carriers(segment))
    return carriers
