from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..config import (
    DEFAULT_FIRST_CARRIER_MAX_OPTIONS,
    DEFAULT_GATEWAY_MAX_ALTERNATIVES,
    DEFAULT_PRIMARY_GATEWAY_MAX_OPTIONS,
)
from ..domain.connection_policy import (
    DEFAULT_PREFERRED_LAYOVER_MAX_MIN,
    candidate_segment_groups as _candidate_segment_groups,
    normalized_direction as _normalized_direction,
)
from ..domain.normalize import numeric_or_none, ordered_unique as _ordered_unique
from ..domain.stop_policy import (
    BUSINESS_DEFAULT_STOP_POLICY,
    select_best_stop_tier,
    stop_tier,
)
from .candidate_scoring import UNKNOWN_RANK_NUMERIC, rank_component
from .candidate_directness import candidate_is_direct


DECISION_FRONTIER_SCHEMA_VERSION = "flight_decision_frontier.v1"
PREFERRED_LAYOVER_MAX_MIN = DEFAULT_PREFERRED_LAYOVER_MAX_MIN
DEFAULT_FRONTIER_MAX_OPTIONS = 6


def build_decision_frontier(
    mixed_candidate_ranking: dict[str, Any],
    *,
    max_gateway_alternatives: int = DEFAULT_GATEWAY_MAX_ALTERNATIVES,
    max_options: int | None = DEFAULT_FRONTIER_MAX_OPTIONS,
    max_primary_gateway_options: int = DEFAULT_PRIMARY_GATEWAY_MAX_OPTIONS,
    max_options_per_first_carrier: int = DEFAULT_FIRST_CARRIER_MAX_OPTIONS,
    preferred_connections_per_journey: int = (
        BUSINESS_DEFAULT_STOP_POLICY.preferred_max_connections
    ),
    preferred_layover_max_min: int = PREFERRED_LAYOVER_MAX_MIN,
) -> dict[str, Any]:
    ranked = [
        candidate
        for candidate in mixed_candidate_ranking.get("ranked_candidates") or []
        if isinstance(candidate, dict)
    ]
    acceptable = [candidate for candidate in ranked if _frontier_acceptable(candidate)]
    direct_ranked = [
        candidate for candidate in ranked if candidate_is_direct(candidate)
    ]
    direct_acceptable = [
        candidate for candidate in acceptable if candidate_is_direct(candidate)
    ]
    eligible_direct = [
        candidate for candidate in acceptable if candidate_is_direct(candidate)
    ]
    if eligible_direct:
        selection_pool = eligible_direct
        direct_limit = (
            len(eligible_direct) if max_options is None else max(0, int(max_options))
        )
        selected_candidates = eligible_direct[:direct_limit]
        selection_reasons = {
            str(candidate.get("id") or ""): [
                "best_viable" if index == 0 else "ranked_acceptable"
            ]
            for index, candidate in enumerate(selected_candidates)
        }
    else:
        selection_pool = _frontier_selection_pool(
            acceptable,
            preferred_connections_per_journey=preferred_connections_per_journey,
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


def _frontier_selection_pool(
    acceptable: list[dict[str, Any]],
    *,
    preferred_connections_per_journey: int,
    preferred_layover_max_min: int,
) -> list[dict[str, Any]]:
    if not acceptable:
        return []

    tier_pool = select_best_stop_tier(
        acceptable,
        preferred_max_connections=preferred_connections_per_journey,
    )

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
    return 0 if _scored_max_connections(candidate) == 0 else UNKNOWN_RANK_NUMERIC


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
        rank_component(candidate, "connection_risk_score"),
        rank_component(candidate, "ticketing_risk_tier"),
        rank_component(candidate, "source_confidence_penalty"),
        rank_component(candidate, "price"),
        rank_component(candidate, "elapsed_time"),
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
        cheapest = _min_finite(
            selected, lambda candidate: rank_component(candidate, "price")
        )
        if cheapest is not None:
            cheapest_id = str(cheapest.get("id") or "")
            reasons[cheapest_id] = _ordered_unique(
                [*(reasons.get(cheapest_id) or []), "cheapest_selected"]
            )
        fastest = _min_finite(
            selected, lambda candidate: rank_component(candidate, "elapsed_time")
        )
        if fastest is not None:
            fastest_id = str(fastest.get("id") or "")
            reasons[fastest_id] = _ordered_unique(
                [*(reasons.get(fastest_id) or []), "fastest_selected"]
            )
    return selected, reasons


# Почему вариант стоит ниже предыдущего. Порядок обязан совпадать с rank_key
# из candidate_scoring: индекс здесь — это позиция компонента там. Ключ
# ранжирования наружу не уезжает, уезжает только его прочтение.
RANK_REASON_BY_RANK_KEY_INDEX: tuple[str, ...] = (
    "does_not_cover_trip",
    "invalid_connection",
    "more_connections",
    "over_preferred_connections",
    "connection_comfort",
    "slower",
    "ticketing_risk",
    "source_confidence",
    "costlier",
    "slower",
)
_ELAPSED_RANK_KEY_INDEXES = frozenset({5, 9})


def _rank_key(candidate: dict[str, Any]) -> list[float]:
    raw = candidate.get("rank_key")
    if not isinstance(raw, list):
        return []
    return [float(numeric_or_none(value) or 0) for value in raw]


def _rank_reason(
    candidate: dict[str, Any], previous: dict[str, Any] | None
) -> dict[str, Any]:
    if previous is None:
        return {"code": "top_ranked", "detail_min": None}
    current, earlier = _rank_key(candidate), _rank_key(previous)
    for index, (mine, theirs) in enumerate(zip(current, earlier)):
        if mine == theirs or index >= len(RANK_REASON_BY_RANK_KEY_INDEX):
            continue
        detail = None
        if index in _ELAPSED_RANK_KEY_INDEXES:
            mine_elapsed = numeric_or_none(candidate.get("elapsed_min"))
            their_elapsed = numeric_or_none(previous.get("elapsed_min"))
            if mine_elapsed is not None and their_elapsed is not None:
                detail = int(mine_elapsed - their_elapsed)
        return {"code": RANK_REASON_BY_RANK_KEY_INDEX[index], "detail_min": detail}
    return {"code": "costlier", "detail_min": None}


def _frontier_options_with_roles(
    candidates: list[dict[str, Any]],
    *,
    selection_reasons: dict[str, list[str]],
) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for candidate in candidates:
        roles = selection_reasons.get(str(candidate.get("id") or "")) or [
            "carrier_diversity"
        ]
        option = _frontier_option(candidate, roles[0])
        option["selection_reasons"] = _ordered_unique(roles)
        option["rank_reason"] = _rank_reason(candidate, previous)
        options.append(option)
        previous = candidate
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
    validation = candidate.get("validation")
    return isinstance(validation, dict) and validation.get("status") == "valid"


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
    max_connections = _scored_max_connections(candidate)
    option["connection_count"] = max_connections
    option["max_connections_per_journey"] = max_connections
    option["stop_tier"] = stop_tier(max_connections)
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


def _scored_max_connections(candidate: dict[str, Any]) -> int:
    value = numeric_or_none(candidate.get("max_connections_per_journey"))
    return max(0, int(value)) if value is not None else 0


def _direct_option_count_by_direction(
    candidates: list[dict[str, Any]],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        if not candidate_is_direct(candidate):
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


__all__ = [
    "DEFAULT_FRONTIER_MAX_OPTIONS",
    "DECISION_FRONTIER_SCHEMA_VERSION",
    "build_decision_frontier",
]
