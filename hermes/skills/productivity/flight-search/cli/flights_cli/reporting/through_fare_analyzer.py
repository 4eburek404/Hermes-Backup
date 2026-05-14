from __future__ import annotations

from typing import Any


def option_common_carriers(option: dict[str, Any], segments: list[dict[str, Any]]) -> set[str]:
    common: set[str] | None = None
    for segment in segments:
        carriers = {
            str(value).upper()
            for value in (
                segment.get("carrier"),
                segment.get("marketing_carrier"),
                segment.get("operating_carrier"),
            )
            if value
        }
        flight_number = str(segment.get("flight_number") or "").upper()
        if len(flight_number) >= 2 and flight_number[:2].isalnum():
            carriers.add(flight_number[:2])
        if not carriers:
            return set()
        common = set(carriers) if common is None else common & carriers
    return common or set()


def grouped_option_segments(option: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for segment in option.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        direction = str(segment.get("direction") or "itinerary")
        grouped.setdefault(direction, []).append(segment)
    return grouped


def through_fare_checks(controls: list[dict[str, Any]], priority_options: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    def add_check(direction: Any, route: str, date: Any, carrier: str, reason: str) -> None:
        key = (str(direction or ""), route, str(date or ""), carrier)
        if key in seen:
            return
        seen.add(key)
        checks.append(
            {
                "direction": direction,
                "route": route,
                "date": date,
                "carrier": carrier,
                "reason": reason,
                "verify_with": ["airline website", "GDS/Sirena/Amadeus-capable seller", "booking screen fare rules"],
            }
        )

    for control in controls:
        for offer in control.get("top_offers") or []:
            if not isinstance(offer, dict):
                continue
            if offer.get("stop_tier") == "T3_THREE_PLUS" or offer.get("reportable_by_stop_policy") is False:
                continue
            carriers = [str(code).upper() for code in offer.get("carriers") or [] if code]
            if len(carriers) != 1 or int(offer.get("change_count") or 0) <= 0:
                continue
            add_check(
                control.get("direction"),
                f"{control.get('origin')}->{control.get('destination')}",
                control.get("date"),
                carriers[0],
                "Same-carrier multi-leg aggregate offer can indicate a single-PNR/through-fare opportunity that segment assembly cannot price.",
            )

    for option in priority_options or []:
        for direction, segments in grouped_option_segments(option).items():
            if len(segments) < 2:
                continue
            carriers = sorted(option_common_carriers(option, segments))
            if len(carriers) != 1:
                continue
            route = f"{segments[0].get('origin')}->{segments[-1].get('destination')}"
            add_check(
                direction,
                route,
                None,
                carriers[0],
                "Same-carrier priority option can be better priced or protected as an airline/GDS through fare than as summed segments.",
            )
    return checks
