from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, MutableMapping

from .gateway_priors import normalize_market_key
from .offer_paths import (
    normalize_direction as _normalize_direction,
    offer_segment_paths,
    provider_result_offers as _provider_result_offers,
    segment_destination as _segment_destination,
    segment_origin as _segment_origin,
)

IATA_CODE_RE = re.compile(r"^[A-Z]{3}$")
PROVIDER_RETURNED_ROUTE_WEIGHT = 200
PROVIDER_RETURNED_ROUTE_SOURCE = "provider_returned_route"
STATIC_PRIOR_SOURCE = "static_prior"
MOSCOW_CONTROL_AIRPORT_CODES = {"MOW", "SVO", "DME", "VKO", "ZIA"}
MOSCOW_CONTROL_LAYER = "moscow_svo_control"


@dataclass(frozen=True, slots=True)
class GatewaySignal:
    source: str
    weight: int | float
    reason: str
    code: str | None = None
    provider: str | None = None
    offer_id: str | None = None
    direction: str | None = None
    debug: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source": self.source,
            "weight": self.weight,
            "reason": self.reason,
        }
        if self.code:
            payload["code"] = self.code
        if self.provider:
            payload["provider"] = self.provider
        if self.offer_id:
            payload["offer_id"] = self.offer_id
        if self.direction:
            payload["direction"] = self.direction
        if self.debug:
            payload["debug"] = dict(self.debug)
        return payload


class _DiscoveredGateway(dict[str, Any]):
    """Ephemeral discovery ordering record; it is never a route model."""

    @property
    def code(self) -> str:
        return str(self["code"])

    @property
    def score(self) -> int | float:
        return self["score"]

    @property
    def signals(self) -> tuple[GatewaySignal, ...]:
        return tuple(self["signals"])

    @property
    def debug(self) -> dict[str, Any]:
        return dict(self["debug"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "score": self.score,
            "signals": [signal.to_dict() for signal in self.signals],
            "risk_flags": list(self["risk_flags"]),
            "debug": self.debug,
        }


class GatewayDiscoveryService:
    def __init__(self, store: Any):
        self.store = store

    def discover(
        self,
        market_key: str,
        *,
        primary_offer_results: list[dict[str, Any]] | None = None,
        provider_results: list[dict[str, Any]] | None = None,
        diagnostics: MutableMapping[str, Any] | None = None,
    ) -> list[_DiscoveredGateway]:
        market = normalize_market_key(market_key)
        state = _DiscoveryState(market=market)
        rejected: list[dict[str, Any]] = []

        for prior in self.store.gateway_priors_for_market(market):
            code = _normalize_gateway_code(prior.get("code"))
            if not code:
                continue
            if _static_prior_is_control_layer(prior, code):
                rejected.append(_static_prior_rejection(prior, code, market))
                continue
            state.add_signal(
                code,
                GatewaySignal(
                    source=STATIC_PRIOR_SOURCE,
                    weight=prior.get("prior_weight", 0),
                    reason=str(prior.get("reason") or "gateway prior"),
                    code=code,
                    debug=_static_prior_debug(prior),
                ),
            )

        extracted, rejected_provider_signals = (
            extract_provider_returned_gateway_signals(
                [
                    *(primary_offer_results or []),
                    *(provider_results or []),
                ]
            )
        )
        rejected.extend(rejected_provider_signals)
        for code, signal in extracted:
            state.add_signal(code, signal)

        candidates = state.ranked_signals()
        if diagnostics is not None:
            diagnostics["market"] = market
            diagnostics["candidate_count"] = len(candidates)
            diagnostics["candidates"] = [
                candidate.to_dict() for candidate in candidates
            ]
            diagnostics["rejected_gateway_signals"] = rejected
            diagnostics["skipped_reasons"] = []
            diagnostics["empty_reason"] = None
            if not candidates:
                diagnostics["empty_reason"] = "no_gateway_candidates_discovered"
                diagnostics["skipped_reasons"] = [
                    diagnostics["empty_reason"],
                ]
        return candidates


def extract_provider_returned_gateway_signals(
    provider_results: list[dict[str, Any]] | None,
) -> tuple[list[tuple[str, GatewaySignal]], list[dict[str, Any]]]:
    extracted: list[tuple[str, GatewaySignal]] = []
    rejected: list[dict[str, Any]] = []
    for result in provider_results or []:
        if isinstance(result, dict):
            _collect_provider_returned_gateways(result, extracted, rejected)
    return extracted, rejected


class _DiscoveryState:
    def __init__(self, *, market: str):
        self.market = market
        self._records: dict[str, dict[str, Any]] = {}
        self._sequence = 0

    def add_signal(
        self,
        code: str,
        signal: GatewaySignal,
        *,
        risk_flags: tuple[str, ...] = (),
    ) -> None:
        record = self._records.get(code)
        if record is None:
            record = {
                "code": code,
                "signals": [],
                "risk_flags": set(),
                "first_seen": self._sequence,
            }
            self._records[code] = record
        record["signals"].append(signal)
        record["risk_flags"].update(risk_flags)
        self._sequence += 1

    def ranked_signals(self) -> list[_DiscoveredGateway]:
        signals = [
            _DiscoveredGateway(
                code=str(record["code"]),
                score=sum(signal.weight for signal in record["signals"]),
                signals=tuple(record["signals"]),
                risk_flags=tuple(sorted(record["risk_flags"])),
                debug={"market": self.market},
            )
            for record in self._records.values()
        ]
        return sorted(signals, key=self._signal_sort_key)

    def _signal_sort_key(
        self, gateway: _DiscoveredGateway
    ) -> tuple[int, int | float, int, str]:
        record = self._records[gateway.code]
        has_provider_signal = any(
            item.source == PROVIDER_RETURNED_ROUTE_SOURCE
            for item in gateway.signals
        )
        provider_rank = 0 if has_provider_signal else 1
        return (
            provider_rank,
            -gateway.score,
            int(record["first_seen"]),
            gateway.code,
        )


def _collect_provider_returned_gateways(
    result: dict[str, Any],
    extracted: list[tuple[str, GatewaySignal]],
    rejected: list[dict[str, Any]],
) -> None:
    provider = str(result.get("provider") or "").strip().lower() or None
    result_direction = _normalize_direction(result.get("direction"))

    offers = _provider_result_offers(result)
    if not isinstance(offers, list):
        return

    for offer in offers:
        if not isinstance(offer, dict):
            continue
        offer_id = str(offer.get("id") or offer.get("offer_id") or "").strip() or None
        offer_direction = (
            _normalize_direction(offer.get("direction")) or result_direction
        )
        segment_paths, skipped = _offer_segment_paths(
            offer,
            provider=provider,
            offer_id=offer_id,
            fallback_direction=offer_direction,
        )
        rejected.extend(skipped)
        for path in segment_paths:
            if len(path["segments"]) < 2:
                continue
            _collect_gateways_from_segments(
                path["segments"],
                extracted,
                rejected,
                provider=provider,
                offer_id=offer_id,
                direction=path["direction"],
                path_debug=path["debug"],
            )


def _offer_segment_paths(
    offer: dict[str, Any],
    *,
    provider: str | None,
    offer_id: str | None,
    fallback_direction: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    journeys = offer.get("journeys")
    rejected: list[dict[str, Any]] = []
    if isinstance(journeys, list):
        for journey_index, journey in enumerate(journeys):
            if not isinstance(journey, dict):
                rejected.append(
                    _rejection(
                        provider=provider,
                        offer_id=offer_id,
                        reason="malformed_segments",
                        debug={
                            "source_path": "journeys",
                            "journey_index": journey_index,
                        },
                    )
                )
                continue
            if not isinstance(journey.get("segments"), list):
                rejected.append(
                    _rejection(
                        provider=provider,
                        offer_id=offer_id,
                        reason="missing_segments",
                        debug={
                            "source_path": "journeys",
                            "journey_index": journey_index,
                        },
                    )
                )
                continue
            for segment_index, segment in enumerate(journey["segments"]):
                if not isinstance(segment, dict):
                    rejected.append(
                        _rejection(
                            provider=provider,
                            offer_id=offer_id,
                            reason="malformed_segments",
                            segment_index=segment_index,
                            debug={
                                "source_path": "journeys",
                                "journey_index": journey_index,
                            },
                        )
                    )
    raw_segments = offer.get("segments")
    if isinstance(raw_segments, list):
        for segment_index, segment in enumerate(raw_segments):
            if not isinstance(segment, dict):
                rejected.append(
                    _rejection(
                        provider=provider,
                        offer_id=offer_id,
                        reason="malformed_segments",
                        segment_index=segment_index,
                        debug={"source_path": "segments"},
                    )
                )
    paths = offer_segment_paths(offer, fallback_direction=fallback_direction)
    if paths:
        return paths, rejected
    rejected.append(
        _rejection(
            provider=provider,
            offer_id=offer_id,
            reason="missing_segments",
        )
    )
    return [], rejected


def _collect_gateways_from_segments(
    segments: list[Any],
    extracted: list[tuple[str, GatewaySignal]],
    rejected: list[dict[str, Any]],
    *,
    provider: str | None,
    offer_id: str | None,
    direction: str | None,
    path_debug: dict[str, Any],
) -> None:
    for index in range(len(segments) - 1):
        current = segments[index]
        following = segments[index + 1]
        if not isinstance(current, dict) or not isinstance(following, dict):
            rejected.append(
                _rejection(
                    provider=provider,
                    offer_id=offer_id,
                    reason="malformed_segments",
                    segment_index=index,
                    debug=path_debug,
                )
            )
            continue
        arrival = _normalize_gateway_code(_segment_destination(current))
        next_departure = _normalize_gateway_code(_segment_origin(following))
        if not arrival or not next_departure:
            rejected.append(
                _rejection(
                    provider=provider,
                    offer_id=offer_id,
                    reason="malformed_segments",
                    segment_index=index,
                    debug=path_debug,
                )
            )
            continue
        if arrival != next_departure:
            rejected.append(
                _rejection(
                    provider=provider,
                    offer_id=offer_id,
                    reason="airport_mismatch",
                    segment_index=index,
                    arrival_airport=arrival,
                    next_departure_airport=next_departure,
                    debug={**path_debug, "ground_transfer_required": True},
                )
            )
            continue
        extracted.append(
            (
                arrival,
                GatewaySignal(
                    source=PROVIDER_RETURNED_ROUTE_SOURCE,
                    weight=PROVIDER_RETURNED_ROUTE_WEIGHT,
                    reason="provider returned route via intermediate airport",
                    code=arrival,
                    provider=provider,
                    offer_id=offer_id,
                    direction=direction,
                    debug={
                        **path_debug,
                        "segment_index": index,
                        "between_segments": [index, index + 1],
                    },
                ),
            )
        )


def _rejection(
    *,
    provider: str | None,
    offer_id: str | None,
    reason: str,
    segment_index: int | None = None,
    arrival_airport: str | None = None,
    next_departure_airport: str | None = None,
    debug: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source": PROVIDER_RETURNED_ROUTE_SOURCE,
        "reason": reason,
    }
    if provider:
        payload["provider"] = provider
    if offer_id:
        payload["offer_id"] = offer_id
    if segment_index is not None:
        payload["segment_index"] = segment_index
    if arrival_airport:
        payload["arrival_airport"] = arrival_airport
    if next_departure_airport:
        payload["next_departure_airport"] = next_departure_airport
    if debug:
        payload["debug"] = dict(debug)
    return payload


def _static_prior_is_control_layer(prior: dict[str, Any], code: str) -> bool:
    if bool(prior.get("allow_as_gateway")):
        return False
    return bool(prior.get("control_layer")) or code in MOSCOW_CONTROL_AIRPORT_CODES


def _static_prior_rejection(
    prior: dict[str, Any], code: str, market: str
) -> dict[str, Any]:
    control_layer = str(prior.get("control_layer") or MOSCOW_CONTROL_LAYER)
    return {
        "source": STATIC_PRIOR_SOURCE,
        "code": code,
        "reason": "control_layer_prior_not_gateway_candidate",
        "control_layer": control_layer,
        "market": market,
        "debug": {
            "static_prior_not_ranked": True,
            "allow_as_gateway_required": True,
        },
    }


def _static_prior_debug(prior: dict[str, Any]) -> dict[str, Any]:
    debug: dict[str, Any] = {}
    if prior.get("allow_as_gateway") is True:
        debug["allow_as_gateway"] = True
    return debug


def _normalize_gateway_code(value: Any) -> str | None:
    code = str(value or "").strip().upper()
    return code if IATA_CODE_RE.match(code) else None


__all__ = [
    "GatewayDiscoveryService",
    "GatewaySignal",
    "PROVIDER_RETURNED_ROUTE_SOURCE",
    "PROVIDER_RETURNED_ROUTE_WEIGHT",
    "STATIC_PRIOR_SOURCE",
    "extract_provider_returned_gateway_signals",
]
