from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any

from ..adapters.providers.registry import providers_for_segment
from ..domain.normalize import normalize_carrier_code, parse_iso_date
from ..errors import CliError
from ..providers.fli_mcp import cached_fli_mcp_search, fli_result_to_segment_result, fli_segment_search_summary
from ..providers.kupibilet import cached_kupibilet_search, fetch_kupibilet_search, kupibilet_result_to_segment_result, kupibilet_segment_search_summary
from ..store import Store
from .cache_status import cache_status_from_result
from .failure_classifier import error_payload_from_cli_error
from .request_deduper import DeduperClaim, RequestDeduper


@dataclass(frozen=True)
class SegmentProbeOutcome:
    summary: dict[str, Any]
    segment_result: dict[str, Any] | None = None
    failure: dict[str, Any] | None = None
    include_segment_result: bool = True


def search_key(spec: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(spec.get("direction") or ""),
        str(spec.get("leg") or ""),
        str(spec.get("origin") or "").upper(),
        str(spec.get("destination") or "").upper(),
    )


def dispatch_segment_probe(
    *,
    spec: dict[str, Any],
    plan: dict[str, Any],
    args: argparse.Namespace,
    store: Store,
    only_carriers: list[str],
    cache_ttl_seconds: int,
    use_live_cache: bool,
    provider_policy: str,
    kupibilet_fetcher: Any = fetch_kupibilet_search,
    request_deduper: RequestDeduper | None = None,
) -> list[SegmentProbeOutcome]:
    spec_only_carriers = [
        normalize_carrier_code(code, "only-carrier")
        for code in (spec.get("only_carriers") or only_carriers)
    ]
    outcomes: list[SegmentProbeOutcome] = []
    selected_providers = providers_for_segment(spec, store, provider_policy)
    for provider in selected_providers:
        claim = request_deduper.claim_segment_probe(
            spec=spec,
            provider=provider,
            plan=plan,
            only_carriers=spec_only_carriers,
            limit=args.segment_limit,
            provider_policy=provider_policy,
            mcp_url=getattr(args, "fli_mcp_url", None),
        ) if request_deduper is not None else DeduperClaim(key=(), probe_id="")
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
                    )
                )
            continue
        try:
            segment_date = parse_iso_date(spec["date"], "segment-date")
            if provider == "kupibilet":
                result = cached_kupibilet_search(
                    spec["origin"],
                    spec["destination"],
                    segment_date,
                    currency=plan["currency"],
                    only_carriers=spec_only_carriers,
                    direct_only=True,
                    limit=args.segment_limit,
                    timeout=args.timeout,
                    cache_ttl_seconds=cache_ttl_seconds,
                    use_cache=use_live_cache,
                    fetcher=kupibilet_fetcher,
                )
                segment_result = kupibilet_result_to_segment_result(result, direction=spec["direction"], leg=spec["leg"])
                summary = {**kupibilet_segment_search_summary(spec, result, segment_result), "provider": "kupibilet"}
            elif provider == "fli":
                result = cached_fli_mcp_search(
                    spec["origin"],
                    spec["destination"],
                    segment_date,
                    currency=plan["currency"],
                    only_carriers=spec_only_carriers,
                    direct_only=True,
                    limit=args.segment_limit,
                    timeout=args.timeout,
                    mcp_url=getattr(args, "fli_mcp_url", None),
                    cache_ttl_seconds=cache_ttl_seconds,
                    use_cache=use_live_cache,
                    store=store,
                )
                segment_result = fli_result_to_segment_result(result, direction=spec["direction"], leg=spec["leg"])
                summary = fli_segment_search_summary(spec, result, segment_result)
            else:
                raise CliError(f"unsupported provider {provider!r}", error_type="validation_error")
            summary = {
                **summary,
                "probe_id": claim.probe_id or None,
                "cache_status": cache_status_from_result(result),
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
            if args.fail_fast:
                raise
            outcome = SegmentProbeOutcome(summary=failure, failure=failure)
            if request_deduper is not None:
                request_deduper.record(claim, outcome)
            outcomes.append(outcome)
            continue
        outcome = SegmentProbeOutcome(summary=summary, segment_result=segment_result)
        if request_deduper is not None:
            request_deduper.record(claim, outcome)
        outcomes.append(outcome)
    return outcomes
