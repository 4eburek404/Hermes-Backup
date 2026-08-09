from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from ..pipeline.search_plan import RouteLegTemplate
from ..store import Store
from .probe_dispatcher import (
    SegmentProbeOptions,
    SegmentProbeOutcome,
    dispatch_segment_probe,
)
from .probe_ledger import ProbeRunLedger


def reachable_local_dates(arrival_at: str, max_layover_min: int) -> list[str]:
    """Return departure calendar dates reachable within the arrival timezone."""

    arrival = datetime.fromisoformat(arrival_at)
    if arrival.tzinfo is None or arrival.utcoffset() is None:
        return []
    end = arrival + timedelta(minutes=max(0, int(max_layover_min)))
    current = arrival.date()
    dates: list[str] = []
    while current <= end.date():
        dates.append(current.isoformat())
        current += timedelta(days=1)
    return dates


@dataclass(frozen=True, slots=True)
class RouteLegProbeOptions:
    segment_limit: int
    timeout: int
    fail_fast: bool


class RouteLegProbeExecutor:
    """Execute immutable route templates and create dated probes at runtime."""

    def __init__(
        self,
        *,
        options: RouteLegProbeOptions,
        store: Store,
        only_carriers: list[str],
        cache_ttl_seconds: int,
        use_live_cache: bool,
        adapter_resolver: Any | None = None,
        probe_ledger: ProbeRunLedger | None = None,
    ) -> None:
        self.options = options
        self.store = store
        self.only_carriers = list(only_carriers)
        self.cache_ttl_seconds = cache_ttl_seconds
        self.use_live_cache = use_live_cache
        self.adapter_resolver = adapter_resolver
        self.probe_ledger = probe_ledger or ProbeRunLedger()
        self.segment_options = SegmentProbeOptions(
            segment_limit=options.segment_limit,
            timeout=options.timeout,
            fail_fast=options.fail_fast,
        )

    def run(
        self, templates: list[RouteLegTemplate], plan: dict[str, Any]
    ) -> dict[str, Any]:
        route = plan.get("route") if isinstance(plan.get("route"), dict) else {}
        dates = route.get("dates") if isinstance(route.get("dates"), dict) else {}
        max_layover_min = int(
            (plan.get("decision_policy") or {}).get("max_layover_min") or 0
        )
        results = [
            self._run_template(
                template,
                initial_date=str(
                    dates.get("return")
                    if template.direction == "return"
                    else dates.get("depart")
                    or ""
                ),
                currency=str(route.get("currency") or ""),
                provider_policy=str(route.get("provider_policy") or "auto"),
                max_layover_min=max_layover_min,
                plan=plan,
            )
            for template in templates
        ]
        return {
            "route_hypotheses": results,
            "viable_hypotheses": sum(
                1 for result in results if result.get("status") == "viable"
            ),
        }

    def _run_template(
        self,
        template: RouteLegTemplate,
        *,
        initial_date: str,
        currency: str,
        provider_policy: str,
        max_layover_min: int,
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        candidate_dates = [initial_date] if initial_date else []
        legs: list[dict[str, Any]] = []
        for leg_index, policy in enumerate(template.leg_policies):
            origin = template.required_airports[leg_index]
            destination = template.required_airports[leg_index + 1]
            attempts: list[dict[str, Any]] = []
            for date_text in candidate_dates:
                attempts.extend(
                    self._run_leg_policy(
                        template,
                        leg_index=leg_index,
                        origin=origin,
                        destination=destination,
                        date_text=date_text,
                        currency=currency,
                        policy=policy,
                        provider_policy=provider_policy,
                        plan=plan,
                    )
                )
            offers = [
                offer
                for attempt in attempts
                for offer in attempt.get("offers") or []
                if isinstance(offer, dict)
            ]
            legs.append(
                {
                    "leg_index": leg_index,
                    "origin": origin,
                    "destination": destination,
                    "policy": policy,
                    "attempts": attempts,
                    "offer_count": len(offers),
                }
            )
            if not offers:
                return {
                    **template.to_dict(),
                    **_no_offer_status(attempts),
                    "legs": legs,
                }
            candidate_dates = sorted(
                {
                    date_text
                    for offer in offers
                    for date_text in _offer_arrival_dates(offer, max_layover_min)
                }
            )
            if leg_index < len(template.leg_policies) - 1 and not candidate_dates:
                return {
                    **template.to_dict(),
                    "status": "excluded",
                    "reason": "route_leg_arrival_time_missing",
                    "legs": legs,
                }
        return {**template.to_dict(), "status": "viable", "legs": legs}

    def _run_leg_policy(
        self,
        template: RouteLegTemplate,
        *,
        leg_index: int,
        origin: str,
        destination: str,
        date_text: str,
        currency: str,
        policy: str,
        provider_policy: str,
        plan: dict[str, Any],
    ) -> list[dict[str, Any]]:
        direct = self._dispatch(
            template,
            leg_index=leg_index,
            origin=origin,
            destination=destination,
            date_text=date_text,
            currency=currency,
            direct_only=True,
            provider_policy=provider_policy,
            plan=plan,
        )
        if policy == "exact_direct" or any(item.get("offers") for item in direct):
            return direct
        return [
            *direct,
            *self._dispatch(
                template,
                leg_index=leg_index,
                origin=origin,
                destination=destination,
                date_text=date_text,
                currency=currency,
                direct_only=False,
                provider_policy=provider_policy,
                plan=plan,
            ),
        ]

    def _dispatch(
        self,
        template: RouteLegTemplate,
        *,
        leg_index: int,
        origin: str,
        destination: str,
        date_text: str,
        currency: str,
        direct_only: bool,
        provider_policy: str,
        plan: dict[str, Any],
    ) -> list[dict[str, Any]]:
        spec = {
            "role": "route_leg_probe",
            "source_type": "route_hypothesis_leg",
            "probe_type": "segment_direct" if direct_only else "segment_hub_leg",
            "hypothesis_id": template.hypothesis_id,
            "direction": template.direction,
            "leg": f"route_leg_{leg_index}",
            "leg_index": leg_index,
            "required_airports": list(template.required_airports),
            "leg_policy": template.leg_policies[leg_index],
            "origin": origin,
            "destination": destination,
            "origin_airports": [origin],
            "destination_airports": [destination],
            "date": date_text,
            "currency": currency,
            "direct_only": direct_only,
            "only_carriers": self.only_carriers,
        }
        outcomes = dispatch_segment_probe(
            spec=spec,
            plan=plan.get("route") if isinstance(plan.get("route"), dict) else {},
            options=self.segment_options,
            store=self.store,
            only_carriers=self.only_carriers,
            cache_ttl_seconds=self.cache_ttl_seconds,
            use_live_cache=self.use_live_cache,
            provider_policy=provider_policy,
            adapter_resolver=self.adapter_resolver,
            probe_ledger=self.probe_ledger,
        )
        return [_attempt_from_outcome(spec, outcome) for outcome in outcomes]


def _attempt_from_outcome(
    spec: dict[str, Any], outcome: SegmentProbeOutcome
) -> dict[str, Any]:
    summary = dict(outcome.summary or {})
    segment_result = outcome.segment_result or {}
    return {
        **spec,
        "provider": summary.get("provider"),
        "status": summary.get("status") or "ok",
        "execution_state": summary.get("execution_state") or "searched",
        "reason": summary.get("reason"),
        "probe_id": summary.get("probe_id"),
        "offers": [
            offer for offer in segment_result.get("offers") or [] if isinstance(offer, dict)
        ],
    }


def _no_offer_status(attempts: list[dict[str, Any]]) -> dict[str, str]:
    for attempt in attempts:
        if str(attempt.get("execution_state") or "") == "not_executed":
            return {
                "status": "not_executed",
                "reason": str(
                    attempt.get("reason") or "route_leg_not_executed"
                ),
            }
    if any(
        str(attempt.get("execution_state") or "") == "failed"
        or str(attempt.get("status") or "") == "error"
        for attempt in attempts
    ):
        return {"status": "excluded", "reason": "route_leg_probe_failed"}
    return {"status": "excluded", "reason": "route_leg_has_no_offers"}


def _offer_arrival_dates(offer: dict[str, Any], max_layover_min: int) -> list[str]:
    segments = offer.get("segments")
    if not isinstance(segments, list) or not segments:
        return []
    last = segments[-1]
    if not isinstance(last, dict) or not last.get("arrival_at"):
        return []
    try:
        return reachable_local_dates(str(last["arrival_at"]), max_layover_min)
    except ValueError:
        return []


__all__ = [
    "RouteLegProbeExecutor",
    "RouteLegProbeOptions",
    "reachable_local_dates",
]
