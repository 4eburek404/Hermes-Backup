from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from ..domain.carriers import carrier_from_flight_number
from ..domain.time import minutes_between
from ..domain.vocabulary import IntentClass, RouteFamily


MIXED_CANDIDATE_RANKING_SCHEMA_VERSION = "flight_mixed_candidate_ranking.v1"
DECISION_FRONTIER_SCHEMA_VERSION = "flight_decision_frontier.v1"
UNKNOWN_RANK_NUMERIC = 999_999_999
MATERIAL_PRICE_DELTA_RATIO = 0.05
MATERIAL_PRICE_DELTA_ABSOLUTE = 5_000
MATERIAL_ELAPSED_DELTA_MIN = 60


def rank_mixed_candidates(
    candidate_envelope: dict[str, Any],
    *,
    legacy_candidates: list[dict[str, Any]] | None = None,
    max_connections_per_journey: int = 2,
    constraints: dict[str, Any] | None = None,
    min_same_airport_connection_min: int = 120,
    min_cross_airport_connection_min: int = 300,
) -> dict[str, Any]:
    normalized_constraints = _normalize_constraints(constraints)
    mct_settings = {
        "min_same_airport_min": max(0, int(min_same_airport_connection_min)),
        "min_cross_airport_min": max(0, int(min_cross_airport_connection_min)),
    }
    candidates = [
        _normalize_candidate(candidate)
        for candidate in candidate_envelope.get("candidates") or []
        if isinstance(candidate, dict)
    ]
    candidates.extend(
        _normalize_legacy_candidate(candidate)
        for candidate in legacy_candidates or []
        if isinstance(candidate, dict)
    )
    evaluated = [
        _candidate_with_rank_diagnostics(
            candidate,
            max_connections_per_journey=max_connections_per_journey,
            constraints=normalized_constraints,
            min_same_airport_connection_min=mct_settings["min_same_airport_min"],
            min_cross_airport_connection_min=mct_settings["min_cross_airport_min"],
        )
        for candidate in candidates
    ]
    ranked = sorted(
        evaluated,
        key=lambda candidate: (
            tuple(candidate["rank_key"]),
            str(candidate.get("id") or ""),
        ),
    )
    for index, candidate in enumerate(ranked, start=1):
        candidate["rank"] = index
    return {
        "schema_version": MIXED_CANDIDATE_RANKING_SCHEMA_VERSION,
        "ranked_candidates": ranked,
        "rejected": deepcopy(candidate_envelope.get("rejected") or []),
        "coverage": {
            "candidate_count": len(ranked),
            "rejected_count": len(candidate_envelope.get("rejected") or []),
            "max_connections_per_journey": max(0, int(max_connections_per_journey)),
            "constraints": normalized_constraints,
            "mct_settings": mct_settings,
            "source_types": sorted(
                {
                    str(candidate.get("source_type"))
                    for candidate in ranked
                    if candidate.get("source_type")
                }
            ),
        },
    }


def build_decision_frontier(
    mixed_candidate_ranking: dict[str, Any],
    *,
    controls: list[dict[str, Any]] | None = None,
    max_gateway_alternatives: int = 2,
) -> dict[str, Any]:
    ranked = [
        candidate
        for candidate in mixed_candidate_ranking.get("ranked_candidates") or []
        if isinstance(candidate, dict)
    ]
    acceptable = [candidate for candidate in ranked if _frontier_acceptable(candidate)]
    selected: list[dict[str, Any]] = []

    best = acceptable[0] if acceptable else None
    _select_frontier_option(selected, best, "best_viable")

    cheapest = _min_finite(acceptable, _price_for_rank)
    if _materially_cheaper(cheapest, selected):
        _select_frontier_option(selected, cheapest, "cheapest_acceptable")

    fastest = _min_finite(acceptable, _elapsed_time_for_rank)
    if _materially_faster(fastest, selected):
        _select_frontier_option(selected, fastest, "fastest_acceptable")

    safer = _safest_candidate(acceptable)
    if _materially_safer(safer, selected):
        _select_frontier_option(selected, safer, "safer_ticketing")

    for candidate in acceptable:
        if _is_direct_control(candidate):
            _select_frontier_option(selected, candidate, "direct_nonstop_control")

    gateway_count = 0
    for candidate in _best_gateway_alternatives(acceptable):
        if gateway_count >= max(0, int(max_gateway_alternatives)):
            break
        if _select_frontier_option(
            selected,
            candidate,
            "significant_gateway_alternative",
        ):
            gateway_count += 1

    return {
        "schema_version": DECISION_FRONTIER_SCHEMA_VERSION,
        "options": selected,
        "controls": _frontier_controls(controls or []),
        "coverage_summary": {
            "candidate_count": len(ranked),
            "acceptable_count": len(acceptable),
            "selected_count": len(selected),
            "rejected_count": len(mixed_candidate_ranking.get("rejected") or []),
            "control_count": len(controls or []),
            "direct_option_count": len(
                [candidate for candidate in acceptable if _is_direct_control(candidate)]
            ),
            "direct_option_count_by_direction": _direct_option_count_by_direction(
                acceptable
            ),
            "gateway_alternative_count": len(_best_gateway_alternatives(acceptable)),
            "source_types": sorted(
                {
                    str(candidate.get("source_type"))
                    for candidate in ranked
                    if candidate.get("source_type")
                }
            ),
            "selection_roles": sorted(
                {
                    role
                    for option in selected
                    for role in option.get("selection_reasons") or []
                }
            ),
        },
    }


def _normalize_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(candidate)
    model, warnings = _normalize_ticketing_model(normalized)
    normalized["ticketing_model"] = model
    normalized["warnings"] = _ordered_unique(
        [*(normalized.get("warnings") or []), *warnings]
    )
    return normalized


def _normalize_legacy_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(candidate)
    normalized.setdefault("source_type", "assembled_separate_ticket")
    normalized.setdefault("covers_requested_trip", True)
    normalized.setdefault("journey_scope", "one_way")
    normalized.setdefault("ticketing_model", "unknown")
    normalized.setdefault("detail_status", "summary_only")
    normalized.setdefault("warnings", [])
    return _normalize_candidate(normalized)


def _candidate_with_rank_diagnostics(
    candidate: dict[str, Any],
    *,
    max_connections_per_journey: int,
    constraints: dict[str, Any],
    min_same_airport_connection_min: int,
    min_cross_airport_connection_min: int,
) -> dict[str, Any]:
    item = deepcopy(candidate)
    max_connections = _max_connections(candidate)
    chronology_violations = _chronology_violations(candidate)
    mct_violations = _cross_ticket_mct_violations(
        candidate,
        min_same_airport_connection_min=min_same_airport_connection_min,
        min_cross_airport_connection_min=min_cross_airport_connection_min,
    )
    constraint_violations = _constraint_violations(candidate, constraints)
    existing_violations = item.get("hard_constraint_violations")
    all_constraint_violations = [
        *(existing_violations if isinstance(existing_violations, list) else []),
        *constraint_violations,
    ]
    if all_constraint_violations:
        item["hard_constraint_violation"] = True
        item["hard_constraint_violations"] = all_constraint_violations
    impossible_connection = (
        _has_impossible_connection(candidate)
        or bool(chronology_violations)
        or bool(mct_violations)
    )
    rank_components = {
        "hard_constraint_violation": 1 if _has_hard_constraint_violation(item) else 0,
        "not_covers_requested_trip": 0
        if bool(candidate.get("covers_requested_trip"))
        else 1,
        "rejected_or_impossible_connection": 1 if impossible_connection else 0,
        "max_connections_per_journey": max(
            0,
            max_connections - max(0, int(max_connections_per_journey)),
        ),
        "preferred_carrier_miss": _preferred_carrier_miss(candidate, constraints),
        "ticketing_risk_tier": _ticketing_risk_tier(candidate),
        "connection_risk_score": _connection_risk_score(candidate),
        "source_confidence_penalty": _source_confidence_penalty(candidate),
        "price": _price_for_rank(candidate),
        "elapsed_time": _elapsed_time_for_rank(candidate),
    }
    if chronology_violations or mct_violations:
        item["candidate_status"] = "impossible"
        item["connection_status"] = "impossible"
    if chronology_violations:
        item["chronology_violations"] = chronology_violations
    if mct_violations:
        item["mct_violations"] = mct_violations
    journey_pairing = _journey_pairing_metadata(
        candidate,
        chronology_violations=chronology_violations,
    )
    if journey_pairing:
        item["journey_pairing_model"] = journey_pairing["ticketing_model"]
        item["direction_pairing"] = journey_pairing
    item["rank_components"] = rank_components
    item["rank_key"] = [
        rank_components["hard_constraint_violation"],
        rank_components["not_covers_requested_trip"],
        rank_components["rejected_or_impossible_connection"],
        rank_components["max_connections_per_journey"],
        rank_components["preferred_carrier_miss"],
        rank_components["ticketing_risk_tier"],
        rank_components["connection_risk_score"],
        rank_components["source_confidence_penalty"],
        rank_components["price"],
        rank_components["elapsed_time"],
    ]
    item["ranking_reasons"] = _ranking_reasons(item, rank_components)
    return item


def _normalize_ticketing_model(candidate: dict[str, Any]) -> tuple[str, list[str]]:
    model = str(candidate.get("ticketing_model") or "unknown")
    if model in {
        "single_pnr",
        "single_pnr_proven",
        "single_ticket_proven",
        "protected_provider_order",
    }:
        if _has_ticketing_proof(candidate):
            return model, []
        return "provider_order_unverified", ["provider_ticketing_protection_unverified"]
    return model, []


def _has_ticketing_proof(candidate: dict[str, Any]) -> bool:
    proof = candidate.get(IntentClass.TICKETING_PROOF)
    if isinstance(proof, dict) and bool(proof.get("proven")):
        return True
    return bool(
        candidate.get("single_pnr_proven")
        or candidate.get("protected_order_proven")
        or candidate.get("ticketing_proven")
    )


def _normalize_constraints(constraints: dict[str, Any] | None) -> dict[str, Any]:
    payload = constraints if isinstance(constraints, dict) else {}
    return {
        "first_departure_after": str(payload.get("first_departure_after") or "")
        or None,
        "must_include_airports": _ordered_unique(
            str(code).strip().upper()
            for code in payload.get("must_include_airports") or []
            if str(code).strip()
        ),
        "only_carriers": _ordered_unique(
            str(code).strip().upper()
            for code in payload.get("only_carriers") or []
            if str(code).strip()
        ),
        "preferred_carriers": _ordered_unique(
            str(code).strip().upper()
            for code in payload.get("preferred_carriers") or []
            if str(code).strip()
        ),
    }


def _constraint_violations(
    candidate: dict[str, Any], constraints: dict[str, Any]
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    missing_airports = [
        code
        for code in constraints.get("must_include_airports") or []
        if code not in _candidate_airports(candidate)
    ]
    if missing_airports:
        violations.append(
            {
                "reason": "missing_required_airport",
                "must_include_airports": missing_airports,
            }
        )

    first_departure_after = constraints.get("first_departure_after")
    if first_departure_after:
        threshold = _hhmm_to_minutes(str(first_departure_after))
        actual = _first_outbound_departure_minutes(candidate)
        if actual is None:
            violations.append(
                {
                    "reason": "missing_first_departure_time",
                    "first_departure_after": first_departure_after,
                }
            )
        elif threshold is not None and actual < threshold:
            violations.append(
                {
                    "reason": "first_departure_before_requested_time",
                    "first_departure_after": first_departure_after,
                    "actual_first_departure": _minutes_to_hhmm(actual),
                }
            )

    only_carriers = set(constraints.get("only_carriers") or [])
    if only_carriers:
        segment_groups = _candidate_segment_groups(candidate)
        if not segment_groups:
            violations.append(
                {
                    "reason": "missing_carrier_evidence",
                    "only_carriers": sorted(only_carriers),
                }
            )
        for journey_index, direction, segments in segment_groups:
            for segment_index, segment in enumerate(segments):
                if _segment_matches_carrier_constraint(segment, only_carriers):
                    continue
                violations.append(
                    {
                        "reason": "carrier_not_allowed",
                        "journey_index": journey_index,
                        "journey_direction": direction,
                        "segment_index": segment_index,
                        "only_carriers": sorted(only_carriers),
                        "segment_carriers": sorted(_segment_carrier_values(segment)),
                    }
                )
    return violations


def _preferred_carrier_miss(
    candidate: dict[str, Any], constraints: dict[str, Any]
) -> int:
    preferred = set(constraints.get("preferred_carriers") or [])
    if not preferred:
        return 0
    for _, _, segments in _candidate_segment_groups(candidate):
        if any(
            _segment_matches_carrier_constraint(segment, preferred)
            for segment in segments
        ):
            return 0
    return 1


def _has_hard_constraint_violation(candidate: dict[str, Any]) -> bool:
    if bool(candidate.get("hard_constraint_violation")):
        return True
    violations = candidate.get("hard_constraint_violations")
    return isinstance(violations, list) and bool(violations)


def _has_impossible_connection(candidate: dict[str, Any]) -> bool:
    status = str(
        candidate.get("connection_status") or candidate.get("candidate_status") or ""
    ).lower()
    if status in {"rejected", "impossible", "invalid", "error"}:
        return True
    warnings = {str(item) for item in candidate.get("warnings") or []}
    return bool(
        warnings
        & {
            "impossible_connection",
            "connection_rejected",
            "airport_mismatch",
        }
    )


def _chronology_violations(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for journey_index, direction, segments in _candidate_segment_groups(candidate):
        for segment_index, (previous, current) in enumerate(
            zip(segments, segments[1:])
        ):
            actual = minutes_between(
                str(previous.get("arrival_at") or ""),
                str(current.get("departure_at") or ""),
            )
            if actual is None or actual >= 0:
                continue
            violations.append(
                {
                    "reason": "invalid_time_order",
                    "message": "next departure is earlier than previous arrival",
                    "journey_index": journey_index,
                    "journey_direction": direction,
                    "between_segments": [segment_index, segment_index + 1],
                    "actual_min": actual,
                    "previous_arrival_at": previous.get("arrival_at"),
                    "next_departure_at": current.get("departure_at"),
                    "previous_destination": previous.get("destination"),
                    "next_origin": current.get("origin"),
                }
            )
    violations.extend(_cross_direction_chronology_violations(candidate))
    return violations


def _cross_direction_chronology_violations(
    candidate: dict[str, Any],
) -> list[dict[str, Any]]:
    outbound_groups: list[tuple[int, list[dict[str, Any]]]] = []
    return_groups: list[tuple[int, list[dict[str, Any]]]] = []
    for journey_index, direction, segments in _candidate_segment_groups(candidate):
        normalized_direction = str(direction or "").strip().lower()
        if normalized_direction == "outbound":
            outbound_groups.append((journey_index, segments))
        elif normalized_direction == "return":
            return_groups.append((journey_index, segments))

    violations: list[dict[str, Any]] = []
    for outbound_index, outbound_segments in outbound_groups:
        if not outbound_segments:
            continue
        outbound_final = outbound_segments[-1]
        for return_index, return_segments in return_groups:
            if not return_segments:
                continue
            return_first = return_segments[0]
            actual = minutes_between(
                str(outbound_final.get("arrival_at") or ""),
                str(return_first.get("departure_at") or ""),
            )
            if actual is None or actual >= 0:
                continue
            violations.append(
                {
                    "reason": "return_departure_before_outbound_arrival",
                    "message": (
                        "return departure is earlier than final outbound arrival"
                    ),
                    "outbound_journey_index": outbound_index,
                    "return_journey_index": return_index,
                    "actual_min": actual,
                    "outbound_arrival_at": outbound_final.get("arrival_at"),
                    "return_departure_at": return_first.get("departure_at"),
                    "outbound_destination": outbound_final.get("destination"),
                    "return_origin": return_first.get("origin"),
                }
            )
    return violations


def _cross_ticket_mct_violations(
    candidate: dict[str, Any],
    *,
    min_same_airport_connection_min: int,
    min_cross_airport_connection_min: int,
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for journey_index, direction, segments in _candidate_segment_groups(candidate):
        for segment_index, (previous, current) in enumerate(
            zip(segments, segments[1:])
        ):
            if not _is_cross_ticket_boundary(candidate, previous, current):
                continue
            actual = minutes_between(
                str(previous.get("arrival_at") or ""),
                str(current.get("departure_at") or ""),
            )
            if actual is None or actual < 0:
                continue
            previous_destination = str(previous.get("destination") or "").upper()
            next_origin = str(current.get("origin") or "").upper()
            same_airport = bool(
                previous_destination and previous_destination == next_origin
            )
            required = (
                min_same_airport_connection_min
                if same_airport
                else min_cross_airport_connection_min
            )
            if actual >= required:
                continue
            violations.append(
                {
                    "reason": "cross_ticket_mct_violation",
                    "message": "cross-ticket connection is shorter than required MCT",
                    "journey_index": journey_index,
                    "journey_direction": direction,
                    "between_segments": [segment_index, segment_index + 1],
                    "actual_min": actual,
                    "required_min": required,
                    "same_airport": same_airport,
                    "previous_arrival_at": previous.get("arrival_at"),
                    "next_departure_at": current.get("departure_at"),
                    "previous_destination": previous.get("destination"),
                    "next_origin": current.get("origin"),
                    "previous_offer_id": previous.get("offer_id"),
                    "next_offer_id": current.get("offer_id"),
                }
            )
    return violations


def _is_cross_ticket_boundary(
    candidate: dict[str, Any],
    previous: dict[str, Any],
    current: dict[str, Any],
) -> bool:
    ticketing_model = str(candidate.get("ticketing_model") or "")
    if ticketing_model in {
        "single_pnr",
        "single_pnr_proven",
        "single_ticket_proven",
        "protected_provider_order",
        "provider_order_unverified",
        "round_trip_single_ticket",
    }:
        return False
    previous_offer_id = str(previous.get("offer_id") or "")
    current_offer_id = str(current.get("offer_id") or "")
    if previous_offer_id and current_offer_id:
        return previous_offer_id != current_offer_id
    boundaries = {
        str(previous.get("ticketing_boundary") or ""),
        str(current.get("ticketing_boundary") or ""),
    }
    if any("separate_ticket" in boundary for boundary in boundaries):
        return True
    return str(candidate.get("source_type") or "") == "gateway_separate_ticket"


def _candidate_segment_groups(
    candidate: dict[str, Any],
) -> list[tuple[int, str, list[dict[str, Any]]]]:
    groups: list[tuple[int, str, list[dict[str, Any]]]] = []
    journeys = candidate.get("journeys")
    if isinstance(journeys, list):
        for journey_index, journey in enumerate(journeys):
            if not isinstance(journey, dict):
                continue
            raw_segments = journey.get("segments")
            if not isinstance(raw_segments, list):
                continue
            segments = [
                segment for segment in raw_segments if isinstance(segment, dict)
            ]
            if segments:
                groups.append(
                    (
                        journey_index,
                        str(journey.get("direction") or f"journey_{journey_index}"),
                        segments,
                    )
                )
    raw_segments = candidate.get("segments")
    if isinstance(raw_segments, list) and not groups:
        segments = [segment for segment in raw_segments if isinstance(segment, dict)]
        if segments:
            groups.append((0, "itinerary", segments))
    return groups


def _journey_pairing_metadata(
    candidate: dict[str, Any],
    *,
    chronology_violations: list[dict[str, Any]],
) -> dict[str, Any] | None:
    directions = {
        str(direction or "").strip().lower()
        for _, direction, segments in _candidate_segment_groups(candidate)
        if segments
    }
    if not {"outbound", "return"}.issubset(directions):
        return None
    invalid_cross_direction = any(
        str(violation.get("reason") or "")
        == "return_departure_before_outbound_arrival"
        for violation in chronology_violations
        if isinstance(violation, dict)
    )
    ticketing_model = _round_trip_ticketing_model(candidate)
    return {
        "outbound": True,
        "return": True,
        "ticketing_model": ticketing_model,
        "cross_direction_chronology": "invalid"
        if invalid_cross_direction
        else "valid",
    }


def _round_trip_ticketing_model(candidate: dict[str, Any]) -> str:
    model = str(candidate.get("ticketing_model") or "").strip()
    if model == "round_trip_single_ticket":
        return "round_trip_single_ticket"
    if model == "one_way_sum" or isinstance(candidate.get("round_trip_pair"), dict):
        return "one_way_sum"
    if model == "separate_ticket_sum":
        return "one_way_sum"
    if model == "provider_order_unverified":
        return "round_trip_provider_order_unverified"
    return model or "unknown"


def _candidate_airports(candidate: dict[str, Any]) -> set[str]:
    airports: set[str] = set()
    for key in ("origin", "destination", "gateway"):
        value = str(candidate.get(key) or "").strip().upper()
        if value:
            airports.add(value)
    for _, _, segments in _candidate_segment_groups(candidate):
        for segment in segments:
            for key in ("origin", "destination"):
                value = str(segment.get(key) or "").strip().upper()
                if value:
                    airports.add(value)
    return airports


def _first_outbound_departure_minutes(candidate: dict[str, Any]) -> int | None:
    groups = _candidate_segment_groups(candidate)
    if not groups:
        return None
    selected_segments = groups[0][2]
    for _, direction, segments in groups:
        if direction == "outbound":
            selected_segments = segments
            break
    if not selected_segments:
        return None
    first = selected_segments[0]
    return _time_text_to_minutes(str(first.get("departure_at") or ""))


def _time_text_to_minutes(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[1]
    return _hhmm_to_minutes(text[:5])


def _hhmm_to_minutes(value: str) -> int | None:
    parts = str(value or "").strip().split(":")
    if len(parts) != 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return None
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return hour * 60 + minute


def _minutes_to_hhmm(value: int) -> str:
    minute_value = max(0, int(value))
    return f"{minute_value // 60:02d}:{minute_value % 60:02d}"


def _segment_matches_carrier_constraint(
    segment: dict[str, Any], allowed_carriers: set[str]
) -> bool:
    allowed = {str(code).strip().upper() for code in allowed_carriers if str(code)}
    if not allowed:
        return True
    values = _segment_carrier_values(segment)
    return any(
        value == code or (len(code) in {2, 3} and value.startswith(code))
        for code in allowed
        for value in values
    )


def _segment_carrier_values(segment: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for key in (
        "carrier",
        "airline",
        "main_airline",
        "marketing_carrier",
        "operating_carrier",
        "carrier_name",
        "airline_name",
        "marketing_carrier_name",
        "operating_carrier_name",
    ):
        _add_carrier_name_values(values, segment.get(key))
    flight_number = segment.get("flight_number")
    if flight_number:
        code = carrier_from_flight_number(str(flight_number))
        if code:
            values.add(code)
    return values


def _add_carrier_name_values(values: set[str], raw_value: Any) -> None:
    raw = str(raw_value or "").strip()
    if not raw:
        return
    upper = raw.upper()
    values.add(upper)
    compact = "".join(ch for ch in upper if ch.isalnum())
    if compact:
        values.add(compact)
    normalized = "".join(ch if ch.isalnum() else " " for ch in upper)
    words = [word for word in normalized.split() if word]
    if not words:
        return
    values.add(words[0])
    initials = "".join(word[0] for word in words if word[0].isalpha())
    if initials:
        values.add(initials)


def _ticketing_risk_tier(candidate: dict[str, Any]) -> int:
    model = str(candidate.get("ticketing_model") or "unknown")
    source_type = str(candidate.get("source_type") or "")
    if model in {
        "single_pnr_proven",
        "single_ticket_proven",
        "protected_provider_order",
        "round_trip_single_ticket",
    }:
        return 0
    if source_type == RouteFamily.DIRECT_INVENTORY:
        return 0
    if model == "one_way_sum":
        return 3
    if source_type == "provider_full_route":
        return 1
    if model in {"metasearch_redirect_unknown", "provider_order_unverified"}:
        return 2
    if source_type == "gateway_separate_ticket" or model == "separate_ticket_sum":
        return 4
    if source_type == "assembled_separate_ticket":
        return 5
    return 6


def _connection_risk_score(candidate: dict[str, Any]) -> int | float:
    explicit = _numeric_or_none(candidate.get("connection_risk_score"))
    if explicit is not None:
        return explicit
    risk = candidate.get("connection_risk")
    if isinstance(risk, dict):
        explicit = _numeric_or_none(risk.get("score"))
        if explicit is not None:
            return explicit
    if candidate.get("source_type") == "gateway_separate_ticket":
        return 30
    return 0


def _source_confidence_penalty(candidate: dict[str, Any]) -> int:
    source_type = str(candidate.get("source_type") or "")
    if source_type in {"provider_full_route", RouteFamily.DIRECT_INVENTORY}:
        return 0
    if source_type == "gateway_separate_ticket":
        return 30
    if source_type == "assembled_separate_ticket":
        return 40
    return 50


def _price_for_rank(candidate: dict[str, Any]) -> int | float:
    amount = _numeric_or_none(candidate.get("price"))
    return amount if amount is not None else UNKNOWN_RANK_NUMERIC


def _elapsed_time_for_rank(candidate: dict[str, Any]) -> int | float:
    for key in ("elapsed_min", "elapsed_time", "duration_min", "total_duration_min"):
        amount = _numeric_or_none(candidate.get(key))
        if amount is not None:
            return amount
    return UNKNOWN_RANK_NUMERIC


def _max_connections(candidate: dict[str, Any]) -> int:
    journeys = candidate.get("journeys")
    if not isinstance(journeys, list):
        return int(_numeric_or_none(candidate.get("connection_count")) or 0)
    max_connections = 0
    for journey in journeys:
        if not isinstance(journey, dict):
            continue
        segments = journey.get("segments")
        if not isinstance(segments, list):
            continue
        max_connections = max(max_connections, max(0, len(segments) - 1))
    return max_connections


def _ranking_reasons(
    candidate: dict[str, Any],
    rank_components: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if rank_components["hard_constraint_violation"]:
        reasons.append("hard_constraint_violation")
    if rank_components["not_covers_requested_trip"]:
        reasons.append("does_not_cover_requested_trip")
    if rank_components["rejected_or_impossible_connection"]:
        reasons.append("rejected_or_impossible_connection")
    chronology_violations = candidate.get("chronology_violations")
    if not isinstance(chronology_violations, list):
        chronology_violations = _chronology_violations(candidate)
    for violation in chronology_violations:
        if not isinstance(violation, dict):
            continue
        reason = str(violation.get("reason") or "invalid_time_order")
        if reason not in reasons:
            reasons.append(reason)
    if candidate.get("mct_violations"):
        reasons.append("cross_ticket_mct_violation")
    if rank_components["max_connections_per_journey"]:
        reasons.append("exceeds_max_connections_per_journey")
    if candidate.get("source_type") == "gateway_separate_ticket":
        reasons.append("separate_ticket_ranked_after_provider_route_evidence")
    if "provider_ticketing_protection_unverified" in set(
        candidate.get("warnings") or []
    ):
        reasons.append("provider_ticketing_protection_unverified")
    return reasons


def _frontier_acceptable(candidate: dict[str, Any]) -> bool:
    components = candidate.get("rank_components")
    if isinstance(components, dict):
        blocking_keys = (
            "hard_constraint_violation",
            "not_covers_requested_trip",
            "rejected_or_impossible_connection",
            "max_connections_per_journey",
        )
        if any(int(components.get(key) or 0) > 0 for key in blocking_keys):
            return False
    return (
        bool(candidate.get("covers_requested_trip"))
        and not _has_impossible_connection(candidate)
        and not _chronology_violations(candidate)
    )


def _select_frontier_option(
    selected: list[dict[str, Any]],
    candidate: dict[str, Any] | None,
    role: str,
) -> bool:
    if candidate is None:
        return False
    candidate_id = str(candidate.get("id") or "")
    for option in selected:
        if str(option.get("id") or "") != candidate_id:
            continue
        option["selection_reasons"] = _ordered_unique(
            [*(option.get("selection_reasons") or []), role]
        )
        return False
    selected.append(_frontier_option(candidate, role))
    return True


def _frontier_option(candidate: dict[str, Any], role: str) -> dict[str, Any]:
    allowed = (
        "id",
        "rank",
        "source_type",
        "provider",
        "source_providers",
        "gateway",
        "covers_requested_trip",
        "journey_scope",
        "price",
        "currency",
        "price_basis",
        "ticketing_model",
        "journey_pairing_model",
        "direction_pairing",
        "detail_status",
        "journeys",
        "warnings",
        "elapsed_min",
        "duration_min",
        "total_duration_min",
        "connection_risk_score",
        "price_comparison",
    )
    option = {key: deepcopy(candidate.get(key)) for key in allowed if key in candidate}
    option["selection_reasons"] = [role]
    option["connection_count"] = _max_connections(candidate)
    sources = _evidence_sources(candidate)
    if sources:
        option["evidence_sources"] = sources
    return option


def _frontier_controls(controls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    allowed = (
        "type",
        "direction",
        "origin",
        "destination",
        "date",
        "status",
        "provider",
        "filters",
        "offer_count",
        "raw_offer_count",
        "cache_status",
        "source_type",
        "control_policy",
        "source_providers",
        "graph_derived",
        "negative_evidence",
        "reason",
        "error",
    )
    result: list[dict[str, Any]] = []
    for control in controls:
        if not isinstance(control, dict):
            continue
        item = {key: deepcopy(control.get(key)) for key in allowed if key in control}
        top_offers = control.get("top_offers")
        if isinstance(top_offers, list):
            item["top_offer_count"] = len(top_offers)
        result.append(item)
    return result


def _evidence_sources(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    sources = [_evidence_source(candidate)]
    for source in candidate.get("alternate_sources") or []:
        if isinstance(source, dict):
            sources.append(_evidence_source(source))
    return [
        source
        for source in sources
        if source.get("source_type") or source.get("source_providers")
    ]


def _evidence_source(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        key: deepcopy(candidate.get(key))
        for key in (
            "source_type",
            "provider",
            "source_providers",
            "gateway",
            "price",
            "currency",
            "price_basis",
            "ticketing_model",
        )
        if key in candidate
    }


def _min_finite(
    candidates: list[dict[str, Any]],
    value_fn: Any,
) -> dict[str, Any] | None:
    finite = [
        candidate
        for candidate in candidates
        if value_fn(candidate) < UNKNOWN_RANK_NUMERIC
    ]
    if not finite:
        return None
    return min(
        finite,
        key=lambda candidate: (value_fn(candidate), int(candidate.get("rank") or 0)),
    )


def _materially_cheaper(
    candidate: dict[str, Any] | None,
    selected: list[dict[str, Any]],
) -> bool:
    if candidate is None or not selected:
        return False
    candidate_price = _price_for_rank(candidate)
    if candidate_price >= UNKNOWN_RANK_NUMERIC:
        return False
    selected_prices = [
        _price_for_rank(option)
        for option in selected
        if _price_for_rank(option) < UNKNOWN_RANK_NUMERIC
    ]
    if not selected_prices:
        return False
    baseline = min(selected_prices)
    delta = baseline - candidate_price
    threshold = max(
        MATERIAL_PRICE_DELTA_ABSOLUTE, baseline * MATERIAL_PRICE_DELTA_RATIO
    )
    return delta >= threshold


def _materially_faster(
    candidate: dict[str, Any] | None,
    selected: list[dict[str, Any]],
) -> bool:
    if candidate is None or not selected:
        return False
    elapsed = _elapsed_time_for_rank(candidate)
    if elapsed >= UNKNOWN_RANK_NUMERIC:
        return False
    selected_elapsed = [
        _elapsed_time_for_rank(option)
        for option in selected
        if _elapsed_time_for_rank(option) < UNKNOWN_RANK_NUMERIC
    ]
    if not selected_elapsed:
        return False
    return min(selected_elapsed) - elapsed >= MATERIAL_ELAPSED_DELTA_MIN


def _safest_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda candidate: (
            _ticketing_risk_tier(candidate),
            _connection_risk_score(candidate),
            int(candidate.get("rank") or 0),
        ),
    )


def _materially_safer(
    candidate: dict[str, Any] | None,
    selected: list[dict[str, Any]],
) -> bool:
    if candidate is None or not selected:
        return False
    candidate_risk = _ticketing_risk_tier(candidate)
    selected_risks = [_ticketing_risk_tier(option) for option in selected]
    if str(candidate.get("id") or "") in {
        str(option.get("id") or "") for option in selected
    }:
        return candidate_risk < max(selected_risks)
    return candidate_risk < min(selected_risks)


def _is_direct_control(candidate: dict[str, Any]) -> bool:
    if str(candidate.get("source_type") or "") == RouteFamily.DIRECT_INVENTORY:
        return True
    journeys = candidate.get("journeys")
    if not isinstance(journeys, list) or not journeys:
        return False
    return all(
        isinstance(journey, dict)
        and isinstance(journey.get("segments"), list)
        and len(journey["segments"]) == 1
        for journey in journeys
    )


def _direct_option_count_by_direction(
    candidates: list[dict[str, Any]],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        if not _is_direct_control(candidate):
            continue
        groups = _candidate_segment_groups(candidate)
        if not groups:
            counts["itinerary"] = counts.get("itinerary", 0) + 1
            continue
        for _, direction, segments in groups:
            if len(segments) != 1:
                continue
            key = str(direction or "itinerary")
            counts[key] = counts.get(key, 0) + 1
    return counts


def _best_gateway_alternatives(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_gateway: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        if str(candidate.get("source_type") or "") != "gateway_separate_ticket":
            continue
        gateway = str(candidate.get("gateway") or "").upper()
        if not gateway:
            continue
        current = by_gateway.get(gateway)
        if current is None or int(candidate.get("rank") or 0) < int(
            current.get("rank") or 0
        ):
            by_gateway[gateway] = candidate
    return sorted(
        by_gateway.values(),
        key=lambda candidate: int(candidate.get("rank") or 0),
    )


def _numeric_or_none(value: Any) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return value
    text = str(value).strip().replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    return int(parsed) if parsed.is_integer() else parsed


def _ordered_unique(items: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for item in items:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return values


__all__ = [
    "DECISION_FRONTIER_SCHEMA_VERSION",
    "MIXED_CANDIDATE_RANKING_SCHEMA_VERSION",
    "build_decision_frontier",
    "rank_mixed_candidates",
]
