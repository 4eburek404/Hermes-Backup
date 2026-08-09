from __future__ import annotations

from typing import Any

from ..domain.normalize import (
    compact_mapping as _compact,
    currency_value as _currency,
    normalize_code as _normalize_code,
    normalize_token as _normalize_token,
    price_amount as _price_amount,
    stable_id as _stable_id,
)
from ..domain.offer_paths import (
    normalize_direction as _normalize_direction,
    offer_segment_paths as _offer_segment_paths,
    provider_result_offers as _provider_result_offers,
    segment_destination as _segment_destination,
    segment_origin as _segment_origin,
)
from .offer_graph_model import OfferGraph


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
        normalized = _normalize_token(value).upper().replace(" ", "")
        if normalized:
            return normalized
    return None


def _carrier_value(*sources: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            value = _normalize_token(source.get(key))
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


def build_offer_graph(
    *,
    primary_offer_results: list[dict[str, Any]] | None = None,
    gateway_leg_results: dict[str, Any] | None = None,
) -> dict[str, Any]:
    builder = OfferGraphBuilder()
    builder.add_primary_offer_results(primary_offer_results or [])
    builder.add_gateway_leg_results(gateway_leg_results or {})
    return builder.to_graph().to_dict()


class OfferGraphBuilder:
    def __init__(self) -> None:
        self.edges: list[dict[str, Any]] = []
        self.offers: list[dict[str, Any]] = []
        self.connections: list[dict[str, Any]] = []
        self._offer_ids: set[str] = set()
        self._edge_ids: set[str] = set()
        self.coverage: dict[str, Any] = {
            "primary_offer_result_count": 0,
            "gateway_count": 0,
            "provider_full_route_offer_count": 0,
            "gateway_leg_offer_count": 0,
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
                result_direction = _normalize_direction(result.get("direction"))
                paths = _offer_segment_paths(
                    offer,
                    fallback_direction=result_direction,
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
                is_atomic_round_trip = _is_atomic_round_trip_offer(offer, paths)
                if result_direction and not is_atomic_round_trip:
                    for path in paths:
                        path["direction"] = result_direction
                if is_atomic_round_trip:
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
            result.get("direction") or offer.get("direction")
        )
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
        if not isinstance(results, dict):
            return
        self._add_route_hypothesis_results(results.get("route_hypotheses"))
        gateways = results.get("gateways") if isinstance(results, dict) else None
        if not isinstance(gateways, list):
            return
        self.coverage["gateway_count"] = len(gateways)
        self.coverage["searched_gateways"] = int(results.get("searched_gateways") or 0)
        self.coverage["viable_gateways"] = int(results.get("viable_gateways") or 0)
        self.coverage["not_searched_budget"] = int(
            results.get("not_searched_budget") or 0
        )
        for gateway_index, gateway_result in enumerate(gateways):
            if not isinstance(gateway_result, dict):
                self._skip("malformed_gateway_result")
                continue
            gateway = str(gateway_result.get("gateway") or "").upper()
            origin_leg_result = gateway_result.get("origin_leg")
            destination_leg_result = gateway_result.get("destination_leg")
            direction = (
                _normalize_direction(gateway_result.get("direction"))
                or _normalize_direction(
                    origin_leg_result.get("direction")
                    if isinstance(origin_leg_result, dict)
                    else None
                )
                or _normalize_direction(
                    destination_leg_result.get("direction")
                    if isinstance(destination_leg_result, dict)
                    else None
                )
                or "outbound"
            )
            origin_leg = self._add_gateway_leg_offers(
                origin_leg_result,
                gateway=gateway,
                leg_role="origin_leg",
                gateway_index=gateway_index,
                direction=direction,
            )
            destination_leg = self._add_gateway_leg_offers(
                destination_leg_result,
                gateway=gateway,
                leg_role="destination_leg",
                gateway_index=gateway_index,
                direction=direction,
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
                            "connection",
                            direction,
                            gateway or str(gateway_index + 1),
                        ),
                        "source_type": "gateway_leg_pair",
                        "gateway": gateway,
                        "direction": direction,
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

    def _add_route_hypothesis_results(self, hypotheses: Any) -> None:
        if not isinstance(hypotheses, list):
            return
        self.coverage["route_hypothesis_count"] = len(hypotheses)
        for hypothesis_index, hypothesis in enumerate(hypotheses):
            if not isinstance(hypothesis, dict):
                self._skip("malformed_route_hypothesis")
                continue
            hypothesis_id = str(hypothesis.get("hypothesis_id") or "").strip()
            required_airports = [
                code
                for code in (
                    _normalize_code(value)
                    for value in hypothesis.get("required_airports") or []
                )
                if code
            ]
            direction = _normalize_direction(hypothesis.get("direction")) or "outbound"
            legs = hypothesis.get("legs")
            if (
                not hypothesis_id
                or len(required_airports) < 3
                or not isinstance(legs, list)
            ):
                self._skip("route_hypothesis_missing_identity")
                continue
            for leg in legs:
                if not isinstance(leg, dict):
                    self._skip("malformed_route_hypothesis_leg")
                    continue
                try:
                    leg_index = int(leg.get("leg_index"))
                except (TypeError, ValueError):
                    self._skip("route_hypothesis_leg_missing_index")
                    continue
                if leg_index < 0 or leg_index >= len(required_airports) - 1:
                    self._skip("route_hypothesis_leg_index_out_of_range")
                    continue
                attempts = leg.get("attempts")
                if not isinstance(attempts, list):
                    continue
                for attempt in attempts:
                    if not isinstance(attempt, dict):
                        self._skip("malformed_route_hypothesis_attempt")
                        continue
                    offers = attempt.get("offers")
                    if not isinstance(offers, list) or not offers:
                        continue
                    leg_result = {
                        **attempt,
                        "origin": required_airports[leg_index],
                        "destination": required_airports[leg_index + 1],
                        "direction": direction,
                        "offer_count": len(offers),
                    }
                    added = self._add_gateway_leg_offers(
                        leg_result,
                        gateway=required_airports[leg_index + 1],
                        leg_role=f"route_leg_{leg_index}",
                        gateway_index=hypothesis_index,
                        direction=direction,
                    )
                    for item in added:
                        self._annotate_route_hypothesis_offer(
                            str(item["offer_id"]),
                            hypothesis_id=hypothesis_id,
                            leg_index=leg_index,
                            required_airports=required_airports,
                            leg_policy=leg.get("policy"),
                        )

    def _annotate_route_hypothesis_offer(
        self,
        offer_id: str,
        *,
        hypothesis_id: str,
        leg_index: int,
        required_airports: list[str],
        leg_policy: Any,
    ) -> None:
        for offer in reversed(self.offers):
            if offer.get("id") == offer_id:
                offer.update(
                    _compact(
                        {
                            "hypothesis_id": hypothesis_id,
                            "leg_index": leg_index,
                            "required_airports": list(required_airports),
                            "leg_policy": str(leg_policy or ""),
                        }
                    )
                )
                return

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
        direction: str,
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
                    path["direction"] = direction
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
                        "direction": direction,
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
                        "direction": direction,
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


__all__ = ["OfferGraphBuilder", "build_offer_graph"]
