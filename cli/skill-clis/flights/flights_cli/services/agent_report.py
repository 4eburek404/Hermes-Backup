from __future__ import annotations

from typing import Any

from .agent_report_contract import validate_agent_report


def minutes_label(value: Any) -> str | None:
    if value is None:
        return None
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return None
    hours, mins = divmod(max(0, minutes), 60)
    if hours and mins:
        return f"{hours}h{mins:02d}"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


def price_label(amount: Any, currency: Any) -> str:
    if amount is None:
        return "price n/a"
    try:
        number = int(amount)
    except (TypeError, ValueError):
        return f"{amount} {currency or ''}".strip()
    return f"{number:,} {currency or ''}".replace(",", " ").strip()


def segment_summary(segment: dict[str, Any], direction: str | None = None) -> dict[str, Any]:
    return {
        "direction": direction,
        "flight_number": segment.get("flight_number"),
        "carrier": segment.get("carrier") or segment.get("operating_carrier") or segment.get("marketing_carrier"),
        "marketing_carrier": segment.get("marketing_carrier"),
        "operating_carrier": segment.get("operating_carrier"),
        "origin": segment.get("origin"),
        "destination": segment.get("destination"),
        "departure_at": segment.get("departure_at"),
        "arrival_at": segment.get("arrival_at"),
    }


def segment_line(segment: dict[str, Any]) -> str:
    flight = segment.get("flight_number") or segment.get("carrier") or "flight"
    dep = str(segment.get("departure_at") or "")
    arr = str(segment.get("arrival_at") or "")
    dep_time = dep[11:16] if len(dep) >= 16 else "?"
    arr_time = arr[11:16] if len(arr) >= 16 else "?"
    return f"{flight} {segment.get('origin')} {dep_time}->{segment.get('destination')} {arr_time}"


def connection_summary(connection: dict[str, Any]) -> dict[str, Any]:
    risk = connection.get("risk") if isinstance(connection.get("risk"), dict) else {}
    return {
        "direction": connection.get("journey_direction"),
        "arrival_airport": connection.get("arrival_airport"),
        "departure_airport": connection.get("departure_airport"),
        "status": connection.get("status"),
        "severity": connection.get("severity"),
        "actual_min": connection.get("actual_min"),
        "actual": minutes_label(connection.get("actual_min")),
        "required_min": connection.get("required_min"),
        "required": minutes_label(connection.get("required_min")),
        "risk": {
            "score": risk.get("score"),
            "grade": risk.get("grade"),
            "reasons": risk.get("reasons") or [],
        },
    }


def candidate_options_from_details(details: list[Any], limit: int = 5) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for detail in details[: max(0, limit)]:
        if not isinstance(detail, dict):
            continue
        ranked = detail.get("ranked") if isinstance(detail.get("ranked"), dict) else {}
        candidate = detail.get("candidate") if isinstance(detail.get("candidate"), dict) else {}
        segments = []
        for journey in candidate.get("journeys") or []:
            if not isinstance(journey, dict):
                continue
            direction = str(journey.get("direction") or "")
            for segment in journey.get("segments") or []:
                if isinstance(segment, dict):
                    segments.append(segment_summary(segment, direction))
        risk = ranked.get("risk") if isinstance(ranked.get("risk"), dict) else {}
        options.append(
            {
                "rank": ranked.get("rank") or detail.get("rank"),
                "id": ranked.get("id") or candidate.get("id"),
                "category": detail.get("category"),
                "reason": detail.get("reason"),
                "ok": ranked.get("ok"),
                "price": {"amount": ranked.get("price"), "currency": ranked.get("currency")},
                "price_text": price_label(ranked.get("price"), ranked.get("currency")),
                "elapsed_min": ranked.get("elapsed_min"),
                "elapsed": minutes_label(ranked.get("elapsed_min")),
                "carriers": ranked.get("carriers") or [],
                "risk": {
                    "score": risk.get("score"),
                    "grade": risk.get("grade"),
                    "reject": risk.get("reject"),
                    "top_reasons": risk.get("top_reasons") or [],
                },
                "validation_summary": ranked.get("validation_summary"),
                "connections": [connection_summary(item) for item in ranked.get("connections") or [] if isinstance(item, dict)],
                "segments": segments,
                "ticketing_note": "Assume separate/self-transfer until the booking screen confirms protected through-ticketing and baggage.",
            }
        )
    return options


def ranked_candidate_options(data: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    details = data.get("ranked_candidates") if isinstance(data.get("ranked_candidates"), list) else []
    return candidate_options_from_details(details, limit=limit)


def priority_candidate_options(data: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    details = data.get("frontier_candidates") if isinstance(data.get("frontier_candidates"), list) else []
    return candidate_options_from_details(details, limit=limit)


def aggregate_control_summary(control: dict[str, Any]) -> dict[str, Any]:
    top_offers = control.get("top_offers") if isinstance(control.get("top_offers"), list) else []
    return {
        "direction": control.get("direction"),
        "origin": control.get("origin"),
        "destination": control.get("destination"),
        "date": control.get("date"),
        "status": control.get("status"),
        "provider": control.get("provider"),
        "filters": control.get("filters") or {},
        "offer_count": control.get("offer_count"),
        "raw_variant_count": control.get("raw_variant_count"),
        "top_offers": top_offers[:3],
        "error": control.get("error"),
    }


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


def rejected_pair_warnings(data: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    warnings = []
    for item in (data.get("rejected_pairs") or [])[: max(0, limit)]:
        if not isinstance(item, dict):
            continue
        warnings.append(
            {
                "direction": item.get("direction"),
                "reason": item.get("reason"),
                "airport_pair_status": item.get("airport_pair_status"),
                "arrival_airport": item.get("arrival_airport"),
                "departure_airport": item.get("departure_airport"),
                "actual_min": item.get("actual_min"),
                "required_min": item.get("required_min"),
                "price": {"amount": item.get("price"), "currency": item.get("currency")},
                "notes": item.get("notes") or [],
            }
        )
    return warnings


def build_answer_lines(report: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    options = report.get("recommended_options") or []
    if options:
        best = options[0]
        risk = best.get("risk") or {}
        lines.append(
            "Best CLI-ranked option: "
            f"{best.get('price_text')} risk={risk.get('grade')}/{risk.get('score')} elapsed={best.get('elapsed') or 'n/a'}."
        )
        segment_lines = [segment_line(segment) for segment in best.get("segments") or []]
        if segment_lines:
            lines.append("Segments: " + " | ".join(segment_lines[:8]))
    else:
        lines.append("No CLI-ranked assembled candidate was produced.")

    controls = report.get("aggregate_controls") or []
    usable_controls = [control for control in controls if control.get("status") == "ok" and int(control.get("offer_count") or 0) > 0]
    if usable_controls:
        control = usable_controls[0]
        offer = (control.get("top_offers") or [{}])[0]
        lines.append(
            "Aggregate control found: "
            f"{price_label(offer.get('price'), offer.get('currency'))} "
            f"{control.get('origin')}->{control.get('destination')} "
            f"{' + '.join(offer.get('flight_numbers') or []) or 'route offer'}."
        )

    priority_options = report.get("priority_options") or []
    if priority_options:
        priority = priority_options[0]
        lines.append(
            "Priority control: "
            f"{priority.get('category')} rank={priority.get('rank')} "
            f"{priority.get('price_text')} elapsed={priority.get('elapsed') or 'n/a'}."
        )

    checks = report.get("through_fare_checks") or []
    if checks:
        first = checks[0]
        lines.append(
            f"Through-fare check required: verify {first.get('carrier')} {first.get('route')} on airline/GDS before pricing it as separate legs."
        )

    lines.append("Do not treat cached or segment-search absence as proof that a through fare, direct flight, or protected ticket does not exist.")
    return lines


def build_agent_report(data: dict[str, Any]) -> dict[str, Any]:
    live = data.get("live_search") if isinstance(data.get("live_search"), dict) else {}
    plan = live.get("plan") if isinstance(live.get("plan"), dict) else {}
    assembly = data.get("assembly") if isinstance(data.get("assembly"), dict) else {}
    aggregate_controls = [aggregate_control_summary(item) for item in live.get("aggregate_controls") or [] if isinstance(item, dict)]
    options = ranked_candidate_options(data, limit=5)
    priority_options = priority_candidate_options(data, limit=5)
    fallback_segments = options[0].get("segments") if options else []
    fallback_origin = fallback_segments[0].get("origin") if fallback_segments else None
    fallback_destination = fallback_segments[-1].get("destination") if fallback_segments else None
    report = {
        "schema_version": "agent_report.v1",
        "route": {
            "origin": plan.get("origin") or fallback_origin,
            "destination": plan.get("destination") or fallback_destination,
            "origin_airports": plan.get("origin_airports") or [],
            "destination_airports": plan.get("destination_airports") or [],
            "dates": plan.get("dates") or {},
            "profile": data.get("profile") or plan.get("profile"),
            "routing_strategy": plan.get("routing_strategy"),
            "provider_policy": live.get("provider_policy"),
        },
        "status": {
            "ranked_output_count": assembly.get("ranked_output_count", len(data.get("ranked") or [])),
            "ranked_total_count": assembly.get("ranked_total_count"),
            "candidate_count": assembly.get("candidate_count"),
            "candidate_pool_truncated": assembly.get("candidate_pool_truncated"),
            "failure_count": live.get("failure_count", 0),
        },
        "source_boundaries": [
            "Segment assembly prices direct one-way legs and does not construct GDS, airline through-fares, or guaranteed single-PNR fares.",
            "Kupibilet aggregate controls can reveal provider-assembled route offers, but ticket protection, baggage, fare rules, and final price still require booking-screen verification.",
            "Travelpayouts/Aviasales cached absence is not negative evidence.",
        ],
        "hub_viability": [
            {
                "hub": item.get("hub"),
                "viable": item.get("viable"),
                "total_offer_count": item.get("total_offer_count"),
                "missing_legs": item.get("missing_legs") or [],
            }
            for item in live.get("hub_viability") or []
            if isinstance(item, dict)
        ],
        "segment_searches": [
            {
                "direction": item.get("direction"),
                "leg": item.get("leg"),
                "origin": item.get("origin"),
                "destination": item.get("destination"),
                "date": item.get("date"),
                "provider": item.get("provider"),
                "status": item.get("status"),
                "reason": item.get("reason"),
                "offer_count": item.get("offer_count"),
            }
            for item in (live.get("segment_searches") or [])[:20]
            if isinstance(item, dict)
        ],
        "recommended_options": options,
        "priority_options": priority_options,
        "aggregate_controls": aggregate_controls,
        "through_fare_checks": through_fare_checks(aggregate_controls, priority_options),
        "rejected_pair_warnings": rejected_pair_warnings(data, limit=5),
    }
    report["answer_lines"] = build_answer_lines(report)
    return report


def attach_agent_report(data: dict[str, Any], args: Any) -> dict[str, Any]:
    if bool(getattr(args, "agent_report", False)) or bool(getattr(args, "agent_mode", False)):
        report = build_agent_report(data)
        validate_agent_report(report)
        data["agent_report"] = report
    return data
