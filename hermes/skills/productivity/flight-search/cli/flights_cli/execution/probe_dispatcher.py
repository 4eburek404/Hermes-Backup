from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..adapters.providers.registry import provider_adapters_for_segment
from ..domain.normalize import normalize_airport_scope, normalize_carrier_code
from ..errors import CliError
from ..ports.providers import ProviderProbeResult
from ..store import Store
from .failure_classifier import error_payload_from_cli_error
from .request_deduper import DeduperClaim, RequestDeduper


@dataclass(frozen=True)
class SegmentProbeOutcome:
    summary: dict[str, Any]
    segment_result: dict[str, Any] | None = None
    failure: dict[str, Any] | None = None
    include_segment_result: bool = True
    provider_result: ProviderProbeResult | None = None


@dataclass(frozen=True, slots=True)
class SegmentProbeOptions:
    segment_limit: int
    timeout: int
    fail_fast: bool


def segment_probe_type(spec: dict[str, Any]) -> str:
    probe_type = str(spec.get("probe_type") or "")
    if probe_type:
        return probe_type
    leg = str(spec.get("leg") or "")
    return "segment_direct" if "direct" in leg else "segment_hub_leg"


def segment_query(
    *,
    spec: dict[str, Any],
    plan: dict[str, Any],
    options: SegmentProbeOptions,
    only_carriers: list[str],
    cache_ttl_seconds: int,
    use_live_cache: bool,
    provider_policy: str,
    probe_id: str,
) -> dict[str, Any]:
    direct_only = bool(spec.get("direct_only", True))
    origin_airports = normalize_airport_scope(
        list(spec.get("origin_airports") or []), "origin-airport"
    )
    destination_airports = normalize_airport_scope(
        list(spec.get("destination_airports") or []), "destination-airport"
    )
    return {
        "probe_id": probe_id,
        "probe_type": segment_probe_type(spec),
        "direction": spec["direction"],
        "leg": spec["leg"],
        "origin": str(spec["origin"]).upper(),
        "destination": str(spec["destination"]).upper(),
        "date": str(spec["date"]),
        "currency": str(plan["currency"]).upper(),
        "only_carriers": only_carriers,
        "origin_airports": origin_airports,
        "destination_airports": destination_airports,
        "direct_only": direct_only,
        "limit": int(options.segment_limit),
        "timeout": int(options.timeout),
        "cache_ttl_seconds": cache_ttl_seconds,
        "use_cache": use_live_cache,
        "provider_policy": provider_policy,
    }


def outcome_summary_from_provider_result(
    result: ProviderProbeResult, *, delegated_probe_id: str | None = None
) -> dict[str, Any]:
    summary = dict(result.result_summary)
    summary.setdefault("provider", result.provider)
    if result.execution_state == "not_supported":
        summary.setdefault("status", "not_supported")
        summary.setdefault("offer_count", 0)
    elif result.execution_state == "failed":
        summary.setdefault("status", "error")
        summary.setdefault("offer_count", 0)
    else:
        summary.setdefault("status", "ok")
    summary["probe_id"] = result.probe_id or delegated_probe_id or None
    summary["cache_status"] = result.cache_status
    return summary


def dispatch_segment_probe(
    *,
    spec: dict[str, Any],
    plan: dict[str, Any],
    options: SegmentProbeOptions,
    store: Store,
    only_carriers: list[str],
    cache_ttl_seconds: int,
    use_live_cache: bool,
    provider_policy: str,
    kupibilet_fetcher: Any | None = None,
    request_deduper: RequestDeduper | None = None,
) -> list[SegmentProbeOutcome]:
    spec_only_carriers = [
        normalize_carrier_code(code, "only-carrier")
        for code in (spec.get("only_carriers") or only_carriers)
    ]
    outcomes: list[SegmentProbeOutcome] = []
    selected_adapters = provider_adapters_for_segment(
        spec,
        store,
        provider_policy,
        kupibilet_fetcher=kupibilet_fetcher,
    )
    for adapter in selected_adapters:
        provider = adapter.name
        claim = (
            request_deduper.claim_segment_probe(
                spec=spec,
                provider=provider,
                plan=plan,
                only_carriers=spec_only_carriers,
                limit=options.segment_limit,
                provider_policy=provider_policy,
                direct_only=bool(spec.get("direct_only", True)),
            )
            if request_deduper is not None
            else DeduperClaim(key=(), probe_id="")
        )
        if claim.is_duplicate:
            original = claim.original
            if isinstance(original, SegmentProbeOutcome):
                summary = {
                    **original.summary,
                    **spec,
                    "provider": provider,
                    "status": "deduped",
                    "reason": "duplicate_segment_probe",
                    "probe_id": claim.probe_id,
                    "original_probe_id": claim.original_probe_id,
                }
                outcomes.append(
                    SegmentProbeOutcome(
                        summary=summary,
                        segment_result=original.segment_result,
                        include_segment_result=False,
                        provider_result=original.provider_result,
                    )
                )
            continue
        try:
            result = adapter.search_segment(
                segment_query(
                    spec=spec,
                    plan=plan,
                    options=options,
                    only_carriers=spec_only_carriers,
                    cache_ttl_seconds=cache_ttl_seconds,
                    use_live_cache=use_live_cache,
                    provider_policy=provider_policy,
                    probe_id=claim.probe_id,
                )
            )
            summary = outcome_summary_from_provider_result(
                result, delegated_probe_id=claim.probe_id
            )
            segment_result = {
                "direction": spec.get("direction"),
                "leg": spec.get("leg"),
                "offers": list(result.offers),
            }
        except CliError as exc:
            failure = {
                **spec,
                "provider": provider,
                "status": "error",
                "probe_id": claim.probe_id or None,
                "cache_status": "unknown",
                "error": error_payload_from_cli_error(exc),
            }
            if options.fail_fast:
                raise
            outcome = SegmentProbeOutcome(summary=failure, failure=failure)
            if request_deduper is not None:
                request_deduper.record(claim, outcome)
            outcomes.append(outcome)
            continue
        outcome = SegmentProbeOutcome(
            summary=summary, segment_result=segment_result, provider_result=result
        )
        if request_deduper is not None:
            request_deduper.record(claim, outcome)
        outcomes.append(outcome)
        if result.provider == "tutu" and result.execution_state == "searched":
            break
    return outcomes
