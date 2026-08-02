from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..domain.carriers import carrier_from_flight_number
from ..domain.connection_policy import (
    airport_mismatch_violations,
    chronology_violations,
    missing_segment_time_violations,
)
from ..domain.offer_paths import (
    offer_segment_paths,
    provider_result_offers,
    segment_destination,
    segment_origin,
)
from ..domain.vocabulary import Direction
from .candidate_validation import candidate_declared_blocking_reasons
from .search_request import SearchRequest


def is_direct_only(request: SearchRequest) -> bool:
    return request.max_connections == 0 and request.tier2_max_connections == 0


def normalize_direction(value: Any) -> str:
    return (
        Direction.RETURN
        if str(value or Direction.OUTBOUND).strip().lower() == Direction.RETURN
        else Direction.OUTBOUND
    )


def requested_directions(route: Mapping[str, Any]) -> tuple[str, ...]:
    directions = [Direction.OUTBOUND]
    if (route.get("dates") or {}).get("return"):
        directions.append(Direction.RETURN)
    return tuple(directions)


def _airport_set(*values: Any) -> set[str]:
    return {str(value).strip().upper() for value in values if str(value or "").strip()}


def requested_airport_codes(
    value: str | None, airport_scope: list[str] | None = None
) -> set[str]:
    scoped = _airport_set(*(airport_scope or []))
    return scoped or _airport_set(value)


def _requested_airport_pair(
    route: Mapping[str, Any], direction: str
) -> tuple[set[str], set[str]]:
    origin = route.get("origin")
    destination = route.get("destination")
    origin_airports = list(route.get("origin_airports") or [])
    destination_airports = list(route.get("destination_airports") or [])
    if normalize_direction(direction) == Direction.RETURN:
        return (
            _airport_set(destination, *destination_airports),
            _airport_set(origin, *origin_airports),
        )
    return (
        _airport_set(origin, *origin_airports),
        _airport_set(destination, *destination_airports),
    )


def _path_is_requested_direct(
    path: Mapping[str, Any],
    *,
    requested_origins: set[str],
    requested_destinations: set[str],
) -> bool:
    segments = path.get("segments") or []
    if len(segments) != 1 or not isinstance(segments[0], dict):
        return False
    segment = segments[0]
    return (
        segment_origin(segment) in requested_origins
        and segment_destination(segment) in requested_destinations
    )


def _segment_carriers(segment: Mapping[str, Any]) -> set[str]:
    carriers = {
        str(segment.get(key) or "").strip().upper()
        for key in ("carrier", "marketing_carrier", "operating_carrier")
        if str(segment.get(key) or "").strip()
    }
    from_flight_number = carrier_from_flight_number(
        str(segment.get("flight_number") or "")
    )
    if from_flight_number:
        carriers.add(from_flight_number.upper())
    return carriers


def _path_is_eligible(
    path: Mapping[str, Any],
    *,
    requested_origins: set[str],
    requested_destinations: set[str],
    only_carriers: set[str],
    requested_date: str | None,
    direct_only: bool,
    max_connections_per_journey: int | None = None,
) -> bool:
    segments = path.get("segments") or []
    if (
        not isinstance(segments, list)
        or not segments
        or any(not isinstance(segment, dict) for segment in segments)
        or (direct_only and len(segments) != 1)
    ):
        return False
    if max_connections_per_journey is not None and len(segments) - 1 > max(
        0, int(max_connections_per_journey)
    ):
        return False
    if (
        segment_origin(segments[0]) not in requested_origins
        or segment_destination(segments[-1]) not in requested_destinations
    ):
        return False
    candidate = {
        "journeys": [
            {
                "direction": normalize_direction(path.get("direction")),
                "segments": segments,
            }
        ]
    }
    if (
        missing_segment_time_violations(candidate)
        or chronology_violations(candidate)
        or airport_mismatch_violations(candidate)
    ):
        return False
    departure_date = str(segments[0].get("departure_at") or "")[:10]
    if requested_date and departure_date != requested_date:
        return False
    if not only_carriers:
        return True
    return all(bool(_segment_carriers(segment) & only_carriers) for segment in segments)


def provider_result_has_eligible_path(
    result: Mapping[str, Any],
    query: Mapping[str, Any],
    *,
    only_carriers: tuple[str, ...] | list[str] = (),
    max_connections_per_journey: int | None = None,
) -> bool:
    """Decide whether a provider result contains usable evidence for its query."""

    if str(result.get("execution_state") or "") in {
        "failed",
        "not_supported",
        "skipped",
        "not_executed",
    }:
        return False
    requested_origins = requested_airport_codes(
        str(query.get("origin") or ""), list(query.get("origin_airports") or [])
    )
    requested_destinations = requested_airport_codes(
        str(query.get("destination") or ""),
        list(query.get("destination_airports") or []),
    )
    carrier_scope = {
        str(carrier).strip().upper()
        for carrier in (query.get("only_carriers") or only_carriers)
        if str(carrier).strip()
    }
    result_direction = normalize_direction(
        result.get("direction") or query.get("direction")
    )
    for offer in provider_result_offers(dict(result)) or []:
        if not isinstance(offer, dict) or candidate_declared_blocking_reasons(offer):
            continue
        for path in offer_segment_paths(offer, fallback_direction=result_direction):
            if _path_is_eligible(
                path,
                requested_origins=requested_origins,
                requested_destinations=requested_destinations,
                only_carriers=carrier_scope,
                requested_date=str(query.get("date") or "") or None,
                direct_only=bool(query.get("direct_only")),
                max_connections_per_journey=max_connections_per_journey,
            ):
                return True
    return False


def candidate_is_direct(candidate: Mapping[str, Any]) -> bool:
    journeys = candidate.get("journeys")
    if not isinstance(journeys, list) or not journeys:
        return False
    if candidate.get("source_type") == "gateway_separate_ticket":
        return False
    return all(
        isinstance(journey, Mapping)
        and isinstance(journey.get("segments"), list)
        and len(journey["segments"]) == 1
        and isinstance(journey["segments"][0], Mapping)
        for journey in journeys
    )


def candidate_direct_mode_violation(
    candidate: Mapping[str, Any], direct_mode: Mapping[str, bool]
) -> str | None:
    active = {
        normalize_direction(direction)
        for direction, enabled in direct_mode.items()
        if enabled
    }
    if not active:
        return None
    journeys = candidate.get("journeys")
    if not isinstance(journeys, list) or not journeys:
        return next(iter(active))
    for journey in journeys:
        if not isinstance(journey, Mapping):
            continue
        direction = normalize_direction(journey.get("direction"))
        if direction not in active:
            continue
        segments = [
            segment
            for segment in journey.get("segments") or []
            if isinstance(segment, Mapping)
        ]
        if (
            len(segments) != 1
            or candidate.get("source_type") == "gateway_separate_ticket"
        ):
            return direction
    return None


def direct_evidence_by_direction(
    route: Mapping[str, Any],
    primary_results: list[dict[str, Any]],
    *,
    only_carriers: tuple[str, ...] | list[str] = (),
) -> dict[str, bool]:
    evidence = {direction: False for direction in requested_directions(route)}
    carrier_scope = {
        str(carrier).strip().upper()
        for carrier in only_carriers
        if str(carrier).strip()
    }
    for result in primary_results:
        if not isinstance(result, dict):
            continue
        if str(result.get("execution_state") or "") in {
            "failed",
            "not_supported",
            "skipped",
            "not_executed",
        }:
            continue
        result_direction = normalize_direction(result.get("direction"))
        for offer in provider_result_offers(result):
            if not isinstance(offer, dict) or candidate_declared_blocking_reasons(
                offer
            ):
                continue
            for path in offer_segment_paths(offer, fallback_direction=result_direction):
                path_direction = normalize_direction(path.get("direction"))
                if path_direction not in evidence:
                    continue
                requested_origins, requested_destinations = _requested_airport_pair(
                    route, path_direction
                )
                if _path_is_requested_direct(
                    path,
                    requested_origins=requested_origins,
                    requested_destinations=requested_destinations,
                ) and _path_is_eligible(
                    path,
                    requested_origins=requested_origins,
                    requested_destinations=requested_destinations,
                    only_carriers=carrier_scope,
                    requested_date=str(
                        (route.get("dates") or {}).get(
                            "return" if path_direction == Direction.RETURN else "depart"
                        )
                        or ""
                    )
                    or None,
                    direct_only=True,
                    max_connections_per_journey=0,
                ):
                    evidence[path_direction] = True
    return evidence


def primary_failure_by_direction(
    route: Mapping[str, Any], primary_results: list[dict[str, Any]]
) -> dict[str, bool]:
    failures = {direction: False for direction in requested_directions(route)}
    for result in primary_results:
        if not isinstance(result, dict):
            continue
        direction = normalize_direction(result.get("direction"))
        if direction not in failures:
            continue
        if str(result.get("execution_state") or "") in {"failed", "not_supported"}:
            failures[direction] = True
    return failures


@dataclass(frozen=True, slots=True)
class DirectGateDecision:
    direct_evidence_present: dict[str, bool]
    direct_mode: dict[str, bool]
    primary_failure: dict[str, bool]
    reasons_by_direction: dict[str, tuple[str, ...]]

    def connection_caps(self, fallback_cap: int) -> dict[str, int]:
        return {
            direction: 0 if direct_present else max(0, int(fallback_cap))
            for direction, direct_present in self.direct_mode.items()
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "flight_direct_presence_gate.v1",
            "direct_evidence_present": dict(self.direct_evidence_present),
            "direct_mode": dict(self.direct_mode),
            "primary_failure": dict(self.primary_failure),
            "reasons_by_direction": {
                direction: list(reasons)
                for direction, reasons in self.reasons_by_direction.items()
            },
            "source": "direct_primary_offer_results",
        }


def evaluate_direct_gate(
    route: Mapping[str, Any],
    primary_results: list[dict[str, Any]],
    *,
    only_carriers: tuple[str, ...] | list[str] = (),
) -> DirectGateDecision:
    evidence = direct_evidence_by_direction(
        route, primary_results, only_carriers=only_carriers
    )
    failures = primary_failure_by_direction(route, primary_results)
    return DirectGateDecision(
        direct_evidence_present=evidence,
        direct_mode={
            direction: bool(present) for direction, present in evidence.items()
        },
        primary_failure=failures,
        reasons_by_direction={
            direction: (
                ("eligible_direct_present",)
                if present
                else ("primary_coverage_damaged",)
                if failures.get(direction, False)
                else ("no_eligible_direct",)
            )
            for direction, present in evidence.items()
        },
    )
