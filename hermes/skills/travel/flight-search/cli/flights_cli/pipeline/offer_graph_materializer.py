from __future__ import annotations

from typing import Any, Mapping

from ..domain.normalize import (
    compact_mapping as _compact,
    currency_value as _currency,
    normalize_code as _normalize_code,
    ordered_unique as _ordered_unique,
    price_amount as _price_amount,
    stable_id as _stable_id,
)
from ..domain.offer_paths import (
    normalize_direction as _normalize_direction,
    segment_dicts as _segment_dicts,
    segment_destination as _segment_destination,
    segment_origin as _segment_origin,
)
from ..domain.vocabulary import RouteFamily, normalize_direction as _direction_of
from .candidate_directness import (
    candidate_direct_mode_violation as _candidate_direct_mode_violation,
    candidate_is_direct as _candidate_is_direct,
    requested_airport_codes as _requested_codes,
)
from .offer_graph_merge import dedupe_candidates as _dedupe_candidates
from .offer_graph_model import OFFER_CANDIDATE_ENVELOPE_SCHEMA_VERSION


def _route_from_segments(segments: list[Any]) -> list[str]:
    route: list[str] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        origin = _normalize_code(_segment_origin(segment))
        destination = _normalize_code(_segment_destination(segment))
        if origin and not route:
            route.append(origin)
        if destination:
            route.append(destination)
    return route


def _self_transfer_fields(offer: dict[str, Any]) -> dict[str, Any]:
    return {
        key: offer.get(key)
        for key in (
            "self_transfer",
            "self_transfer_note",
            "self_transfer_source",
        )
        if key in offer
    }


def materialize_offer_graph_candidates(
    offer_graph: dict[str, Any],
    *,
    round_trip: bool = False,
    direct_only: bool = False,
    requested_origin: str | None = None,
    requested_destination: str | None = None,
    requested_origin_airports: list[str] | None = None,
    requested_destination_airports: list[str] | None = None,
    requested_dates: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project graph evidence into a unified, unranked candidate envelope."""

    offers = [
        offer for offer in offer_graph.get("offers") or [] if isinstance(offer, dict)
    ]
    edges = [edge for edge in offer_graph.get("edges") or [] if isinstance(edge, dict)]
    edges_by_id = {str(edge.get("id") or ""): edge for edge in edges}
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    allowed_dates = {
        _direction_of(direction): {str(date) for date in dates or () if date}
        for direction, dates in (requested_dates or {}).items()
    }

    for offer in offers:
        candidate = _candidate_from_offer(
            offer,
            edges_by_id,
            requested_origin=requested_origin,
            requested_destination=requested_destination,
            requested_origin_airports=requested_origin_airports,
            requested_destination_airports=requested_destination_airports,
        )
        _accept_or_reject_candidate(
            candidate,
            candidates,
            rejected,
            direct_only=direct_only,
            allowed_dates=allowed_dates,
        )

    candidates, direct_mode = _hide_connections_where_direct_exists(
        candidates, rejected
    )
    candidates, deduped_count = _dedupe_candidates(candidates)
    return {
        "schema_version": OFFER_CANDIDATE_ENVELOPE_SCHEMA_VERSION,
        "candidates": candidates,
        "rejected": rejected,
        "coverage": {
            "candidate_count": len(candidates),
            "rejected_count": len(rejected),
            "deduped_count": deduped_count,
            "direct_only": bool(direct_only),
            "direct_mode": {
                str(direction): bool(enabled)
                for direction, enabled in direct_mode.items()
                if enabled
            },
            "source_types": sorted(
                {
                    str(candidate.get("source_type"))
                    for candidate in candidates
                    if candidate.get("source_type")
                }
            ),
        },
    }


def _candidate_from_offer(
    offer: dict[str, Any],
    edges_by_id: dict[str, dict[str, Any]],
    *,
    requested_origin: str | None,
    requested_destination: str | None,
    requested_origin_airports: list[str] | None,
    requested_destination_airports: list[str] | None,
) -> dict[str, Any]:
    source_type = str(offer.get("source_type") or "provider_full_route")
    candidate_source_type = source_type
    if source_type == RouteFamily.DIRECT_INVENTORY:
        candidate_source_type = RouteFamily.DIRECT_INVENTORY
    elif source_type != "provider_full_route":
        candidate_source_type = "provider_full_route"
    edge_ids = [str(edge_id) for edge_id in offer.get("edge_ids") or []]
    segments = _segments_for_edge_ids(edge_ids, edges_by_id)
    journeys = _journeys_from_segments_by_direction(
        segments,
        fallback_direction=_normalize_direction(offer.get("direction")) or "outbound",
    )
    detail_status = _candidate_detail_status(offer, segments)
    price = _price_amount(offer)
    currency = _currency(offer)
    warnings = _candidate_warnings(offer, detail_status=detail_status)
    return {
        "id": _stable_id("candidate", offer.get("id")),
        "source_type": candidate_source_type,
        "provider": offer.get("provider"),
        "source_providers": _ordered_unique([offer.get("provider")]),
        "covers_requested_trip": _covers_requested_trip(
            segments,
            offer,
            journeys=journeys,
            requested_origin=requested_origin,
            requested_destination=requested_destination,
            requested_origin_airports=requested_origin_airports,
            requested_destination_airports=requested_destination_airports,
            detail_status=detail_status,
        ),
        "journey_scope": str(offer.get("journey_scope") or "one_way"),
        "price": price,
        "currency": currency,
        "price_basis": "provider_offer_price" if price is not None else "unknown",
        "ticketing_model": str(
            offer.get("ticketing_model") or "provider_order_unverified"
        ),
        **_self_transfer_fields(offer),
        "detail_status": detail_status,
        "journeys": journeys,
        "warnings": warnings,
        "offer_ids": [offer.get("id")],
        "edge_ids": edge_ids,
    }


def _departure_date_outside_request(
    candidate: dict[str, Any], allowed_dates: dict[str, set[str]]
) -> bool:
    """Вылет не в тот день, который спрашивали у провайдера."""
    journeys = candidate.get("journeys")
    if not isinstance(journeys, list):
        return False
    for journey in journeys:
        if not isinstance(journey, Mapping):
            continue
        allowed = allowed_dates.get(_direction_of(journey.get("direction")))
        if not allowed:
            continue
        segments = [
            segment
            for segment in journey.get("segments") or []
            if isinstance(segment, Mapping)
        ]
        if not segments:
            continue
        departure_date = str(segments[0].get("departure_at") or "")[:10]
        if departure_date and departure_date not in allowed:
            return True
    return False


def _accept_or_reject_candidate(
    candidate: dict[str, Any],
    candidates: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    *,
    direct_only: bool,
    allowed_dates: dict[str, set[str]] | None = None,
) -> None:
    if direct_only and not _candidate_is_direct(candidate):
        rejected.append(
            {
                "candidate_id": candidate.get("id"),
                "source_type": candidate.get("source_type"),
                "reason": "direct_only_hard_constraint",
            }
        )
        return
    if allowed_dates and _departure_date_outside_request(candidate, allowed_dates):
        rejected.append(
            {
                "candidate_id": candidate.get("id"),
                "source_type": candidate.get("source_type"),
                "reason": "departure_date_outside_request",
            }
        )
        return
    candidates.append(candidate)


def _directions_with_direct(candidates: list[dict[str, Any]]) -> set[str]:
    """Направления, на которых среди кандидатов есть прямой рейс."""
    directions: set[str] = set()
    for candidate in candidates:
        journeys = candidate.get("journeys")
        if not isinstance(journeys, list):
            continue
        for journey in journeys:
            if not isinstance(journey, Mapping):
                continue
            segments = [
                segment
                for segment in journey.get("segments") or []
                if isinstance(segment, Mapping)
            ]
            if len(segments) == 1:
                directions.add(_direction_of(journey.get("direction")))
    return directions


def _hide_connections_where_direct_exists(
    candidates: list[dict[str, Any]], rejected: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, bool]]:
    """Есть прямые на направлении — стыковочные варианты туда не показываем.

    Раньше это решалось по сырым ответам провайдера, до того как кандидаты
    построены: гейту надо было ответить рано, чтобы решить, слать ли вторую
    пробу. Двухфазности больше нет, и вопрос задаётся там, где на него уже
    есть ответ, — на самих кандидатах.
    """
    direct_mode = {direction: True for direction in _directions_with_direct(candidates)}
    if not direct_mode:
        return candidates, direct_mode
    kept: list[dict[str, Any]] = []
    for candidate in candidates:
        violation = _candidate_direct_mode_violation(candidate, direct_mode)
        if violation is None:
            kept.append(candidate)
            continue
        rejected.append(
            {
                "candidate_id": candidate.get("id"),
                "source_type": candidate.get("source_type"),
                "reason": "direct_mode_gate",
                "direction": violation,
            }
        )
    return kept, direct_mode


def _segments_for_edge_ids(
    edge_ids: list[str], edges_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for index, edge_id in enumerate(edge_ids):
        edge = edges_by_id.get(edge_id)
        if not isinstance(edge, dict):
            continue
        segments.append(
            _compact(
                {
                    "origin": _normalize_code(edge.get("origin")),
                    "destination": _normalize_code(edge.get("destination")),
                    "provider": edge.get("provider"),
                    "offer_id": edge.get("offer_id"),
                    "edge_id": edge.get("id"),
                    "sequence": edge.get("sequence", index),
                    "source_type": edge.get("source_type"),
                    "ticketing_boundary": edge.get("ticketing_boundary"),
                    "ticketing_model": edge.get("ticketing_model"),
                    "direction": edge.get("direction"),
                    "flight_number": edge.get("flight_number"),
                    "marketing_carrier": edge.get("marketing_carrier"),
                    "operating_carrier": edge.get("operating_carrier"),
                    "carrier": edge.get("carrier"),
                    "carrier_name": edge.get("carrier_name"),
                    "departure_at": edge.get("departure_at"),
                    "arrival_at": edge.get("arrival_at"),
                }
            )
        )
    return segments


def _journeys_from_segments(
    segments: list[dict[str, Any]], *, direction: str
) -> list[dict[str, Any]]:
    if not segments:
        return []
    return [{"direction": direction, "segments": segments}]


def _journeys_from_segments_by_direction(
    segments: list[dict[str, Any]], *, fallback_direction: str
) -> list[dict[str, Any]]:
    if not segments:
        return []
    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for segment in segments:
        direction = (
            _normalize_direction(segment.get("direction"))
            or _normalize_direction(fallback_direction)
            or "outbound"
        )
        if direction not in groups:
            groups[direction] = []
            order.append(direction)
        groups[direction].append(segment)
    return [
        {"direction": direction, "segments": groups[direction]}
        for direction in order
        if groups[direction]
    ]


def _candidate_detail_status(
    offer: dict[str, Any], segments: list[dict[str, Any]]
) -> str:
    explicit = str(offer.get("detail_status") or "").strip().lower()
    if explicit in {"full", "summary_only", "missing"}:
        return explicit
    return "full" if segments else "summary_only"


def _candidate_warnings(offer: dict[str, Any], *, detail_status: str) -> list[str]:
    warnings = [str(item) for item in offer.get("warnings") or [] if item]
    if detail_status == "summary_only" and "summary_only_offer_details" not in warnings:
        warnings.append("summary_only_offer_details")
    if detail_status == "missing" and "missing_offer_details" not in warnings:
        warnings.append("missing_offer_details")
    return _ordered_unique(warnings)


def _covers_requested_trip(
    segments: list[dict[str, Any]],
    offer: dict[str, Any],
    *,
    journeys: list[dict[str, Any]] | None,
    requested_origin: str | None,
    requested_destination: str | None,
    requested_origin_airports: list[str] | None,
    requested_destination_airports: list[str] | None,
    detail_status: str,
) -> bool:
    if detail_status != "full":
        return False
    origin = _normalize_code(requested_origin)
    destination = _normalize_code(requested_destination)
    origin_codes = _requested_codes(origin, requested_origin_airports)
    destination_codes = _requested_codes(destination, requested_destination_airports)
    if origin_codes and destination_codes and journeys:
        by_direction: dict[str, list[dict[str, Any]]] = {}
        for journey in journeys:
            if not isinstance(journey, dict):
                continue
            direction = _normalize_direction(journey.get("direction"))
            journey_segments = _segment_dicts(journey.get("segments"))
            if direction and journey_segments:
                by_direction[direction] = journey_segments
        outbound = by_direction.get("outbound") or []
        inbound = by_direction.get("return") or []
        if outbound and inbound:
            return (
                _normalize_code(outbound[0].get("origin")) in origin_codes
                and _normalize_code(outbound[-1].get("destination"))
                in destination_codes
                and _normalize_code(inbound[0].get("origin")) in destination_codes
                and _normalize_code(inbound[-1].get("destination")) in origin_codes
            )
        if set(by_direction) == {"return"}:
            origin_codes, destination_codes = destination_codes, origin_codes
    elif _normalize_direction(offer.get("direction")) == "return":
        origin_codes, destination_codes = destination_codes, origin_codes
    if not origin_codes and not destination_codes:
        return bool(segments)
    route_origin = (
        _normalize_code(segments[0].get("origin"))
        if segments
        else _normalize_code(offer.get("origin"))
    )
    route_destination = (
        _normalize_code(segments[-1].get("destination"))
        if segments
        else _normalize_code(offer.get("destination"))
    )
    if origin_codes and route_origin not in origin_codes:
        return False
    if destination_codes and route_destination not in destination_codes:
        return False
    return bool(route_origin and route_destination)


__all__ = ["materialize_offer_graph_candidates"]
