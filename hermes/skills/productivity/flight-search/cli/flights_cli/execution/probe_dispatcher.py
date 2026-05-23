from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from typing import Any

from ..adapters.providers.registry import providers_for_segment
from ..config import KUPIBILET_CITY_CODE_FIRST_AIRPORTS
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


def _raw_offer_actual_airports(offer: dict[str, Any]) -> tuple[str, str]:
    flights = offer.get("flights") if isinstance(offer.get("flights"), list) else []
    if not flights:
        origin = str(offer.get("origin") or offer.get("departure_airport") or "").upper()
        destination = str(offer.get("destination") or offer.get("arrival_airport") or "").upper()
        return origin, destination
    first = flights[0] if isinstance(flights[0], dict) else {}
    last = flights[-1] if isinstance(flights[-1], dict) else {}
    origin = str(first.get("origin") or first.get("departure_airport") or "").upper()
    destination = str(last.get("destination") or last.get("arrival_airport") or "").upper()
    return origin, destination


def _city_code_offer_rejection_reason(
    *,
    actual_origin: str,
    actual_destination: str,
    origin_scope: set[str],
    destination_scope: set[str],
) -> str | None:
    if not actual_origin or not actual_destination:
        return "missing_actual_airport_fields"
    if origin_scope and actual_origin not in origin_scope:
        return "origin_out_of_scope"
    if destination_scope and actual_destination not in destination_scope:
        return "destination_out_of_scope"
    return None


def validate_kupibilet_city_code_scope(spec: dict[str, Any], result: dict[str, Any], segment_result: dict[str, Any]) -> dict[str, Any] | None:
    query_origin = str(spec.get("origin") or "").upper()
    query_destination = str(spec.get("destination") or "").upper()
    origin_scope = {str(code).upper() for code in KUPIBILET_CITY_CODE_FIRST_AIRPORTS.get(query_origin, [])}
    destination_scope = {str(code).upper() for code in KUPIBILET_CITY_CODE_FIRST_AIRPORTS.get(query_destination, [])}
    if not origin_scope and not destination_scope:
        return None

    rejected_reasons: Counter[str] = Counter()
    raw_offers = [offer for offer in (result.get("offers") or []) if isinstance(offer, dict)]
    for raw_offer in raw_offers:
        actual_origin, actual_destination = _raw_offer_actual_airports(raw_offer)
        reason = _city_code_offer_rejection_reason(
            actual_origin=actual_origin,
            actual_destination=actual_destination,
            origin_scope=origin_scope,
            destination_scope=destination_scope,
        )
        if reason:
            rejected_reasons[reason] += 1

    accepted_offers: list[dict[str, Any]] = []
    for offer in segment_result.get("offers") or []:
        if not isinstance(offer, dict):
            continue
        actual_origin = str(offer.get("departure_airport") or offer.get("origin") or "").upper()
        actual_destination = str(offer.get("arrival_airport") or offer.get("destination") or "").upper()
        reason = _city_code_offer_rejection_reason(
            actual_origin=actual_origin,
            actual_destination=actual_destination,
            origin_scope=origin_scope,
            destination_scope=destination_scope,
        )
        if reason:
            continue
        accepted_offers.append(offer)

    segment_result["offers"] = accepted_offers
    validation = {
        "query_origin": query_origin,
        "query_destination": query_destination,
        "origin_scope_airports": sorted(origin_scope),
        "destination_scope_airports": sorted(destination_scope),
        "accepted_offer_count": len(accepted_offers),
        "rejected_offer_count": sum(rejected_reasons.values()),
        "rejected_reasons": dict(rejected_reasons),
    }
    return validation


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
                city_code_validation = validate_kupibilet_city_code_scope(spec, result, segment_result)
                summary = {**kupibilet_segment_search_summary(spec, result, segment_result), "provider": "kupibilet"}
                if city_code_validation is not None:
                    summary["city_code_validation"] = city_code_validation
                    if city_code_validation["rejected_offer_count"] and not city_code_validation["accepted_offer_count"]:
                        summary["status"] = "invalid"
                        summary["reason"] = "city_code_scope_validation_failed"
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
