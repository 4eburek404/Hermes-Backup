from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from ..domain.normalize import numeric_or_none
from ..domain.vocabulary import RouteFamily


OFFER_GRAPH_SCHEMA_VERSION = "flight_offer_graph.v1"
OFFER_CANDIDATE_ENVELOPE_SCHEMA_VERSION = "flight_offer_candidate_envelope.v1"


@dataclass(frozen=True, slots=True)
class OfferGraph:
    edges: list[dict[str, Any]] = field(default_factory=list)
    offers: list[dict[str, Any]] = field(default_factory=list)
    connections: list[dict[str, Any]] = field(default_factory=list)
    coverage: dict[str, Any] = field(default_factory=dict)
    schema_version: str = OFFER_GRAPH_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "edges": deepcopy(self.edges),
            "offers": deepcopy(self.offers),
            "connections": deepcopy(self.connections),
            "coverage": deepcopy(self.coverage),
        }


def build_offer_graph(
    *,
    primary_offer_results: list[dict[str, Any]] | None = None,
    gateway_leg_results: dict[str, Any] | None = None,
    direct_mode: dict[str, bool] | None = None,
    requested_origin: str | None = None,
    requested_destination: str | None = None,
    requested_origin_airports: list[str] | None = None,
    requested_destination_airports: list[str] | None = None,
) -> dict[str, Any]:
    builder = OfferGraphBuilder(
        direct_mode=direct_mode,
        requested_origin=requested_origin,
        requested_destination=requested_destination,
        requested_origin_airports=requested_origin_airports,
        requested_destination_airports=requested_destination_airports,
    )
    builder.add_primary_offer_results(primary_offer_results or [])
    builder.add_gateway_leg_results(gateway_leg_results or {})
    return builder.to_graph().to_dict()


def materialize_offer_graph_candidates(
    offer_graph: dict[str, Any],
    *,
    direct_only: bool = False,
    direct_mode: dict[str, bool] | None = None,
    requested_origin: str | None = None,
    requested_destination: str | None = None,
    requested_origin_airports: list[str] | None = None,
    requested_destination_airports: list[str] | None = None,
    max_path_offers: int = 3,
) -> dict[str, Any]:
    """Project graph evidence into a unified, unranked candidate envelope."""

    offers = [
        offer for offer in offer_graph.get("offers") or [] if isinstance(offer, dict)
    ]
    edges = [edge for edge in offer_graph.get("edges") or [] if isinstance(edge, dict)]
    edges_by_id = {str(edge.get("id") or ""): edge for edge in edges}
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for offer in offers:
        source_type = str(offer.get("source_type") or "")
        if source_type == "gateway_leg":
            continue
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
            direct_mode=direct_mode or {},
        )

    for candidate in _candidates_from_gateway_offer_paths(
        offers,
        edges_by_id,
        requested_origin=requested_origin,
        requested_destination=requested_destination,
        requested_origin_airports=requested_origin_airports,
        requested_destination_airports=requested_destination_airports,
        max_path_offers=max_path_offers,
    ):
        _accept_or_reject_candidate(
            candidate,
            candidates,
            rejected,
            direct_only=direct_only,
            direct_mode=direct_mode or {},
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
                for direction, enabled in (direct_mode or {}).items()
                if enabled
            },
            "max_path_offers": max(1, int(max_path_offers)),
            "source_types": sorted(
                {
                    str(candidate.get("source_type"))
                    for candidate in candidates
                    if candidate.get("source_type")
                }
            ),
        },
    }


class OfferGraphBuilder:
    def __init__(
        self,
        *,
        direct_mode: dict[str, bool] | None = None,
        requested_origin: str | None = None,
        requested_destination: str | None = None,
        requested_origin_airports: list[str] | None = None,
        requested_destination_airports: list[str] | None = None,
    ) -> None:
        self.edges: list[dict[str, Any]] = []
        self.offers: list[dict[str, Any]] = []
        self.connections: list[dict[str, Any]] = []
        self._offer_ids: set[str] = set()
        self._edge_ids: set[str] = set()
        self.direct_mode = {
            _normalize_direction(direction): bool(enabled)
            for direction, enabled in (direct_mode or {}).items()
        }
        self.requested_origin = _normalize_code(requested_origin)
        self.requested_destination = _normalize_code(requested_destination)
        self.requested_origin_airports = _requested_codes(
            self.requested_origin, requested_origin_airports
        )
        self.requested_destination_airports = _requested_codes(
            self.requested_destination, requested_destination_airports
        )
        self.coverage: dict[str, Any] = {
            "primary_offer_result_count": 0,
            "gateway_count": 0,
            "provider_full_route_offer_count": 0,
            "gateway_leg_offer_count": 0,
            "direct_inventory_offer_count": 0,
            "assembled_separate_ticket_candidate_count": 0,
            "skipped_offer_count": 0,
            "skipped_reasons": [],
        }

    def add_primary_offer_results(self, results: list[dict[str, Any]]) -> None:
        self.coverage["primary_offer_result_count"] = len(results)
        for result_index, result in enumerate(results):
            if not isinstance(result, dict):
                self._skip("malformed_primary_offer_result")
                continue
            provider = _provider(result)
            source_type = str(result.get("source_type") or "provider_full_route")
            if source_type != "provider_full_route":
                source_type = "provider_full_route"
            offers = _provider_result_offers(result)
            if offers is None:
                self._skip("primary_offer_result_missing_offers")
                continue
            for offer_index, offer in enumerate(offers):
                if not isinstance(offer, dict):
                    self._skip("malformed_primary_offer")
                    continue
                paths = _offer_segment_paths(
                    offer,
                    fallback_direction=_normalize_direction(result.get("direction")),
                )
                if not paths:
                    self._add_primary_summary_offer(
                        result,
                        offer,
                        provider=provider,
                        result_index=result_index,
                        offer_index=offer_index,
                    )
                    continue
                if _is_atomic_round_trip_offer(offer, paths):
                    if any(
                        self._primary_path_blocked_by_direct_mode(
                            path["segments"], direction=path.get("direction")
                        )
                        for path in paths
                    ):
                        self._skip("direct_mode_gate")
                        continue
                    offer_id = self._unique_offer_id(
                        "primary_offer",
                        provider,
                        _offer_id(offer)
                        or f"result{result_index + 1}-offer{offer_index + 1}",
                    )
                    edge_ids: list[str] = []
                    for path_index, path in enumerate(paths):
                        edge_ids.extend(
                            self._add_route_edges(
                                offer_id=offer_id,
                                provider=provider,
                                source_type=source_type,
                                ticketing_boundary="provider_protected_full_route",
                                segments=path["segments"],
                                direction=path.get("direction"),
                                source_debug={
                                    "result_index": result_index,
                                    "offer_index": offer_index,
                                    **(path.get("debug") or {}),
                                    "path_index": path_index,
                                },
                            )
                        )
                    if not edge_ids:
                        self._skip("primary_offer_no_valid_edges")
                        continue
                    first_segments = paths[0]["segments"]
                    self.offers.append(
                        _compact(
                            {
                                "id": offer_id,
                                "source_type": source_type,
                                "provider": provider,
                                "ticketing_boundary": "provider_protected_full_route",
                                "ticketing_model": str(
                                    offer.get("ticketing_model")
                                    or _ticketing_model_for_boundary(
                                        "provider_protected_full_route"
                                    )
                                ),
                                "origin": _normalize_code(
                                    _segment_origin(first_segments[0])
                                ),
                                "destination": _normalize_code(
                                    _segment_destination(first_segments[-1])
                                ),
                                "journey_scope": str(
                                    offer.get("journey_scope") or "round_trip"
                                ),
                                "edge_ids": edge_ids,
                                "route": _route_from_paths(paths),
                                "price": _price_amount(offer),
                                "currency": _currency(offer, result),
                                "detail_status": _detail_status(
                                    offer,
                                    has_edges=bool(edge_ids),
                                ),
                                "warnings": _warnings(offer),
                                **_self_transfer_fields(offer),
                                "source_ref": {
                                    "result_index": result_index,
                                    "offer_index": offer_index,
                                    "provider_offer_id": _offer_id(offer),
                                },
                            }
                        )
                    )
                    self.coverage["provider_full_route_offer_count"] += 1
                    continue
                for path_index, path in enumerate(paths):
                    segments = path["segments"]
                    if not segments:
                        self._add_primary_summary_offer(
                            result,
                            offer,
                            provider=provider,
                            result_index=result_index,
                            offer_index=offer_index,
                        )
                        continue
                    if self._primary_path_blocked_by_direct_mode(
                        segments, direction=path.get("direction")
                    ):
                        self._skip("direct_mode_gate")
                        continue
                    offer_id = self._unique_offer_id(
                        "primary_offer",
                        provider,
                        _offer_id(offer)
                        or f"result{result_index + 1}-offer{offer_index + 1}",
                        suffix=f"path{path_index + 1}" if len(paths) > 1 else None,
                    )
                    edge_ids = self._add_route_edges(
                        offer_id=offer_id,
                        provider=provider,
                        source_type=source_type,
                        ticketing_boundary="provider_protected_full_route",
                        segments=segments,
                        direction=path.get("direction"),
                        source_debug={
                            "result_index": result_index,
                            "offer_index": offer_index,
                            **(path.get("debug") or {}),
                        },
                    )
                    if not edge_ids:
                        self._skip("primary_offer_no_valid_edges")
                        continue
                    self.offers.append(
                        _compact(
                            {
                                "id": offer_id,
                                "source_type": source_type,
                                "provider": provider,
                                "ticketing_boundary": "provider_protected_full_route",
                                "ticketing_model": _ticketing_model_for_boundary(
                                    "provider_protected_full_route"
                                ),
                                "origin": _normalize_code(_segment_origin(segments[0])),
                                "destination": _normalize_code(
                                    _segment_destination(segments[-1])
                                ),
                                "direction": path.get("direction"),
                                "edge_ids": edge_ids,
                                "route": _route_from_segments(segments),
                                "price": _price_amount(offer),
                                "currency": _currency(offer, result),
                                "detail_status": _detail_status(
                                    offer,
                                    has_edges=bool(edge_ids),
                                ),
                                "warnings": _warnings(offer),
                                **_self_transfer_fields(offer),
                                "source_ref": {
                                    "result_index": result_index,
                                    "offer_index": offer_index,
                                    "provider_offer_id": _offer_id(offer),
                                },
                            }
                        )
                    )
                    self.coverage["provider_full_route_offer_count"] += 1

    def _add_primary_summary_offer(
        self,
        result: dict[str, Any],
        offer: dict[str, Any],
        *,
        provider: str,
        result_index: int,
        offer_index: int,
    ) -> None:
        offer_id = self._unique_offer_id(
            "primary_offer",
            provider,
            _offer_id(offer) or f"result{result_index + 1}-offer{offer_index + 1}",
        )
        origin = _normalize_code(offer.get("origin") or result.get("origin"))
        destination = _normalize_code(
            offer.get("destination") or result.get("destination")
        )
        direction = _normalize_direction(
            offer.get("direction") or result.get("direction")
        )
        if self.direct_mode.get(direction):
            self._skip("direct_mode_gate")
            return
        self.offers.append(
            _compact(
                {
                    "id": offer_id,
                    "source_type": "provider_full_route",
                    "provider": provider,
                    "ticketing_boundary": "provider_protected_full_route",
                    "ticketing_model": _ticketing_model_for_boundary(
                        "provider_protected_full_route"
                    ),
                    "origin": origin,
                    "destination": destination,
                    "direction": direction,
                    "edge_ids": [],
                    "route": [origin, destination] if origin and destination else [],
                    "price": _price_amount(offer),
                    "currency": _currency(offer, result),
                    "detail_status": _detail_status(offer, has_edges=False),
                    "warnings": [
                        *_warnings(offer),
                        "summary_only_offer_details",
                    ],
                    **_self_transfer_fields(offer),
                    "source_ref": {
                        "result_index": result_index,
                        "offer_index": offer_index,
                        "provider_offer_id": _offer_id(offer),
                    },
                }
            )
        )
        self.coverage["provider_full_route_offer_count"] += 1

    def add_gateway_leg_results(self, results: dict[str, Any]) -> None:
        gateways = results.get("gateways") if isinstance(results, dict) else None
        if not isinstance(gateways, list):
            return
        self.coverage["gateway_count"] = len(gateways)
        self.coverage["searched_gateways"] = int(results.get("searched_gateways") or 0)
        self.coverage["viable_gateways"] = int(results.get("viable_gateways") or 0)
        self.coverage["failed_gateways"] = int(results.get("failed_gateways") or 0)
        self.coverage["not_searched_budget"] = int(
            results.get("not_searched_budget") or 0
        )
        for gateway_index, gateway_result in enumerate(gateways):
            if not isinstance(gateway_result, dict):
                self._skip("malformed_gateway_result")
                continue
            gateway = str(gateway_result.get("gateway") or "").upper()
            origin_leg = self._add_gateway_leg_offers(
                gateway_result.get("origin_leg"),
                gateway=gateway,
                leg_role="origin_leg",
                gateway_index=gateway_index,
            )
            destination_leg = self._add_gateway_leg_offers(
                gateway_result.get("destination_leg"),
                gateway=gateway,
                leg_role="destination_leg",
                gateway_index=gateway_index,
            )
            if not origin_leg or not destination_leg:
                continue
            origin_edge_ids = [
                edge_id for item in origin_leg for edge_id in item.get("edge_ids", [])
            ]
            destination_edge_ids = [
                edge_id
                for item in destination_leg
                for edge_id in item.get("edge_ids", [])
            ]
            self.connections.append(
                _compact(
                    {
                        "id": _stable_id(
                            "connection", gateway or str(gateway_index + 1)
                        ),
                        "source_type": "gateway_leg_pair",
                        "gateway": gateway,
                        "ticketing_boundary": "separate_ticket_candidate",
                        "candidate_status": "complete_gateway_legs_unranked",
                        "origin_leg_offer_ids": [
                            item["offer_id"] for item in origin_leg
                        ],
                        "destination_leg_offer_ids": [
                            item["offer_id"] for item in destination_leg
                        ],
                        "edge_ids": [*origin_edge_ids, *destination_edge_ids],
                    }
                )
            )
            self.coverage["assembled_separate_ticket_candidate_count"] += 1

    def to_graph(self) -> OfferGraph:
        self.coverage.update(
            {
                "offer_count": len(self.offers),
                "edge_count": len(self.edges),
                "connection_count": len(self.connections),
                "source_types": sorted(
                    {
                        str(offer.get("source_type"))
                        for offer in self.offers
                        if offer.get("source_type")
                    }
                ),
            }
        )
        return OfferGraph(
            edges=self.edges,
            offers=self.offers,
            connections=self.connections,
            coverage={
                key: value for key, value in self.coverage.items() if value != []
            },
        )

    def _add_gateway_leg_offers(
        self,
        leg_result: Any,
        *,
        gateway: str,
        leg_role: str,
        gateway_index: int,
    ) -> list[dict[str, Any]]:
        if not isinstance(leg_result, dict):
            return []
        if int(leg_result.get("offer_count") or 0) <= 0:
            return []
        offers = leg_result.get("offers")
        if not isinstance(offers, list) or not offers:
            return []
        provider = _provider(leg_result)
        collected: list[dict[str, Any]] = []
        for offer_index, offer in enumerate(offers):
            if not isinstance(offer, dict):
                self._skip("malformed_gateway_leg_offer")
                continue
            paths = _offer_segment_paths(
                offer,
                fallback_direction=_normalize_direction(leg_result.get("direction")),
            )
            if paths:
                for path_index, path in enumerate(paths):
                    segments = path["segments"]
                    if not segments:
                        continue
                    offer_id = self._unique_offer_id(
                        "gateway_leg",
                        provider,
                        gateway or f"gateway{gateway_index + 1}",
                        leg_role,
                        _offer_id(offer) or f"offer{offer_index + 1}",
                        suffix=f"path{path_index + 1}" if len(paths) > 1 else None,
                    )
                    edge_ids = self._add_route_edges(
                        offer_id=offer_id,
                        provider=provider,
                        source_type="gateway_leg",
                        ticketing_boundary="separate_ticket_leg",
                        segments=segments,
                        direction=path.get("direction"),
                        source_debug={
                            "gateway_index": gateway_index,
                            "gateway": gateway,
                            "leg_role": leg_role,
                            "provider_offer_id": _offer_id(offer),
                            **(path.get("debug") or {}),
                        },
                    )
                    if not edge_ids:
                        self._skip("gateway_leg_offer_no_valid_edges")
                        continue
                    self.offers.append(
                        _compact(
                            {
                                "id": offer_id,
                                "source_type": "gateway_leg",
                                "provider": provider,
                                "ticketing_boundary": "separate_ticket_leg",
                                "ticketing_model": _ticketing_model_for_boundary(
                                    "separate_ticket_leg"
                                ),
                                "origin": _normalize_code(_segment_origin(segments[0])),
                                "destination": _normalize_code(
                                    _segment_destination(segments[-1])
                                ),
                                "gateway": gateway,
                                "leg_role": leg_role,
                                "direction": path.get("direction"),
                                "edge_ids": edge_ids,
                                "route": _route_from_segments(segments),
                                "price": _price_amount(offer, leg_result),
                                "currency": _currency(offer, leg_result),
                                "detail_status": _detail_status(
                                    offer,
                                    has_edges=bool(edge_ids),
                                ),
                                "warnings": _warnings(offer),
                                **_self_transfer_fields(offer),
                                "source_ref": {
                                    "gateway_index": gateway_index,
                                    "leg_role": leg_role,
                                    "provider_offer_id": _offer_id(offer),
                                    "probe_id": leg_result.get("probe_id"),
                                },
                            }
                        )
                    )
                    self.coverage["gateway_leg_offer_count"] += 1
                    collected.append({"offer_id": offer_id, "edge_ids": edge_ids})
                continue
            origin = _normalize_code(
                offer.get("origin")
                or offer.get("departure_airport")
                or leg_result.get("origin")
            )
            destination = _normalize_code(
                offer.get("destination")
                or offer.get("arrival_airport")
                or leg_result.get("destination")
            )
            if not origin or not destination:
                self._skip("gateway_leg_offer_missing_airports")
                continue
            offer_id = self._unique_offer_id(
                "gateway_leg",
                provider,
                gateway or f"gateway{gateway_index + 1}",
                leg_role,
                _offer_id(offer) or f"offer{offer_index + 1}",
            )
            edge_id = self._unique_edge_id(offer_id, "0")
            self.edges.append(
                _compact(
                    {
                        "id": edge_id,
                        "offer_id": offer_id,
                        "source_type": "gateway_leg",
                        "provider": provider,
                        "ticketing_boundary": "separate_ticket_leg",
                        "ticketing_model": _ticketing_model_for_boundary(
                            "separate_ticket_leg"
                        ),
                        "origin": origin,
                        "destination": destination,
                        "gateway": gateway,
                        "leg_role": leg_role,
                        "direction": _normalize_direction(leg_result.get("direction")),
                        "sequence": 0,
                        "flight_number": _flight_number(offer, leg_result),
                        "marketing_carrier": _carrier_value(
                            offer,
                            leg_result,
                            keys=("marketing_carrier",),
                        ),
                        "operating_carrier": _carrier_value(
                            offer,
                            leg_result,
                            keys=("operating_carrier",),
                        ),
                        "carrier": _carrier_value(
                            offer,
                            leg_result,
                            keys=("carrier", "airline", "main_airline"),
                        ),
                        "carrier_name": _carrier_value(
                            offer,
                            leg_result,
                            keys=("carrier_name", "airline_name"),
                        ),
                        "departure_at": _time_value(
                            offer,
                            leg_result,
                            prefix="departure",
                        ),
                        "arrival_at": _time_value(
                            offer,
                            leg_result,
                            prefix="arrival",
                        ),
                    }
                )
            )
            self.offers.append(
                _compact(
                    {
                        "id": offer_id,
                        "source_type": "gateway_leg",
                        "provider": provider,
                        "ticketing_boundary": "separate_ticket_leg",
                        "ticketing_model": _ticketing_model_for_boundary(
                            "separate_ticket_leg"
                        ),
                        "origin": origin,
                        "destination": destination,
                        "gateway": gateway,
                        "leg_role": leg_role,
                        "direction": _normalize_direction(leg_result.get("direction")),
                        "edge_ids": [edge_id],
                        "route": [origin, destination],
                        "price": _price_amount(offer, leg_result),
                        "currency": _currency(offer, leg_result),
                        "detail_status": _detail_status(offer, has_edges=True),
                        "warnings": _warnings(offer),
                        **_self_transfer_fields(offer),
                        "source_ref": {
                            "gateway_index": gateway_index,
                            "leg_role": leg_role,
                            "provider_offer_id": _offer_id(offer),
                            "probe_id": leg_result.get("probe_id"),
                        },
                    }
                )
            )
            self.coverage["gateway_leg_offer_count"] += 1
            collected.append({"offer_id": offer_id, "edge_ids": [edge_id]})
        return collected

    def _add_route_edges(
        self,
        *,
        offer_id: str,
        provider: str,
        source_type: str,
        ticketing_boundary: str,
        segments: list[Any],
        direction: str | None,
        source_debug: dict[str, Any],
    ) -> list[str]:
        edge_ids: list[str] = []
        for index, segment in enumerate(segments):
            if not isinstance(segment, dict):
                self._skip("malformed_route_segment")
                continue
            origin = _normalize_code(_segment_origin(segment))
            destination = _normalize_code(_segment_destination(segment))
            if not origin or not destination:
                self._skip("route_segment_missing_airports")
                continue
            edge_id = self._unique_edge_id(offer_id, str(index))
            self.edges.append(
                _compact(
                    {
                        "id": edge_id,
                        "offer_id": offer_id,
                        "source_type": source_type,
                        "provider": provider,
                        "ticketing_boundary": ticketing_boundary,
                        "ticketing_model": _ticketing_model_for_boundary(
                            ticketing_boundary
                        ),
                        "origin": origin,
                        "destination": destination,
                        "gateway": source_debug.get("gateway"),
                        "leg_role": source_debug.get("leg_role"),
                        "direction": direction,
                        "sequence": index,
                        "flight_number": _flight_number(segment),
                        "marketing_carrier": _carrier_value(
                            segment,
                            keys=("marketing_carrier",),
                        ),
                        "operating_carrier": _carrier_value(
                            segment,
                            keys=("operating_carrier",),
                        ),
                        "carrier": _carrier_value(
                            segment,
                            keys=("carrier", "airline", "main_airline"),
                        ),
                        "carrier_name": _carrier_value(
                            segment,
                            keys=("carrier_name", "airline_name"),
                        ),
                        "departure_at": _time_value(segment, prefix="departure"),
                        "arrival_at": _time_value(segment, prefix="arrival"),
                        "source_debug": source_debug,
                    }
                )
            )
            edge_ids.append(edge_id)
        return edge_ids

    def _unique_offer_id(self, *parts: object, suffix: str | None = None) -> str:
        base = _stable_id(*parts, suffix=suffix)
        candidate = base
        index = 2
        while candidate in self._offer_ids:
            candidate = f"{base}:{index}"
            index += 1
        self._offer_ids.add(candidate)
        return candidate

    def _unique_edge_id(self, offer_id: str, segment_index: str) -> str:
        base = _stable_id("edge", offer_id, segment_index)
        candidate = base
        index = 2
        while candidate in self._edge_ids:
            candidate = f"{base}:{index}"
            index += 1
        self._edge_ids.add(candidate)
        return candidate

    def _skip(self, reason: str) -> None:
        self.coverage["skipped_offer_count"] += 1
        reasons = self.coverage["skipped_reasons"]
        if reason not in reasons:
            reasons.append(reason)

    def _primary_path_blocked_by_direct_mode(
        self, segments: list[Any], *, direction: str | None
    ) -> bool:
        normalized_direction = _normalize_direction(direction)
        if not self.direct_mode.get(normalized_direction):
            return False
        requested_origins, requested_destinations = _requested_scope_pair_for_direction(
            self.requested_origin_airports,
            self.requested_destination_airports,
            normalized_direction,
        )
        return not _segments_are_requested_direct_path(
            segments,
            requested_origins=requested_origins,
            requested_destinations=requested_destinations,
        )


def _provider(result: dict[str, Any]) -> str:
    return str(result.get("provider") or "unknown").strip().lower() or "unknown"


def _ticketing_model_for_boundary(ticketing_boundary: str) -> str:
    if ticketing_boundary == "provider_protected_full_route":
        return "provider_order_unverified"
    if ticketing_boundary == "separate_ticket_leg":
        return "separate_ticket_leg"
    if ticketing_boundary == "separate_ticket_candidate":
        return "separate_ticket_sum"
    return "unknown"


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
    if source_type == "assembled_separate_ticket":
        candidate_source_type = "assembled_separate_ticket"
    elif source_type == RouteFamily.DIRECT_INVENTORY:
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
        "gateway": offer.get("gateway"),
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


def _candidates_from_gateway_offer_paths(
    offers: list[dict[str, Any]],
    edges_by_id: dict[str, dict[str, Any]],
    *,
    requested_origin: str | None,
    requested_destination: str | None,
    requested_origin_airports: list[str] | None,
    requested_destination_airports: list[str] | None,
    max_path_offers: int,
) -> list[dict[str, Any]]:
    origin_codes = _requested_codes(requested_origin, requested_origin_airports)
    destination_codes = _requested_codes(
        requested_destination, requested_destination_airports
    )
    if not origin_codes or not destination_codes:
        return []
    max_offers = max(1, int(max_path_offers))
    gateway_offers = [
        offer
        for offer in offers
        if str(offer.get("source_type") or "") == "gateway_leg"
        and _normalize_code(offer.get("origin"))
        and _normalize_code(offer.get("destination"))
    ]
    by_origin: dict[str, list[dict[str, Any]]] = {}
    for offer in gateway_offers:
        by_origin.setdefault(_normalize_code(offer.get("origin")), []).append(offer)
    for bucket in by_origin.values():
        bucket.sort(key=lambda item: str(item.get("id") or ""))

    candidates: list[dict[str, Any]] = []
    queue: list[tuple[list[dict[str, Any]], set[str]]] = []
    for origin in sorted(origin_codes):
        for offer in by_origin.get(origin, []):
            offer_destination = _normalize_code(offer.get("destination"))
            if not offer_destination:
                continue
            queue.append(([offer], {origin, offer_destination}))

    while queue:
        path, visited_airports = queue.pop(0)
        last_destination = _normalize_code(path[-1].get("destination"))
        if last_destination in destination_codes and len(path) >= 2:
            candidates.append(
                _candidate_from_offer_path(
                    path,
                    edges_by_id,
                    requested_origin=requested_origin,
                    requested_destination=requested_destination,
                    requested_origin_airports=requested_origin_airports,
                    requested_destination_airports=requested_destination_airports,
                )
            )
            continue
        if len(path) >= max_offers:
            continue
        used_offer_ids = {str(offer.get("id") or "") for offer in path}
        for next_offer in by_origin.get(last_destination, []):
            next_offer_id = str(next_offer.get("id") or "")
            if next_offer_id in used_offer_ids:
                continue
            next_destination = _normalize_code(next_offer.get("destination"))
            if not next_destination:
                continue
            if (
                next_destination in visited_airports
                and next_destination not in destination_codes
            ):
                continue
            queue.append(
                (
                    [*path, next_offer],
                    {*visited_airports, next_destination},
                )
            )
    return candidates


def _candidate_from_offer_path(
    path: list[dict[str, Any]],
    edges_by_id: dict[str, dict[str, Any]],
    *,
    requested_origin: str | None,
    requested_destination: str | None,
    requested_origin_airports: list[str] | None,
    requested_destination_airports: list[str] | None,
) -> dict[str, Any]:
    edge_ids = [
        str(edge_id)
        for offer in path
        for edge_id in offer.get("edge_ids") or []
        if str(edge_id)
    ]
    offer_ids = [offer.get("id") for offer in path]
    segments = _segments_for_edge_ids(edge_ids, edges_by_id)
    price, currency, price_basis, price_warnings = _summed_leg_price(path)
    detail_status = _combined_detail_status(path)
    route = _route_from_segments(segments)
    gateways = _ordered_unique([offer.get("gateway") for offer in path])
    if not gateways and len(route) > 2:
        gateways = route[1:-1]
    warnings = [
        "separate_ticket_connection_unverified",
        *price_warnings,
        *_candidate_warnings(
            {
                "warnings": [
                    warning
                    for offer in path
                    for warning in (offer.get("warnings") or [])
                ]
            },
            detail_status=detail_status,
        ),
    ]
    return {
        "id": _stable_id("candidate", "path", *offer_ids),
        "source_type": "gateway_separate_ticket",
        "provider": None,
        "source_providers": _ordered_unique([offer.get("provider") for offer in path]),
        "gateway": gateways[0] if len(gateways) == 1 else None,
        "gateways": gateways,
        "covers_requested_trip": _covers_requested_trip(
            segments,
            {},
            journeys=None,
            requested_origin=requested_origin,
            requested_destination=requested_destination,
            requested_origin_airports=requested_origin_airports,
            requested_destination_airports=requested_destination_airports,
            detail_status=detail_status,
        ),
        "journey_scope": "one_way",
        "price": price,
        "currency": currency,
        "price_basis": price_basis,
        "ticketing_model": "separate_ticket_sum",
        "ticketing_boundaries": _ordered_unique(
            [offer.get("ticketing_boundary") for offer in path]
        ),
        "detail_status": detail_status,
        "journeys": _journeys_from_segments(
            segments,
            direction="outbound",
        ),
        "warnings": _ordered_unique(warnings),
        "offer_ids": offer_ids,
        "edge_ids": edge_ids,
        "path_offer_count": len(path),
    }


def _accept_or_reject_candidate(
    candidate: dict[str, Any],
    candidates: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    *,
    direct_only: bool,
    direct_mode: dict[str, bool],
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
    direct_mode_violation = _candidate_direct_mode_violation(candidate, direct_mode)
    if direct_mode_violation is not None:
        rejected.append(
            {
                "candidate_id": candidate.get("id"),
                "source_type": candidate.get("source_type"),
                "reason": "direct_mode_gate",
                "direction": direct_mode_violation,
            }
        )
        return
    candidates.append(candidate)


def _candidate_is_direct(candidate: dict[str, Any]) -> bool:
    journeys = (
        candidate.get("journeys") if isinstance(candidate.get("journeys"), list) else []
    )
    if not journeys:
        return False
    segment_count = 0
    for journey in journeys:
        if not isinstance(journey, dict):
            continue
        segments = (
            journey.get("segments") if isinstance(journey.get("segments"), list) else []
        )
        segment_count += len(segments)
    return (
        segment_count == 1 and candidate.get("source_type") != "gateway_separate_ticket"
    )


def _candidate_direct_mode_violation(
    candidate: dict[str, Any], direct_mode: dict[str, bool]
) -> str | None:
    active = {
        _normalize_direction(direction)
        for direction, enabled in (direct_mode or {}).items()
        if enabled
    }
    if not active:
        return None
    journeys = (
        candidate.get("journeys") if isinstance(candidate.get("journeys"), list) else []
    )
    if not journeys:
        return next(iter(active))
    for journey in journeys:
        if not isinstance(journey, dict):
            continue
        direction = _normalize_direction(journey.get("direction"))
        if direction not in active:
            continue
        segments = (
            journey.get("segments") if isinstance(journey.get("segments"), list) else []
        )
        if (
            len([segment for segment in segments if isinstance(segment, dict)]) != 1
            or candidate.get("source_type") == "gateway_separate_ticket"
        ):
            return direction
    return None


def _segments_are_requested_direct_path(
    segments: list[Any],
    *,
    requested_origins: set[str],
    requested_destinations: set[str],
) -> bool:
    rows = [segment for segment in segments if isinstance(segment, dict)]
    if len(rows) != 1:
        return False
    segment = rows[0]
    origin = _normalize_code(_segment_origin(segment))
    destination = _normalize_code(_segment_destination(segment))
    if requested_origins and origin not in requested_origins:
        return False
    if requested_destinations and destination not in requested_destinations:
        return False
    return bool(origin and destination)


def _requested_scope_pair_for_direction(
    requested_origins: set[str],
    requested_destinations: set[str],
    direction: str | None,
) -> tuple[set[str], set[str]]:
    if _normalize_direction(direction) == "return":
        return requested_destinations, requested_origins
    return requested_origins, requested_destinations


def _requested_codes(
    value: str | None, airport_scope: list[str] | None = None
) -> set[str]:
    scoped = {code for item in airport_scope or [] if (code := _normalize_code(item))}
    if scoped:
        return scoped
    code = _normalize_code(value)
    if not code:
        return set()
    return {code}


def _dedupe_candidates(
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    deduped: list[dict[str, Any]] = []
    signature_index: dict[tuple[tuple[str, ...], ...], int] = {}
    deduped_count = 0
    for candidate in candidates:
        signature = _candidate_signature(candidate)
        if signature is None:
            deduped.append(candidate)
            continue
        existing_index = signature_index.get(signature)
        if existing_index is None:
            signature_index[signature] = len(deduped)
            deduped.append(candidate)
            continue
        deduped[existing_index] = _merge_duplicate_candidates(
            deduped[existing_index],
            candidate,
        )
        deduped_count += 1
    return deduped, deduped_count


def _candidate_signature(
    candidate: dict[str, Any],
) -> tuple[tuple[str, ...], ...] | None:
    journeys = candidate.get("journeys")
    if not isinstance(journeys, list) or not journeys:
        return None
    signature: list[tuple[str, ...]] = []
    for journey in journeys:
        if not isinstance(journey, dict):
            return None
        direction = _normalize_direction(journey.get("direction")) or ""
        segments = journey.get("segments")
        if not isinstance(segments, list) or not segments:
            return None
        for segment in segments:
            if not isinstance(segment, dict):
                return None
            part = (
                direction,
                _normalize_code(segment.get("origin")),
                _normalize_code(segment.get("destination")),
                _normalize_token(segment.get("departure_at")),
                _normalize_token(segment.get("arrival_at")),
            )
            if not all(part):
                return None
            signature.append(part)
    return tuple(signature) if signature else None


def _merge_duplicate_candidates(
    existing: dict[str, Any],
    incoming: dict[str, Any],
) -> dict[str, Any]:
    if _candidate_preference(incoming) > _candidate_preference(existing):
        primary = deepcopy(incoming)
        alternate = existing
    else:
        primary = deepcopy(existing)
        alternate = incoming

    alternate_sources = [
        *[
            dict(source)
            for source in primary.get("alternate_sources") or []
            if isinstance(source, dict)
        ],
        _candidate_source_summary(alternate),
        *[
            dict(source)
            for source in alternate.get("alternate_sources") or []
            if isinstance(source, dict)
        ],
    ]
    primary["alternate_sources"] = _dedupe_source_summaries(alternate_sources)
    primary["source_providers"] = _ordered_unique(
        [
            *(primary.get("source_providers") or []),
            *(alternate.get("source_providers") or []),
        ]
    )
    primary["offer_ids"] = _ordered_unique(
        [*(primary.get("offer_ids") or []), *(alternate.get("offer_ids") or [])]
    )
    primary["edge_ids"] = _ordered_unique(
        [*(primary.get("edge_ids") or []), *(alternate.get("edge_ids") or [])]
    )
    primary["warnings"] = _ordered_unique(
        [*(primary.get("warnings") or []), *(alternate.get("warnings") or [])]
    )
    primary["covers_requested_trip"] = bool(
        primary.get("covers_requested_trip") or alternate.get("covers_requested_trip")
    )
    _attach_price_comparison(primary)
    return primary


def _candidate_preference(candidate: dict[str, Any]) -> tuple[int, int, int]:
    return (
        1 if candidate.get("source_type") == "provider_full_route" else 0,
        1 if candidate.get("price_basis") == "provider_offer_price" else 0,
        1 if candidate.get("price") is not None else 0,
    )


def _candidate_source_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "id",
        "source_type",
        "provider",
        "source_providers",
        "gateway",
        "gateways",
        "price",
        "currency",
        "price_basis",
        "ticketing_model",
        "ticketing_boundaries",
        "detail_status",
        "journey_scope",
        "covers_requested_trip",
        "offer_ids",
        "edge_ids",
        "path_offer_count",
        "warnings",
    )
    return {key: deepcopy(candidate.get(key)) for key in keys if key in candidate}


def _dedupe_source_summaries(
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for source in sources:
        key = (
            str(source.get("source_type") or ""),
            "|".join(str(item) for item in source.get("offer_ids") or []),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped


def _attach_price_comparison(candidate: dict[str, Any]) -> None:
    provider_price = _candidate_price_for_basis(candidate, "provider_offer_price")
    summed_price = _candidate_price_for_basis(candidate, "summed_live_leg_prices")
    if provider_price is None or summed_price is None:
        candidate.pop("price_comparison", None)
        return
    provider_amount, provider_currency = provider_price
    summed_amount, summed_currency = summed_price
    if provider_currency != summed_currency or provider_amount == summed_amount:
        candidate.pop("price_comparison", None)
        return
    candidate["price_comparison"] = {
        "provider_offer_price": {
            "amount": provider_amount,
            "currency": provider_currency,
        },
        "summed_live_leg_prices": {
            "amount": summed_amount,
            "currency": summed_currency,
        },
        "difference": summed_amount - provider_amount,
        "currency": provider_currency,
    }


def _candidate_price_for_basis(
    candidate: dict[str, Any],
    basis: str,
) -> tuple[int | float, str] | None:
    sources = [
        candidate,
        *[
            source
            for source in candidate.get("alternate_sources") or []
            if isinstance(source, dict)
        ],
    ]
    for source in sources:
        if source.get("price_basis") != basis:
            continue
        amount = _price_amount(source)
        currency = _currency(source)
        if amount is not None and currency:
            return amount, currency
    return None


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
                    "gateway": edge.get("gateway"),
                    "leg_role": edge.get("leg_role"),
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


def _combined_detail_status(offers: list[dict[str, Any]]) -> str:
    statuses = [_candidate_detail_status(offer, []) for offer in offers]
    if any(status == "missing" for status in statuses):
        return "missing"
    if any(status == "summary_only" for status in statuses):
        return "summary_only"
    return "full"


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


def _summed_leg_price(
    offers: list[dict[str, Any]],
) -> tuple[int | float | None, str | None, str, list[str]]:
    amounts = [_price_amount(offer) for offer in offers]
    currencies = [_currency(offer) for offer in offers]
    warnings: list[str] = []
    if any(amount is None for amount in amounts):
        warnings.append("leg_price_missing")
        return None, None, "unknown", warnings
    normalized_currencies = [currency for currency in currencies if currency]
    if len(set(normalized_currencies)) != 1 or len(normalized_currencies) != len(
        offers
    ):
        warnings.append("leg_currency_mismatch")
        return None, None, "unknown", warnings
    return (
        sum(amount for amount in amounts if amount is not None),
        normalized_currencies[0],
        "summed_live_leg_prices",
        warnings,
    )


def _price_amount(*sources: dict[str, Any]) -> int | float | None:
    for source in sources:
        if not isinstance(source, dict):
            continue
        price = source.get("price")
        if isinstance(price, dict):
            amount = numeric_or_none(
                price.get("amount") or price.get("value") or price.get("total")
            )
            if amount is not None:
                return amount
        amount = numeric_or_none(price)
        if amount is not None:
            return amount
        amount = numeric_or_none(
            source.get("amount") or source.get("total_price") or source.get("value")
        )
        if amount is not None:
            return amount
    return None


def _currency(*sources: dict[str, Any]) -> str | None:
    for source in sources:
        if not isinstance(source, dict):
            continue
        price = source.get("price")
        if isinstance(price, dict):
            currency = str(price.get("currency") or "").strip().upper()
            if currency:
                return currency
        currency = str(source.get("currency") or "").strip().upper()
        if currency:
            return currency
    return None


def _detail_status(offer: dict[str, Any], *, has_edges: bool) -> str:
    explicit = str(offer.get("detail_status") or "").strip().lower()
    if explicit in {"full", "summary_only", "missing"}:
        return explicit
    return "full" if has_edges else "summary_only"


def _warnings(offer: dict[str, Any]) -> list[str]:
    warnings = offer.get("warnings")
    if isinstance(warnings, list):
        return [str(item) for item in warnings if item]
    return []


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


def _flight_number(*sources: dict[str, Any]) -> str | None:
    for source in sources:
        if not isinstance(source, dict):
            continue
        value = (
            source.get("flight_number")
            or source.get("flight_no")
            or source.get("flight")
            or source.get("number")
        )
        normalized = _normalize_flight_number(value)
        if normalized:
            return normalized
    return None


def _carrier_value(*sources: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            value = str(source.get(key) or "").strip()
            if value:
                return value.upper()
    return None


def _time_value(*sources: dict[str, Any], prefix: str) -> str | None:
    keys = (
        f"{prefix}_at",
        f"{prefix}_time",
        f"{prefix}_datetime",
        prefix,
    )
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            normalized = _normalize_token(source.get(key))
            if normalized:
                return normalized
    return None


def _normalize_flight_number(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "")


def _normalize_token(value: Any) -> str:
    return str(value or "").strip()


def _ordered_unique(items: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _provider_result_offers(result: dict[str, Any]) -> list[Any] | None:
    for key in ("offers", "top_offers"):
        offers = result.get(key)
        if isinstance(offers, list):
            return offers
    return None


def _offer_segment_paths(
    offer: dict[str, Any], *, fallback_direction: str | None
) -> list[dict[str, Any]]:
    journeys = offer.get("journeys")
    paths: list[dict[str, Any]] = []
    if isinstance(journeys, list):
        for journey_index, journey in enumerate(journeys):
            if not isinstance(journey, dict):
                continue
            journey_segments = _segment_dicts(journey.get("segments"))
            if not journey_segments:
                continue
            paths.append(
                {
                    "segments": journey_segments,
                    "direction": _normalize_direction(journey.get("direction"))
                    or fallback_direction,
                    "debug": {
                        "source_path": "journeys",
                        "journey_index": journey_index,
                    },
                }
            )
    if paths:
        return paths
    segments = _segment_dicts(offer.get("segments"))
    if segments:
        return [
            {
                "segments": segments,
                "direction": _normalize_direction(offer.get("direction"))
                or fallback_direction,
                "debug": {"source_path": "segments"},
            }
        ]
    return []


def _segment_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [segment for segment in value if isinstance(segment, dict)]


def _is_atomic_round_trip_offer(
    offer: dict[str, Any], paths: list[dict[str, Any]]
) -> bool:
    if len(paths) < 2:
        return False
    directions = {
        _normalize_direction(path.get("direction"))
        for path in paths
        if _normalize_direction(path.get("direction"))
    }
    if {"outbound", "return"}.issubset(directions):
        return True
    return str(offer.get("journey_scope") or "").strip().lower() == "round_trip"


def _offer_id(offer: dict[str, Any]) -> str | None:
    value = str(offer.get("id") or offer.get("offer_id") or "").strip()
    return value or None


def _segment_origin(segment: dict[str, Any]) -> Any:
    return (
        segment.get("origin")
        or segment.get("departure")
        or segment.get("from")
        or segment.get("departure_airport")
    )


def _segment_destination(segment: dict[str, Any]) -> Any:
    return (
        segment.get("destination")
        or segment.get("arrival")
        or segment.get("to")
        or segment.get("arrival_airport")
    )


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


def _route_from_paths(paths: list[dict[str, Any]]) -> list[str]:
    route: list[str] = []
    for path in paths:
        for code in _route_from_segments(path.get("segments") or []):
            if code and (not route or route[-1] != code):
                route.append(code)
    return route


def _normalize_code(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_direction(value: Any) -> str | None:
    direction = str(value or "").strip().lower()
    return direction or None


def _stable_id(*parts: object, suffix: str | None = None) -> str:
    tokens = [
        str(part).strip().replace(" ", "_") for part in parts if str(part).strip()
    ]
    if suffix:
        tokens.append(str(suffix).strip().replace(" ", "_"))
    return ":".join(tokens)


def _compact(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


__all__ = [
    "OFFER_CANDIDATE_ENVELOPE_SCHEMA_VERSION",
    "OFFER_GRAPH_SCHEMA_VERSION",
    "OfferGraph",
    "OfferGraphBuilder",
    "build_offer_graph",
    "materialize_offer_graph_candidates",
]
