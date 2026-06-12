"""Calendar-safe segment summaries for flight-calendar-ics envelopes."""
from __future__ import annotations

from typing import Any


def safe_segment_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "flight_number": summary.get("flight_number"),
        "route": summary.get("route"),
        "dtstart_utc": summary.get("dtstart_utc"),
        "dtend_utc": summary.get("dtend_utc"),
    }


def itinerary_flight_segments(itinerary: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "flight_number": f.get("flight_number"),
            "route": f"{(f.get('departure') or {}).get('airport')}->{(f.get('arrival') or {}).get('airport')}",
            "departure_local": (f.get("departure") or {}).get("local"),
            "arrival_local": (f.get("arrival") or {}).get("local"),
        }
        for f in itinerary.get("flights", [])
    ]
