from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..domain.vocabulary import IntentClass, RouteFamily


MIXED_CANDIDATE_RANKING_SCHEMA_VERSION = "flight_mixed_candidate_ranking.v1"
UNKNOWN_RANK_NUMERIC = 999_999_999


def rank_mixed_candidates(
    candidate_envelope: dict[str, Any],
    *,
    legacy_candidates: list[dict[str, Any]] | None = None,
    max_connections_per_journey: int = 2,
) -> dict[str, Any]:
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
            "source_types": sorted(
                {
                    str(candidate.get("source_type"))
                    for candidate in ranked
                    if candidate.get("source_type")
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
) -> dict[str, Any]:
    item = deepcopy(candidate)
    max_connections = _max_connections(candidate)
    rank_components = {
        "hard_constraint_violation": 1 if _has_hard_constraint_violation(candidate) else 0,
        "not_covers_requested_trip": 0
        if bool(candidate.get("covers_requested_trip"))
        else 1,
        "rejected_or_impossible_connection": 1
        if _has_impossible_connection(candidate)
        else 0,
        "max_connections_per_journey": max(
            0,
            max_connections - max(0, int(max_connections_per_journey)),
        ),
        "ticketing_risk_tier": _ticketing_risk_tier(candidate),
        "connection_risk_score": _connection_risk_score(candidate),
        "source_confidence_penalty": _source_confidence_penalty(candidate),
        "price": _price_for_rank(candidate),
        "elapsed_time": _elapsed_time_for_rank(candidate),
    }
    item["rank_components"] = rank_components
    item["rank_key"] = [
        rank_components["hard_constraint_violation"],
        rank_components["not_covers_requested_trip"],
        rank_components["rejected_or_impossible_connection"],
        rank_components["max_connections_per_journey"],
        rank_components["ticketing_risk_tier"],
        rank_components["connection_risk_score"],
        rank_components["source_confidence_penalty"],
        rank_components["price"],
        rank_components["elapsed_time"],
    ]
    item["ranking_reasons"] = _ranking_reasons(candidate, rank_components)
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
        return "provider_order_unverified", [
            "provider_ticketing_protection_unverified"
        ]
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


def _has_hard_constraint_violation(candidate: dict[str, Any]) -> bool:
    if bool(candidate.get("hard_constraint_violation")):
        return True
    violations = candidate.get("hard_constraint_violations")
    return isinstance(violations, list) and bool(violations)


def _has_impossible_connection(candidate: dict[str, Any]) -> bool:
    status = str(
        candidate.get("connection_status")
        or candidate.get("candidate_status")
        or ""
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


def _ticketing_risk_tier(candidate: dict[str, Any]) -> int:
    model = str(candidate.get("ticketing_model") or "unknown")
    source_type = str(candidate.get("source_type") or "")
    if model in {"single_pnr_proven", "single_ticket_proven", "protected_provider_order"}:
        return 0
    if source_type == RouteFamily.DIRECT_INVENTORY:
        return 0
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
    if rank_components["max_connections_per_journey"]:
        reasons.append("exceeds_max_connections_per_journey")
    if candidate.get("source_type") == "gateway_separate_ticket":
        reasons.append("separate_ticket_ranked_after_provider_route_evidence")
    if "provider_ticketing_protection_unverified" in set(
        candidate.get("warnings") or []
    ):
        reasons.append("provider_ticketing_protection_unverified")
    return reasons


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


def _ordered_unique(items: list[Any]) -> list[str]:
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
    "MIXED_CANDIDATE_RANKING_SCHEMA_VERSION",
    "rank_mixed_candidates",
]
