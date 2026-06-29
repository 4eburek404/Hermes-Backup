from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, MutableMapping

from .gateway_priors import normalize_market_key

IATA_CODE_RE = re.compile(r"^[A-Z]{3}$")
PROVIDER_RETURNED_ROUTE_WEIGHT = 100
PROVIDER_RETURNED_ROUTE_SOURCE = "provider_returned_route"
STATIC_PRIOR_SOURCE = "static_prior"


@dataclass(frozen=True, slots=True)
class GatewaySignal:
    source: str
    weight: int | float
    reason: str
    provider: str | None = None
    offer_id: str | None = None
    debug: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source": self.source,
            "weight": self.weight,
            "reason": self.reason,
        }
        if self.provider:
            payload["provider"] = self.provider
        if self.offer_id:
            payload["offer_id"] = self.offer_id
        if self.debug:
            payload["debug"] = dict(self.debug)
        return payload


@dataclass(frozen=True, slots=True)
class GatewayCandidate:
    code: str
    score: int | float
    signals: tuple[GatewaySignal, ...]
    risk_flags: tuple[str, ...] = ()
    debug: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "score": self.score,
            "signals": [signal.to_dict() for signal in self.signals],
            "risk_flags": list(self.risk_flags),
        }
        if self.debug:
            payload["debug"] = dict(self.debug)
        return payload


class GatewayDiscoveryService:
    def __init__(self, store: Any):
        self.store = store

    def discover(
        self,
        market_key: str,
        *,
        primary_offer_results: list[dict[str, Any]] | None = None,
        diagnostics: MutableMapping[str, Any] | None = None,
    ) -> list[GatewayCandidate]:
        market = normalize_market_key(market_key)
        state = _DiscoveryState(market=market)
        rejected: list[dict[str, Any]] = []

        for prior in self.store.gateway_priors_for_market(market):
            code = _normalize_gateway_code(prior.get("code"))
            if not code:
                continue
            state.add_signal(
                code,
                GatewaySignal(
                    source=STATIC_PRIOR_SOURCE,
                    weight=prior.get("prior_weight", 0),
                    reason=str(prior.get("reason") or "gateway prior"),
                ),
            )

        for result in primary_offer_results or []:
            _collect_provider_returned_gateways(result, state, rejected)

        candidates = state.candidates()
        if diagnostics is not None:
            diagnostics["market"] = market
            diagnostics["candidate_count"] = len(candidates)
            diagnostics["candidates"] = [candidate.to_dict() for candidate in candidates]
            diagnostics["rejected_gateway_signals"] = rejected
        return candidates


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

    def candidates(self) -> list[GatewayCandidate]:
        candidates = [
            GatewayCandidate(
                code=str(record["code"]),
                score=sum(signal.weight for signal in record["signals"]),
                signals=tuple(record["signals"]),
                risk_flags=tuple(sorted(record["risk_flags"])),
                debug={"market": self.market},
            )
            for record in self._records.values()
        ]
        return sorted(candidates, key=self._candidate_sort_key)

    def _candidate_sort_key(
        self, candidate: GatewayCandidate
    ) -> tuple[int, int | float, int, str]:
        record = self._records[candidate.code]
        has_provider_signal = any(
            signal.source == PROVIDER_RETURNED_ROUTE_SOURCE
            for signal in candidate.signals
        )
        provider_rank = 0 if has_provider_signal else 1
        return (provider_rank, -candidate.score, int(record["first_seen"]), candidate.code)


def _collect_provider_returned_gateways(
    result: dict[str, Any],
    state: _DiscoveryState,
    rejected: list[dict[str, Any]],
) -> None:
    provider = str(result.get("provider") or "").strip().lower()
    if provider != "kupibilet":
        return
    role = str(result.get("role") or "").strip()
    if role and role != "primary_offer_collection":
        return
    source_type = str(result.get("source_type") or "").strip()
    if source_type and source_type != "provider_full_route":
        return

    offers = result.get("top_offers")
    if not isinstance(offers, list):
        offers = result.get("normalized_offers")
    if not isinstance(offers, list):
        return

    for offer in offers:
        if not isinstance(offer, dict):
            continue
        offer_id = str(offer.get("id") or offer.get("offer_id") or "").strip() or None
        segments = offer.get("segments")
        if not isinstance(segments, list):
            rejected.append(
                {
                    "source": PROVIDER_RETURNED_ROUTE_SOURCE,
                    "provider": provider,
                    "offer_id": offer_id,
                    "reason": "missing_segment_detail",
                }
            )
            continue
        if len(segments) < 2:
            continue
        _collect_gateways_from_segments(
            segments,
            state,
            rejected,
            provider=provider,
            offer_id=offer_id,
        )


def _collect_gateways_from_segments(
    segments: list[Any],
    state: _DiscoveryState,
    rejected: list[dict[str, Any]],
    *,
    provider: str,
    offer_id: str | None,
) -> None:
    for index in range(len(segments) - 1):
        current = segments[index]
        following = segments[index + 1]
        if not isinstance(current, dict) or not isinstance(following, dict):
            rejected.append(
                {
                    "source": PROVIDER_RETURNED_ROUTE_SOURCE,
                    "provider": provider,
                    "offer_id": offer_id,
                    "segment_index": index,
                    "reason": "missing_segment_detail",
                }
            )
            continue
        arrival = _normalize_gateway_code(_segment_destination(current))
        next_departure = _normalize_gateway_code(_segment_origin(following))
        if not arrival or not next_departure:
            rejected.append(
                {
                    "source": PROVIDER_RETURNED_ROUTE_SOURCE,
                    "provider": provider,
                    "offer_id": offer_id,
                    "segment_index": index,
                    "reason": "missing_segment_detail",
                }
            )
            continue
        if arrival != next_departure:
            rejected.append(
                {
                    "source": PROVIDER_RETURNED_ROUTE_SOURCE,
                    "provider": provider,
                    "offer_id": offer_id,
                    "segment_index": index,
                    "reason": "airport_mismatch_between_segments",
                    "arrival_airport": arrival,
                    "next_departure_airport": next_departure,
                    "debug": {"ground_transfer_required": True},
                }
            )
            continue
        state.add_signal(
            arrival,
            GatewaySignal(
                source=PROVIDER_RETURNED_ROUTE_SOURCE,
                weight=PROVIDER_RETURNED_ROUTE_WEIGHT,
                reason="provider full-route offer contains intermediate airport",
                provider=provider,
                offer_id=offer_id,
                debug={"segment_index": index},
            ),
        )


def _segment_origin(segment: dict[str, Any]) -> Any:
    return segment.get("origin") or segment.get("departure") or segment.get("from")


def _segment_destination(segment: dict[str, Any]) -> Any:
    return segment.get("destination") or segment.get("arrival") or segment.get("to")


def _normalize_gateway_code(value: Any) -> str | None:
    code = str(value or "").strip().upper()
    return code if IATA_CODE_RE.match(code) else None


__all__ = [
    "GatewayCandidate",
    "GatewayDiscoveryService",
    "GatewaySignal",
    "PROVIDER_RETURNED_ROUTE_SOURCE",
    "PROVIDER_RETURNED_ROUTE_WEIGHT",
    "STATIC_PRIOR_SOURCE",
]
