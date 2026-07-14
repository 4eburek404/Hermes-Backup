from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from ..domain.normalize import numeric_or_none
from ..domain.time import minutes_between
from ..domain.vocabulary import RouteFamily


MIXED_CANDIDATE_RANKING_SCHEMA_VERSION = "flight_mixed_candidate_ranking.v1"
DECISION_FRONTIER_SCHEMA_VERSION = "flight_decision_frontier.v1"
UNKNOWN_RANK_NUMERIC = 999_999_999
MATERIAL_PRICE_DELTA_RATIO = 0.05
MATERIAL_PRICE_DELTA_ABSOLUTE = 5_000
MATERIAL_ELAPSED_DELTA_MIN = 60
MAX_GATEWAY_LAYOVER_MIN = 24 * 60
PREFERRED_LAYOVER_MAX_MIN = 6 * 60
DEFAULT_FRONTIER_MAX_OPTIONS = 6
DEFAULT_PRIMARY_GATEWAY_MAX_OPTIONS = 4
DEFAULT_FIRST_CARRIER_MAX_OPTIONS = 2


def rank_mixed_candidates(
    candidate_envelope: dict[str, Any],
    *,
    max_connections_per_journey: int = 2,
    max_connections_per_direction: dict[str, int] | None = None,
    preferred_connections_per_journey: int = 1,
    min_same_airport_connection_min: int = 120,
    min_cross_airport_connection_min: int = 300,
) -> dict[str, Any]:
    directional_max_connections = _normalize_connection_caps(
        max_connections_per_direction
    )
    mct_settings = {
        "min_same_airport_min": max(0, int(min_same_airport_connection_min)),
        "min_cross_airport_min": max(0, int(min_cross_airport_connection_min)),
    }
    candidates = [
        _normalize_candidate(candidate)
        for candidate in candidate_envelope.get("candidates") or []
        if isinstance(candidate, dict)
    ]
    evaluated = [
        _candidate_with_rank_diagnostics(
            candidate,
            max_connections_per_journey=max_connections_per_journey,
            max_connections_per_direction=directional_max_connections,
            preferred_connections_per_journey=preferred_connections_per_journey,
            min_same_airport_connection_min=mct_settings["min_same_airport_min"],
            min_cross_airport_connection_min=mct_settings["min_cross_airport_min"],
        )
        for candidate in candidates
    ]
    ranked = _quality_ranked_candidates(evaluated)
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
            "max_connections_per_direction": directional_max_connections,
            "preferred_connections_per_journey": max(
                0, int(preferred_connections_per_journey)
            ),
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
    max_gateway_alternatives: int = 2,
    max_options: int | None = DEFAULT_FRONTIER_MAX_OPTIONS,
    max_primary_gateway_options: int = DEFAULT_PRIMARY_GATEWAY_MAX_OPTIONS,
    max_options_per_first_carrier: int = DEFAULT_FIRST_CARRIER_MAX_OPTIONS,
    preferred_layover_max_min: int = PREFERRED_LAYOVER_MAX_MIN,
) -> dict[str, Any]:
    ranked = [
        candidate
        for candidate in mixed_candidate_ranking.get("ranked_candidates") or []
        if isinstance(candidate, dict)
    ]
    acceptable = [candidate for candidate in ranked if _frontier_acceptable(candidate)]
    direct_ranked = [
        candidate for candidate in ranked if _is_direct_inventory(candidate)
    ]
    direct_acceptable = [
        candidate for candidate in acceptable if _is_direct_inventory(candidate)
    ]
    if direct_acceptable:
        selection_pool = direct_acceptable
        direct_limit = (
            len(direct_acceptable) if max_options is None else max(0, int(max_options))
        )
        selected_candidates = direct_acceptable[:direct_limit]
        selection_reasons = {
            str(candidate.get("id") or ""): [
                "best_viable" if index == 0 else "ranked_acceptable"
            ]
            for index, candidate in enumerate(selected_candidates)
        }
    else:
        selection_pool = _frontier_selection_pool(
            acceptable,
            preferred_layover_max_min=preferred_layover_max_min,
        )
        selected_candidates, selection_reasons = _select_diverse_frontier_candidates(
            selection_pool,
            max_options=max_options,
            max_primary_gateway_options=max_primary_gateway_options,
            max_gateway_alternatives=max_gateway_alternatives,
            max_options_per_first_carrier=max_options_per_first_carrier,
        )
    selected = _frontier_options_with_roles(
        selected_candidates,
        selection_reasons=selection_reasons,
    )

    return {
        "schema_version": DECISION_FRONTIER_SCHEMA_VERSION,
        "options": selected,
        "coverage_summary": {
            "candidate_count": len(ranked),
            "acceptable_count": len(acceptable),
            "selected_count": len(selected),
            "suppressed_by_output_limit_count": max(
                0, len(selection_pool) - len(selected)
            ),
            "rejected_count": len(mixed_candidate_ranking.get("rejected") or []),
            "direct_option_count": len(direct_ranked),
            "acceptable_direct_option_count": len(direct_acceptable),
            "direct_option_count_by_direction": _direct_option_count_by_direction(
                direct_ranked
            ),
            "acceptable_direct_option_count_by_direction": (
                _direct_option_count_by_direction(direct_acceptable)
            ),
            "gateway_alternative_count": _gateway_alternative_count(selection_pool),
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


def _candidate_with_rank_diagnostics(
    candidate: dict[str, Any],
    *,
    max_connections_per_journey: int,
    max_connections_per_direction: dict[str, int],
    preferred_connections_per_journey: int,
    min_same_airport_connection_min: int,
    min_cross_airport_connection_min: int,
) -> dict[str, Any]:
    item = deepcopy(candidate)
    max_connections = _max_connections(candidate)
    chronology_violations = _chronology_violations(candidate)
    airport_mismatch_violations = _airport_mismatch_violations(candidate)
    mct_violations = _cross_ticket_mct_violations(
        candidate,
        min_same_airport_connection_min=min_same_airport_connection_min,
        min_cross_airport_connection_min=min_cross_airport_connection_min,
    )
    impossible_connection = (
        _has_impossible_connection(candidate)
        or bool(chronology_violations)
        or bool(airport_mismatch_violations)
        or bool(mct_violations)
    )
    connection_assessment = _connection_assessment(
        candidate,
        min_same_airport_connection_min=min_same_airport_connection_min,
        airport_mismatch_violations=airport_mismatch_violations,
        chronology_violations=chronology_violations,
        mct_violations=mct_violations,
    )
    impossible_connection = impossible_connection or (
        connection_assessment.get("status") == "invalid"
    )
    impossible_connection = impossible_connection or (
        connection_assessment.get("status") == "invalid"
    )
    ticket_protection = _ticket_protection(candidate)
    rank_components = {
        "not_covers_requested_trip": 0
        if bool(candidate.get("covers_requested_trip"))
        else 1,
        "rejected_or_impossible_connection": 1 if impossible_connection else 0,
        "max_connections_per_journey": max(
            0,
            _max_connections_over_limit(
                candidate,
                default_limit=max_connections_per_journey,
                direction_limits=max_connections_per_direction,
            ),
        ),
        "preferred_connections_per_journey": max(
            0,
            max_connections - max(0, int(preferred_connections_per_journey)),
        ),
        "ticketing_risk_tier": _ticketing_risk_tier(candidate),
        "connection_risk_score": _connection_risk_score(
            candidate, connection_assessment
        ),
        "source_confidence_penalty": _source_confidence_penalty(candidate),
        "price": _price_for_rank(candidate),
        "elapsed_time": _elapsed_time_for_rank(candidate),
    }
    if chronology_violations or airport_mismatch_violations or mct_violations:
        item["candidate_status"] = "impossible"
        item["connection_status"] = "impossible"
    if chronology_violations:
        item["chronology_violations"] = chronology_violations
    if airport_mismatch_violations:
        item["airport_mismatch_violations"] = airport_mismatch_violations
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
    item["connection_assessment"] = connection_assessment
    item["ticket_protection"] = ticket_protection
    item["rank_key"] = [
        rank_components["not_covers_requested_trip"],
        rank_components["rejected_or_impossible_connection"],
        rank_components["max_connections_per_journey"],
        rank_components["connection_risk_score"],
        rank_components["preferred_connections_per_journey"],
        rank_components["elapsed_time"],
        rank_components["price"],
        rank_components["ticketing_risk_tier"],
        rank_components["source_confidence_penalty"],
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
    proof = candidate.get("ticketing_proof")
    if isinstance(proof, dict) and bool(proof.get("proven")):
        return True
    return bool(
        candidate.get("single_pnr_proven")
        or candidate.get("protected_order_proven")
        or candidate.get("ticketing_proven")
    )


def _normalize_connection_caps(caps: dict[str, int] | None) -> dict[str, int]:
    payload = caps if isinstance(caps, dict) else {}
    normalized: dict[str, int] = {}
    for direction, value in payload.items():
        normalized_direction = _normalized_direction(direction)
        if normalized_direction not in {"outbound", "return"}:
            continue
        try:
            normalized[normalized_direction] = max(0, int(value))
        except (TypeError, ValueError):
            continue
    return normalized


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


def _airport_mismatch_violations(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for journey_index, direction, segments in _candidate_segment_groups(candidate):
        for segment_index, (previous, current) in enumerate(
            zip(segments, segments[1:])
        ):
            previous_destination = str(previous.get("destination") or "").upper()
            next_origin = str(current.get("origin") or "").upper()
            if not previous_destination or not next_origin:
                continue
            if previous_destination == next_origin:
                continue
            violations.append(
                {
                    "reason": "airport_change_forbidden",
                    "message": "connections requiring an airport change are forbidden",
                    "journey_index": journey_index,
                    "journey_direction": direction,
                    "between_segments": [segment_index, segment_index + 1],
                    "previous_destination": previous_destination,
                    "next_origin": next_origin,
                }
            )
    return violations


def _connection_assessment(
    candidate: dict[str, Any],
    *,
    min_same_airport_connection_min: int,
    airport_mismatch_violations: list[dict[str, Any]],
    chronology_violations: list[dict[str, Any]],
    mct_violations: list[dict[str, Any]],
) -> dict[str, Any]:
    connections: list[dict[str, Any]] = []
    comfort_scores = {
        "comfortable": 0,
        "acceptable": 1,
        "long": 2,
        "tight": 3,
        "unknown": 4,
        "invalid": 5,
    }
    for journey_index, direction, segments in _candidate_segment_groups(candidate):
        for segment_index, (previous, current) in enumerate(
            zip(segments, segments[1:])
        ):
            arrival_airport = str(previous.get("destination") or "").upper()
            departure_airport = str(current.get("origin") or "").upper()
            actual = minutes_between(
                str(previous.get("arrival_at") or ""),
                str(current.get("departure_at") or ""),
            )
            cross_ticket = _is_cross_ticket_boundary(candidate, previous, current)
            required = max(0, int(min_same_airport_connection_min))
            status = "valid"
            if not arrival_airport or not departure_airport or actual is None:
                status = "unknown"
                comfort = "unknown"
            elif arrival_airport != departure_airport or actual < 0:
                status = "invalid"
                comfort = "invalid"
            elif actual > MAX_GATEWAY_LAYOVER_MIN:
                status = "invalid"
                comfort = "invalid"
            elif cross_ticket and actual < required:
                status = "invalid"
                comfort = "invalid"
            elif actual < required + 60:
                comfort = "tight"
            elif actual < required + 120:
                comfort = "acceptable"
            elif actual <= PREFERRED_LAYOVER_MAX_MIN:
                comfort = "comfortable"
            else:
                comfort = "long"
            connections.append(
                {
                    "journey_index": journey_index,
                    "journey_direction": direction,
                    "between_segments": [segment_index, segment_index + 1],
                    "airport": arrival_airport or None,
                    "same_airport": bool(
                        arrival_airport and arrival_airport == departure_airport
                    ),
                    "actual_min": actual,
                    "required_min": required,
                    "margin_min": actual - required if actual is not None else None,
                    "cross_ticket": cross_ticket,
                    "status": status,
                    "comfort": comfort,
                }
            )
    comfort = max(
        (entry["comfort"] for entry in connections),
        key=lambda value: comfort_scores[value],
        default="comfortable",
    )
    status = (
        "invalid"
        if comfort == "invalid"
        or airport_mismatch_violations
        or chronology_violations
        or mct_violations
        else "unknown"
        if comfort == "unknown"
        else "valid"
    )
    return {"status": status, "comfort": comfort, "connections": connections}


def _ticket_protection(candidate: dict[str, Any]) -> dict[str, Any]:
    model = str(candidate.get("ticketing_model") or "unknown")
    source_type = str(candidate.get("source_type") or "")
    protected_models = {
        "single_pnr_proven",
        "single_ticket_proven",
        "protected_provider_order",
        "round_trip_single_ticket",
    }
    separate_models = {"separate_ticket_sum", "one_way_sum"}
    if model in protected_models and _has_ticketing_proof(candidate):
        return {"status": "protected", "source": "provider_proof", "reasons": []}
    if (
        candidate.get("self_transfer") is True
        or model in separate_models
        or source_type in {"gateway_separate_ticket", "assembled_separate_ticket"}
    ):
        return {
            "status": "unprotected",
            "source": "separate_ticket_boundary",
            "reasons": ["separate_tickets"],
        }
    return {
        "status": "unknown",
        "source": "provider_evidence_incomplete",
        "reasons": ["ticket_protection_unproven"],
    }


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


def _normalized_direction(value: Any) -> str:
    direction = str(value or "").strip().lower()
    return direction if direction in {"outbound", "return"} else ""


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
        str(violation.get("reason") or "") == "return_departure_before_outbound_arrival"
        for violation in chronology_violations
        if isinstance(violation, dict)
    )
    ticketing_model = _round_trip_ticketing_model(candidate)
    return {
        "outbound": True,
        "return": True,
        "ticketing_model": ticketing_model,
        "cross_direction_chronology": "invalid" if invalid_cross_direction else "valid",
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


def _ticketing_risk_tier(candidate: dict[str, Any]) -> int:
    status = _ticket_protection(candidate)["status"]
    return {"protected": 0, "unknown": 1, "unprotected": 2}[status]


def _connection_risk_score(
    candidate: dict[str, Any], assessment: dict[str, Any] | None = None
) -> int | float:
    payload = assessment if isinstance(assessment, dict) else {}
    return {
        "comfortable": 0,
        "acceptable": 10,
        "long": 15,
        "tight": 20,
        "unknown": 30,
        "invalid": 100,
    }.get(str(payload.get("comfort") or "unknown"), 30)


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
    amount = numeric_or_none(candidate.get("price"))
    return amount if amount is not None else UNKNOWN_RANK_NUMERIC


def _elapsed_time_for_rank(candidate: dict[str, Any]) -> int | float:
    for key in ("elapsed_min", "elapsed_time", "duration_min", "total_duration_min"):
        amount = numeric_or_none(candidate.get(key))
        if amount is not None:
            return amount
    elapsed = 0
    found = False
    for _, _direction, segments in _candidate_segment_groups(candidate):
        if not segments:
            continue
        minutes = minutes_between(
            str(segments[0].get("departure_at") or ""),
            str(segments[-1].get("arrival_at") or ""),
        )
        if minutes is None or minutes < 0:
            continue
        elapsed += minutes
        found = True
    if found:
        return elapsed
    return UNKNOWN_RANK_NUMERIC


def _max_connections(candidate: dict[str, Any]) -> int:
    journeys = candidate.get("journeys")
    if not isinstance(journeys, list):
        return int(numeric_or_none(candidate.get("connection_count")) or 0)
    max_connections = 0
    for journey in journeys:
        if not isinstance(journey, dict):
            continue
        segments = journey.get("segments")
        if not isinstance(segments, list):
            continue
        max_connections = max(max_connections, max(0, len(segments) - 1))
    return max_connections


def _max_connections_over_limit(
    candidate: dict[str, Any],
    *,
    default_limit: int,
    direction_limits: dict[str, int],
) -> int:
    default_cap = max(0, int(default_limit))
    if not direction_limits:
        return _max_connections(candidate) - default_cap
    over_limit = 0
    groups = _candidate_segment_groups(candidate)
    if not groups:
        connection_count = int(numeric_or_none(candidate.get("connection_count")) or 0)
        return connection_count - default_cap
    for _, direction, segments in groups:
        normalized_direction = _normalized_direction(direction)
        cap = direction_limits.get(normalized_direction, default_cap)
        over_limit = max(over_limit, max(0, len(segments) - 1) - cap)
    return over_limit


def _ranking_reasons(
    candidate: dict[str, Any],
    rank_components: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
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
    if candidate.get("airport_mismatch_violations"):
        reasons.append("airport_change_forbidden")
    if rank_components["max_connections_per_journey"]:
        reasons.append("exceeds_max_connections_per_journey")
    if rank_components.get("preferred_connections_per_journey"):
        reasons.append("exceeds_preferred_connections_per_journey")
    if "provider_ticketing_protection_unverified" in set(
        candidate.get("warnings") or []
    ):
        reasons.append("provider_ticketing_protection_unverified")
    return reasons


def _quality_ranked_candidates(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    fastest_by_quality: dict[tuple[int, ...], int | float] = {}
    for candidate in candidates:
        prefix = _quality_rank_prefix(candidate)
        elapsed = _elapsed_time_for_rank(candidate)
        fastest_by_quality[prefix] = min(
            fastest_by_quality.get(prefix, UNKNOWN_RANK_NUMERIC),
            elapsed,
        )

    for candidate in candidates:
        components = candidate.get("rank_components")
        if not isinstance(components, dict):
            components = {}
            candidate["rank_components"] = components
        prefix = _quality_rank_prefix(candidate)
        elapsed = _elapsed_time_for_rank(candidate)
        fastest = fastest_by_quality.get(prefix, elapsed)
        elapsed_band = (
            0
            if elapsed >= UNKNOWN_RANK_NUMERIC or fastest >= UNKNOWN_RANK_NUMERIC
            else max(0, int(elapsed - fastest) // MATERIAL_ELAPSED_DELTA_MIN)
        )
        components["elapsed_time_band"] = elapsed_band
        candidate["rank_key"] = [
            *prefix,
            elapsed_band,
            _ticketing_risk_tier(candidate),
            _source_confidence_penalty(candidate),
            _price_for_rank(candidate),
            elapsed,
        ]

    return sorted(
        candidates,
        key=lambda candidate: (
            tuple(candidate.get("rank_key") or []),
            str(candidate.get("id") or ""),
        ),
    )


def _quality_rank_prefix(candidate: dict[str, Any]) -> tuple[int, ...]:
    components = candidate.get("rank_components")
    payload = components if isinstance(components, dict) else {}
    return (
        int(payload.get("not_covers_requested_trip") or 0),
        int(payload.get("rejected_or_impossible_connection") or 0),
        int(payload.get("max_connections_per_journey") or 0),
        int(payload.get("preferred_connections_per_journey") or 0),
        int(payload.get("connection_risk_score") or 0),
    )


def _frontier_selection_pool(
    acceptable: list[dict[str, Any]],
    *,
    preferred_layover_max_min: int,
) -> list[dict[str, Any]]:
    if not acceptable:
        return []

    preferred = [
        candidate
        for candidate in acceptable
        if int(
            (candidate.get("rank_components") or {}).get(
                "preferred_connections_per_journey"
            )
            or 0
        )
        == 0
    ]
    if preferred:
        tier_pool = preferred
    else:
        minimum_connections = min(
            _max_connections(candidate) for candidate in acceptable
        )
        tier_pool = [
            candidate
            for candidate in acceptable
            if _max_connections(candidate) == minimum_connections
        ]

    layover_limit = max(0, int(preferred_layover_max_min))
    preferred_layovers = [
        candidate
        for candidate in tier_pool
        if _candidate_max_layover_min(candidate) <= layover_limit
    ]
    layover_pool = preferred_layovers or tier_pool

    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for candidate in layover_pool:
        grouped.setdefault(_gateway_signature(candidate), []).append(candidate)

    comfort_pool: list[dict[str, Any]] = []
    for group in grouped.values():
        normal = [
            candidate
            for candidate in group
            if str(
                (candidate.get("connection_assessment") or {}).get("comfort")
                or "unknown"
            )
            in {"comfortable", "acceptable"}
        ]
        comfort_pool.extend(normal or group)

    return sorted(
        _pareto_prune_within_gateway(comfort_pool),
        key=lambda candidate: (
            int(candidate.get("rank") or UNKNOWN_RANK_NUMERIC),
            str(candidate.get("id") or ""),
        ),
    )


def _candidate_max_layover_min(candidate: dict[str, Any]) -> int | float:
    assessment = candidate.get("connection_assessment")
    connections = (
        assessment.get("connections")
        if isinstance(assessment, dict)
        and isinstance(assessment.get("connections"), list)
        else []
    )
    values = [
        numeric_or_none(connection.get("actual_min"))
        for connection in connections
        if isinstance(connection, dict)
    ]
    finite = [value for value in values if value is not None]
    if finite:
        return max(finite)
    return 0 if _max_connections(candidate) == 0 else UNKNOWN_RANK_NUMERIC


def _pareto_prune_within_gateway(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        candidate
        for candidate in candidates
        if not any(
            other is not candidate and _dominates_within_gateway(other, candidate)
            for other in candidates
        )
    ]


def _dominates_within_gateway(candidate: dict[str, Any], other: dict[str, Any]) -> bool:
    if _gateway_signature(candidate) != _gateway_signature(other):
        return False
    candidate_values = _dominance_values(candidate)
    other_values = _dominance_values(other)
    return all(
        candidate_value <= other_value
        for candidate_value, other_value in zip(candidate_values, other_values)
    ) and any(
        candidate_value < other_value
        for candidate_value, other_value in zip(candidate_values, other_values)
    )


def _dominance_values(candidate: dict[str, Any]) -> tuple[int | float, ...]:
    return (
        _connection_risk_score(candidate, candidate.get("connection_assessment")),
        _ticketing_risk_tier(candidate),
        _source_confidence_penalty(candidate),
        _price_for_rank(candidate),
        _elapsed_time_for_rank(candidate),
    )


def _gateway_signature(candidate: dict[str, Any]) -> tuple[Any, ...]:
    signature: list[tuple[str, tuple[str, ...]]] = []
    for _index, direction, segments in _candidate_segment_groups(candidate):
        intermediate = tuple(
            str(segment.get("destination") or "").strip().upper()
            for segment in segments[:-1]
            if str(segment.get("destination") or "").strip()
        )
        signature.append((_normalized_direction(direction), intermediate))
    return tuple(signature)


def _carrier_chain_signature(candidate: dict[str, Any]) -> tuple[Any, ...]:
    signature: list[tuple[str, tuple[str, ...]]] = []
    for _index, direction, segments in _candidate_segment_groups(candidate):
        carriers = tuple(_segment_carrier(segment) for segment in segments)
        if carriers and all(carrier == "UNKNOWN" for carrier in carriers):
            carriers = (*carriers, str(candidate.get("id") or "UNKNOWN"))
        signature.append((_normalized_direction(direction), carriers))
    return tuple(signature)


def _segment_carrier(segment: dict[str, Any]) -> str:
    return (
        str(
            segment.get("marketing_carrier")
            or segment.get("carrier")
            or segment.get("operating_carrier")
            or "UNKNOWN"
        )
        .strip()
        .upper()
    )


def _first_leg_carrier(candidate: dict[str, Any]) -> str:
    groups = _candidate_segment_groups(candidate)
    for _index, direction, segments in groups:
        if _normalized_direction(direction) == "outbound" and segments:
            carrier = _segment_carrier(segments[0])
            return (
                carrier
                if carrier != "UNKNOWN"
                else str(candidate.get("id") or "UNKNOWN")
            )
    for _index, _direction, segments in groups:
        if segments:
            carrier = _segment_carrier(segments[0])
            return (
                carrier
                if carrier != "UNKNOWN"
                else str(candidate.get("id") or "UNKNOWN")
            )
    return str(candidate.get("id") or "UNKNOWN")


def _select_diverse_frontier_candidates(
    candidates: list[dict[str, Any]],
    *,
    max_options: int | None,
    max_primary_gateway_options: int,
    max_gateway_alternatives: int,
    max_options_per_first_carrier: int,
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    if not candidates:
        return [], {}
    total_limit = (
        DEFAULT_FRONTIER_MAX_OPTIONS
        if max_options is None
        else max(0, int(max_options))
    )
    if total_limit == 0:
        return [], {}

    ordered = sorted(
        candidates,
        key=lambda candidate: (
            int(candidate.get("rank") or UNKNOWN_RANK_NUMERIC),
            str(candidate.get("id") or ""),
        ),
    )
    primary_gateway = _gateway_signature(ordered[0])
    primary_limit = min(total_limit, max(0, int(max_primary_gateway_options)))
    alternative_limit = min(total_limit, max(0, int(max_gateway_alternatives)))
    first_carrier_limit = max(1, int(max_options_per_first_carrier))
    selected: list[dict[str, Any]] = []
    reasons: dict[str, list[str]] = {}
    seen_signatures: set[tuple[Any, ...]] = set()
    first_carrier_counts: dict[str, int] = {}
    selected_primary = 0
    selected_alternatives = 0

    def add(candidate: dict[str, Any], role: str) -> bool:
        nonlocal selected_primary, selected_alternatives
        if len(selected) >= total_limit:
            return False
        signature = (_gateway_signature(candidate), _carrier_chain_signature(candidate))
        first_carrier = _first_leg_carrier(candidate)
        if signature in seen_signatures:
            return False
        if first_carrier_counts.get(first_carrier, 0) >= first_carrier_limit:
            return False
        is_primary = _gateway_signature(candidate) == primary_gateway
        if is_primary and selected_primary >= primary_limit:
            return False
        if not is_primary and selected_alternatives >= alternative_limit:
            return False
        selected.append(candidate)
        seen_signatures.add(signature)
        first_carrier_counts[first_carrier] = (
            first_carrier_counts.get(first_carrier, 0) + 1
        )
        if is_primary:
            selected_primary += 1
        else:
            selected_alternatives += 1
        reasons[str(candidate.get("id") or "")] = [role]
        return True

    primary_candidates = [
        candidate
        for candidate in ordered
        if _gateway_signature(candidate) == primary_gateway
    ]
    seen_primary_carriers: set[str] = set()
    for candidate in primary_candidates:
        first_carrier = _first_leg_carrier(candidate)
        if first_carrier in seen_primary_carriers:
            continue
        if add(candidate, "carrier_diversity"):
            seen_primary_carriers.add(first_carrier)

    alternative_gateways: list[tuple[Any, ...]] = []
    for candidate in ordered:
        gateway = _gateway_signature(candidate)
        if gateway == primary_gateway or gateway in alternative_gateways:
            continue
        alternative_gateways.append(gateway)
    for gateway in alternative_gateways:
        candidate = next(
            item for item in ordered if _gateway_signature(item) == gateway
        )
        add(candidate, "gateway_alternative")

    for candidate in primary_candidates:
        add(candidate, "carrier_diversity")

    selected.sort(
        key=lambda candidate: (
            int(candidate.get("rank") or UNKNOWN_RANK_NUMERIC),
            str(candidate.get("id") or ""),
        )
    )
    if selected:
        best_id = str(selected[0].get("id") or "")
        reasons[best_id] = (
            ["best_viable"]
            if len(selected) == 1
            else _ordered_unique(["best_viable", *(reasons.get(best_id) or [])])
        )
    if len(selected) > 1:
        cheapest = _min_finite(selected, _price_for_rank)
        if cheapest is not None:
            cheapest_id = str(cheapest.get("id") or "")
            reasons[cheapest_id] = _ordered_unique(
                [*(reasons.get(cheapest_id) or []), "cheapest_selected"]
            )
        fastest = _min_finite(selected, _elapsed_time_for_rank)
        if fastest is not None:
            fastest_id = str(fastest.get("id") or "")
            reasons[fastest_id] = _ordered_unique(
                [*(reasons.get(fastest_id) or []), "fastest_selected"]
            )
    return selected, reasons


def _frontier_options_with_roles(
    candidates: list[dict[str, Any]],
    *,
    selection_reasons: dict[str, list[str]],
) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for candidate in candidates:
        roles = selection_reasons.get(str(candidate.get("id") or "")) or [
            "carrier_diversity"
        ]
        option = _frontier_option(candidate, roles[0])
        option["selection_reasons"] = _ordered_unique(roles)
        options.append(option)
    return options


def _gateway_alternative_count(candidates: list[dict[str, Any]]) -> int:
    if not candidates:
        return 0
    primary = _gateway_signature(candidates[0])
    return len(
        {
            _gateway_signature(candidate)
            for candidate in candidates
            if _gateway_signature(candidate) != primary
        }
    )


def _frontier_acceptable(candidate: dict[str, Any]) -> bool:
    components = candidate.get("rank_components")
    if isinstance(components, dict):
        blocking_keys = (
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
        and (candidate.get("connection_assessment") or {}).get("status") != "invalid"
        and (candidate.get("connection_assessment") or {}).get("status") != "invalid"
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
        "self_transfer",
        "self_transfer_note",
        "self_transfer_source",
        "journey_pairing_model",
        "direction_pairing",
        "detail_status",
        "journeys",
        "warnings",
        "elapsed_min",
        "duration_min",
        "total_duration_min",
        "connection_risk_score",
        "connection_assessment",
        "ticket_protection",
        "price_comparison",
    )
    option = {key: deepcopy(candidate.get(key)) for key in allowed if key in candidate}
    option["selection_reasons"] = [role]
    option["connection_count"] = _max_connections(candidate)
    sources = _evidence_sources(candidate)
    if sources:
        option["evidence_sources"] = sources
    return option


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


def _is_direct_inventory(candidate: dict[str, Any]) -> bool:
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
        if not _is_direct_inventory(candidate):
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
