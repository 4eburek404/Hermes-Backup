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
) -> dict[str, Any]:
    builder = OfferGraphBuilder()
    builder.add_primary_offer_results(primary_offer_results or [])
    return builder.to_graph().to_dict()


class OfferGraphBuilder:
    def __init__(self) -> None:
        self.edges: list[dict[str, Any]] = []
        self.offers: list[dict[str, Any]] = []
        self._offer_ids: set[str] = set()
        self._edge_ids: set[str] = set()
        self.coverage: dict[str, Any] = {
            "primary_offer_result_count": 0,
            "provider_full_route_offer_count": 0,
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

    def to_graph(self) -> OfferGraph:
        self.coverage.update(
            {
                "offer_count": len(self.offers),
                "edge_count": len(self.edges),
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
            coverage={
                key: value for key, value in self.coverage.items() if value != []
            },
        )

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
