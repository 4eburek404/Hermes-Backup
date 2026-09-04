"""Единственный проход валидации кандидата и его авторитетный исход.

Модуль звался `candidate_validation` и стоял в списке на удаление: имя
обещало фронтир, а содержимое производит поля ответа —
`connection_assessment`, `ticket_protection`, `journey_pairing_model` и
`validation.blocking_reasons`, по которым фронтир решает, что показывать.
Переехал под своё имя целиком: из 324 строк мёртвым оказался только
`__all__`, перечислявший приватные имена, которых никто не импортировал.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from ..domain.connection_policy import (
    ConnectionPolicy,
    DEFAULT_MAX_LAYOVER_MIN,
    DEFAULT_MIN_CROSS_AIRPORT_CONNECTION_MIN,
    DEFAULT_MIN_SAME_AIRPORT_CONNECTION_MIN,
    DEFAULT_PREFERRED_LAYOVER_MAX_MIN,
    airport_mismatch_violations,
    candidate_segment_groups as _candidate_segment_groups,
    chronology_violations,
    connection_assessment,
    cross_ticket_mct_violations,
    missing_segment_time_violations,
    normalized_direction as _normalized_direction,
)
from ..domain.normalize import ordered_unique as _ordered_unique
from ..domain.stop_policy import (
    BUSINESS_DEFAULT_STOP_POLICY,
    candidate_connections_over_limit,
    candidate_max_connections,
)


CANDIDATE_VALIDATION_SCHEMA_VERSION = "flight_candidate_validation.v1"


def validate_candidate_envelope(
    candidate_envelope: dict[str, Any],
    *,
    max_connections_per_journey: int = (
        BUSINESS_DEFAULT_STOP_POLICY.hard_max_connections
    ),
    max_connections_per_direction: dict[str, int] | None = None,
    min_same_airport_connection_min: int = DEFAULT_MIN_SAME_AIRPORT_CONNECTION_MIN,
    min_cross_airport_connection_min: int = DEFAULT_MIN_CROSS_AIRPORT_CONNECTION_MIN,
    max_layover_min: int = DEFAULT_MAX_LAYOVER_MIN,
    preferred_layover_max_min: int = DEFAULT_PREFERRED_LAYOVER_MAX_MIN,
) -> dict[str, Any]:
    """Validate each candidate once and attach the authoritative outcome."""

    directional_caps = _normalize_connection_caps(max_connections_per_direction)
    connection_policy = ConnectionPolicy(
        min_same_airport_min=max(0, int(min_same_airport_connection_min)),
        min_cross_airport_min=max(0, int(min_cross_airport_connection_min)),
        max_layover_min=max(0, int(max_layover_min)),
        preferred_layover_max_min=max(0, int(preferred_layover_max_min)),
    )
    candidates = [
        _validate_candidate(
            _normalize_candidate(candidate),
            connection_policy=connection_policy,
            max_connections_per_journey=max_connections_per_journey,
            max_connections_per_direction=directional_caps,
        )
        for candidate in candidate_envelope.get("candidates") or []
        if isinstance(candidate, dict)
    ]
    return {
        "schema_version": CANDIDATE_VALIDATION_SCHEMA_VERSION,
        "candidates": candidates,
        "rejected": deepcopy(candidate_envelope.get("rejected") or []),
        "coverage": {
            "candidate_count": len(candidates),
            "valid_count": sum(
                1
                for candidate in candidates
                if (candidate.get("validation") or {}).get("status") == "valid"
            ),
            "invalid_count": sum(
                1
                for candidate in candidates
                if (candidate.get("validation") or {}).get("status") == "invalid"
            ),
            "max_connections_per_journey": max(0, int(max_connections_per_journey)),
            "max_connections_per_direction": directional_caps,
            "mct_settings": {
                "min_same_airport_min": connection_policy.min_same_airport_min,
                "min_cross_airport_min": connection_policy.min_cross_airport_min,
                "max_layover_min": connection_policy.max_layover_min,
                "preferred_layover_max_min": (
                    connection_policy.preferred_layover_max_min
                ),
            },
        },
    }


def _validate_candidate(
    candidate: dict[str, Any],
    *,
    connection_policy: ConnectionPolicy,
    max_connections_per_journey: int,
    max_connections_per_direction: dict[str, int],
) -> dict[str, Any]:
    item = deepcopy(candidate)
    segment_time_errors = missing_segment_time_violations(candidate)
    chronology_errors = chronology_violations(candidate)
    airport_errors = airport_mismatch_violations(candidate)
    mct_errors = cross_ticket_mct_violations(candidate, connection_policy)
    assessment = connection_assessment(
        candidate,
        connection_policy,
        airport_violations=airport_errors,
        chronology_errors=chronology_errors,
        mct_errors=mct_errors,
    )
    connections = candidate_max_connections(candidate)
    connections_over_limit = max(
        0,
        candidate_connections_over_limit(
            candidate,
            default_limit=max_connections_per_journey,
            direction_limits=max_connections_per_direction,
        ),
    )
    blocking_reasons: list[str] = []
    blocking_reasons.extend(candidate_declared_blocking_reasons(candidate))
    for violation in segment_time_errors:
        if isinstance(violation, dict):
            blocking_reasons.append(
                str(violation.get("reason") or "invalid_segment_time")
            )
    for violation in chronology_errors:
        if isinstance(violation, dict):
            blocking_reasons.append(
                str(violation.get("reason") or "invalid_time_order")
            )
    if airport_errors:
        blocking_reasons.append("airport_change_forbidden")
    if mct_errors:
        blocking_reasons.append("cross_ticket_mct_violation")
    if assessment.get("status") == "invalid":
        blocking_reasons.append("rejected_or_impossible_connection")
    if connections_over_limit:
        blocking_reasons.append("exceeds_max_connections_per_journey")
    blocking_reasons = _ordered_unique(blocking_reasons)

    if segment_time_errors or chronology_errors or airport_errors or mct_errors:
        item["candidate_status"] = "impossible"
        item["connection_status"] = "impossible"
    if segment_time_errors:
        item["segment_time_violations"] = segment_time_errors
    if chronology_errors:
        item["chronology_violations"] = chronology_errors
    if airport_errors:
        item["airport_mismatch_violations"] = airport_errors
    if mct_errors:
        item["mct_violations"] = mct_errors
    journey_pairing = _journey_pairing_metadata(
        candidate,
        chronology_violations=chronology_errors,
    )
    if journey_pairing:
        item["journey_pairing_model"] = journey_pairing["ticketing_model"]
        item["direction_pairing"] = journey_pairing
    item["max_connections_per_journey"] = connections
    item["connection_assessment"] = assessment
    item["ticket_protection"] = _ticket_protection(candidate)
    item["validation"] = {
        "schema_version": CANDIDATE_VALIDATION_SCHEMA_VERSION,
        "status": "invalid" if blocking_reasons else "valid",
        "blocking_reasons": blocking_reasons,
        "connections_over_limit": connections_over_limit,
    }
    return item


def _normalize_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(candidate)
    model, warnings = _normalize_ticketing_model(normalized)
    normalized["ticketing_model"] = model
    normalized["warnings"] = _ordered_unique(
        [*(normalized.get("warnings") or []), *warnings]
    )
    return normalized


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


def candidate_declared_blocking_reasons(candidate: Mapping[str, Any]) -> list[str]:
    """Return explicit upstream rejection facts without deriving route policy."""

    reasons: list[str] = []
    if candidate.get("covers_requested_trip") is False:
        reasons.append("does_not_cover_requested_trip")
    status = (
        str(
            candidate.get("connection_status")
            or candidate.get("candidate_status")
            or candidate.get("status")
            or ""
        )
        .strip()
        .lower()
    )
    if status in {"rejected", "impossible", "invalid", "error"}:
        reasons.append("rejected_or_impossible_connection")
    warnings = {str(item).strip().lower() for item in candidate.get("warnings") or []}
    if warnings & {
        "impossible_connection",
        "connection_rejected",
        "airport_mismatch",
    }:
        reasons.append("rejected_or_impossible_connection")
    return _ordered_unique(reasons)


def _ticket_protection(candidate: dict[str, Any]) -> dict[str, Any]:
    model = str(candidate.get("ticketing_model") or "unknown")
    protected_models = {
        "single_pnr_proven",
        "single_ticket_proven",
        "protected_provider_order",
        "round_trip_single_ticket",
    }
    separate_models = {"separate_ticket_sum"}
    if model in protected_models and _has_ticketing_proof(candidate):
        return {"status": "protected", "source": "provider_proof", "reasons": []}
    if candidate.get("self_transfer") is True or model in separate_models:
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
    if model == "separate_ticket_sum":
        return "one_way_sum"
    if model == "provider_order_unverified":
        return "round_trip_provider_order_unverified"
    return model or "unknown"


__all__ = [
    "CANDIDATE_VALIDATION_SCHEMA_VERSION",
    "validate_candidate_envelope",
]
