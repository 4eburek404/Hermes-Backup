from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from ..errors import CliError
from ..store import Store
from .coverage_evaluator import CoverageEvaluator, CoverageEvaluatorOptions
from .failure_classifier import error_payload_from_cli_error
from .probe_dispatcher import (
    SegmentProbeOptions,
    dispatch_segment_probe,
)
from .probe_intent import ProbeIntent, intent_from_segment
from .probe_ledger import ProbeExecutionLedger
from .request_deduper import RequestDeduper


@dataclass(frozen=True, slots=True)
class GatewayLegProbeOptions:
    gateway_discovery_limit: int
    gateway_probe_batch_size: int
    gateway_probe_max_batches: int
    segment_limit: int
    timeout: int
    fli_mcp_url: str
    fail_fast: bool


class GatewayLegProbeExecutor:
    def __init__(
        self,
        *,
        options: GatewayLegProbeOptions,
        store: Store,
        only_carriers: list[str],
        cache_ttl_seconds: int,
        use_live_cache: bool,
        kupibilet_fetcher: Any | None = None,
        request_deduper: RequestDeduper | None = None,
        probe_ledger: ProbeExecutionLedger | None = None,
    ) -> None:
        self.options = options
        self.store = store
        self.only_carriers = list(only_carriers)
        self.cache_ttl_seconds = cache_ttl_seconds
        self.use_live_cache = use_live_cache
        self.kupibilet_fetcher = kupibilet_fetcher
        self.request_deduper = request_deduper or RequestDeduper()
        self.probe_ledger = probe_ledger
        self.segment_options = SegmentProbeOptions(
            segment_limit=options.segment_limit,
            timeout=options.timeout,
            fli_mcp_url=options.fli_mcp_url,
            fail_fast=options.fail_fast,
        )

    def run(
        self, queries: list[dict[str, Any]], plan: dict[str, Any]
    ) -> dict[str, Any]:
        grouped = _gateway_query_groups(queries)
        eligible_gateways = self._eligible_gateways(grouped)
        evaluator = CoverageEvaluator(
            CoverageEvaluatorOptions(
                min_gateways_searched=len(eligible_gateways),
                min_viable_gateways=1,
                planned_probes_terminal=True,
            )
        )
        gateways: list[dict[str, Any]] = []
        evaluations: list[dict[str, Any]] = []
        batch_size = max(0, int(self.options.gateway_probe_batch_size))
        max_batches = max(0, int(self.options.gateway_probe_max_batches))
        stop_reason = "gateway_probe_budget_exhausted"
        for batch_index, gateway_batch in enumerate(
            _batches(eligible_gateways, batch_size),
            start=1,
        ):
            if batch_index > max_batches:
                break
            for gateway in gateway_batch:
                gateways.append(self._execute_gateway(gateway, grouped[gateway], plan))
            evaluation = evaluator.evaluate(
                gateways,
                total_gateway_count=len(grouped),
                batch_index=batch_index,
                max_batches=max_batches,
            )
            evaluations.append(
                {
                    **evaluation.to_dict(),
                    "batch_index": batch_index,
                    "max_batches": max_batches,
                }
            )
            if not evaluation.continue_search:
                if "viable_gateway_found" in evaluation.reasons:
                    stop_reason = "gateway_probe_coverage_satisfied"
                break

        searched_codes = {str(gateway.get("gateway") or "") for gateway in gateways}
        for gateway, gateway_queries in grouped.items():
            if gateway in searched_codes:
                continue
            gateways.append(
                _not_searched_gateway(gateway, gateway_queries, stop_reason)
            )
        return _coverage(gateways, evaluations=evaluations)

    def _eligible_gateways(
        self, grouped: "OrderedDict[str, dict[str, list[dict[str, Any]]]]"
    ) -> list[str]:
        candidate_limit = max(0, int(self.options.gateway_discovery_limit))
        batch_size = max(0, int(self.options.gateway_probe_batch_size))
        max_batches = max(0, int(self.options.gateway_probe_max_batches))
        batch_budget = batch_size * max_batches
        if candidate_limit <= 0 or batch_budget <= 0:
            return []
        allowed_count = min(candidate_limit, batch_budget, len(grouped))
        return list(grouped)[:allowed_count]

    def _execute_gateway(
        self,
        gateway: str,
        gateway_queries: dict[str, list[dict[str, Any]]],
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        item = _gateway_result(gateway, searched=True)
        for leg_key in ("origin_leg", "destination_leg"):
            queries = gateway_queries.get(leg_key) or []
            if not queries:
                item["skipped_reasons"].append(f"{leg_key}_query_missing")
                item["missing_legs"].append(leg_key)
                item[leg_key] = _missing_leg_result(leg_key)
                continue
            direct_queries = [query for query in queries if query.get("direct_only")]
            broad_queries = [query for query in queries if not query.get("direct_only")]
            direct_results = [self._execute_leg(query, plan) for query in direct_queries]
            direct_found = any(
                int(result.get("offer_count") or 0) > 0 for result in direct_results
            )
            if direct_found:
                for query in broad_queries:
                    intent = intent_from_segment(
                        query, provider=str(query.get("provider") or "") or None
                    )
                    if self.probe_ledger is not None:
                        self.probe_ledger.plan_intents([intent])
                        self.probe_ledger.record_skipped(
                            intent, reason="direct_available"
                        )
                broad_results: list[dict[str, Any]] = []
            else:
                broad_results = [
                    self._execute_leg(query, plan) for query in broad_queries
                ]
            leg_results = [*direct_results, *broad_results]
            leg_result = _merge_leg_results(leg_results)
            item[leg_key] = leg_result
            item["provider_failures"].extend(
                result["failure"]
                for result in leg_results
                if isinstance(result.get("failure"), dict)
            )
            if int(leg_result.get("offer_count") or 0) <= 0 and leg_result.get(
                "skipped_reason"
            ):
                item["skipped_reasons"].append(str(leg_result["skipped_reason"]))
            if int(leg_result.get("offer_count") or 0) <= 0:
                item["missing_legs"].append(leg_key)
        item["viable"] = not item["missing_legs"] and not item["skipped_reasons"]
        return item

    def _execute_leg(
        self, query: dict[str, Any], plan: dict[str, Any]
    ) -> dict[str, Any]:
        provider = str(query.get("provider") or "").strip().lower()
        intent = intent_from_segment(query, provider=provider or None)
        if self.probe_ledger is not None:
            self.probe_ledger.plan_intents([intent])
        if not provider:
            if self.probe_ledger is not None:
                self.probe_ledger.record_skipped(intent, reason="missing_provider")
            return _skipped_leg_result(query, "missing_provider")
        if str(query.get("execution_state") or "") == "skipped":
            reason = str(query.get("reason") or "gateway_leg_query_skipped")
            if self.probe_ledger is not None:
                self.probe_ledger.record_skipped(intent, reason=reason)
            return _skipped_leg_result(
                query,
                reason,
            )
        try:
            outcomes = dispatch_segment_probe(
                spec=query,
                plan=plan,
                options=self.segment_options,
                store=self.store,
                only_carriers=self.only_carriers,
                cache_ttl_seconds=self.cache_ttl_seconds,
                use_live_cache=self.use_live_cache,
                provider_policy=provider,
                kupibilet_fetcher=self.kupibilet_fetcher,
                request_deduper=self.request_deduper,
            )
        except CliError as exc:
            if self.options.fail_fast:
                raise
            error = error_payload_from_cli_error(exc)
            if self.probe_ledger is not None:
                self.probe_ledger.record_failed(intent, provider=provider, error=error)
            failure = {
                **_leg_identity(query),
                "provider": provider,
                "status": "error",
                "error": error,
            }
            return {
                **_leg_identity(query),
                "provider": provider,
                "status": "error",
                "execution_state": "failed",
                "offer_count": 0,
                "failure": failure,
            }
        if self.probe_ledger is not None:
            self._record_ledger_outcome(intent, outcomes)
        return _leg_result_from_outcomes(query, outcomes)

    def _record_ledger_outcome(self, intent: ProbeIntent, outcomes: list[Any]) -> None:
        assert self.probe_ledger is not None
        if not outcomes:
            self.probe_ledger.record_skipped(
                intent, reason="provider_returned_no_outcome"
            )
            return
        outcome = outcomes[0]
        summary = dict(getattr(outcome, "summary", {}) or {})
        provider = summary.get("provider") or intent.provider
        status = summary.get("status") or "ok"
        failure = getattr(outcome, "failure", None)
        if failure is not None:
            self.probe_ledger.record_failed(
                intent, provider=provider, error=failure.get("error")
            )
            return
        if status == "deduped":
            self.probe_ledger.record_deduped(
                intent, original_probe_id=summary.get("original_probe_id")
            )
            return
        if status == "not_supported":
            self.probe_ledger.record_not_supported(
                intent, provider=provider, reason=summary.get("reason")
            )
            return
        if status == "skipped":
            self.probe_ledger.record_skipped(
                intent, reason=summary.get("reason") or "provider_skipped"
            )
            return
        self.probe_ledger.record_searched(
            intent,
            status=status,
            provider=provider,
            offer_count=summary.get("offer_count"),
            cache_status=summary.get("cache_status"),
        )


def _gateway_query_groups(
    queries: list[dict[str, Any]],
) -> "OrderedDict[str, dict[str, list[dict[str, Any]]]]":
    rows = [
        query
        for query in queries
        if isinstance(query, dict)
        and str(query.get("role") or "") == "gateway_leg_probe"
        and str(query.get("gateway") or "").strip()
    ]
    rows.sort(
        key=lambda query: (
            int(query.get("gateway_rank") or 0),
            str(query.get("gateway") or "").upper(),
            0 if str(query.get("leg") or "") == "origin_to_gateway" else 1,
            str(query.get("date") or ""),
        )
    )
    grouped: "OrderedDict[str, dict[str, list[dict[str, Any]]]]" = OrderedDict()
    for query in rows:
        gateway = str(query.get("gateway") or "").upper()
        group = grouped.setdefault(gateway, {})
        leg = str(query.get("leg") or "")
        if leg == "origin_to_gateway":
            group.setdefault("origin_leg", []).append(query)
        elif leg == "gateway_to_destination":
            group.setdefault("destination_leg", []).append(query)
    return grouped


def _coverage(
    gateways: list[dict[str, Any]],
    *,
    evaluations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    searched_gateways = [item for item in gateways if item.get("searched")]
    viable_gateways = [item for item in searched_gateways if item.get("viable")]
    failed_gateways = [
        item for item in searched_gateways if item.get("provider_failures")
    ]
    not_searched_budget = len([item for item in gateways if not item.get("searched")])
    coverage_evaluations = list(evaluations or [])
    coverage_evaluation = (
        dict(coverage_evaluations[-1]) if coverage_evaluations else None
    )
    return {
        "searched_gateways": len(searched_gateways),
        "viable_gateways": len(viable_gateways),
        "failed_gateways": len(failed_gateways),
        "not_searched_budget": not_searched_budget,
        "coverage_evaluation": coverage_evaluation,
        "coverage_evaluations": coverage_evaluations,
        "gateways": gateways,
    }


def _gateway_result(gateway: str, *, searched: bool) -> dict[str, Any]:
    return {
        "gateway": gateway,
        "searched": searched,
        "viable": False,
        "origin_leg": None,
        "destination_leg": None,
        "provider_failures": [],
        "skipped_reasons": [],
        "missing_legs": [],
    }


def _not_searched_gateway(
    gateway: str,
    gateway_queries: dict[str, list[dict[str, Any]]],
    reason: str = "gateway_probe_budget_exhausted",
) -> dict[str, Any]:
    item = _gateway_result(gateway, searched=False)
    item["skipped_reasons"] = [reason]
    item["origin_leg"] = _not_searched_leg_result(
        (gateway_queries.get("origin_leg") or [None])[0], reason
    )
    item["destination_leg"] = _not_searched_leg_result(
        (gateway_queries.get("destination_leg") or [None])[0], reason
    )
    return item


def _batches(items: list[str], size: int) -> list[list[str]]:
    if size <= 0:
        return []
    return [items[index : index + size] for index in range(0, len(items), size)]


def _leg_identity(query: dict[str, Any]) -> dict[str, Any]:
    item = {
        "leg": query.get("leg"),
        "origin": query.get("origin"),
        "destination": query.get("destination"),
        "date": query.get("date"),
        "gateway": query.get("gateway"),
    }
    if "wave_index" in query:
        item["wave_index"] = query.get("wave_index")
    return item


def _not_searched_leg_result(
    query: dict[str, Any] | None, reason: str
) -> dict[str, Any] | None:
    if not query:
        return None
    return {
        **_leg_identity(query),
        "provider": query.get("provider"),
        "status": "not_executed",
        "execution_state": "not_executed",
        "offer_count": 0,
        "skipped_reason": reason,
    }


def _missing_leg_result(leg_key: str) -> dict[str, Any]:
    return {
        "leg": leg_key,
        "status": "skipped",
        "execution_state": "skipped",
        "offer_count": 0,
        "skipped_reason": f"{leg_key}_query_missing",
    }


def _skipped_leg_result(query: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        **_leg_identity(query),
        "provider": query.get("provider"),
        "status": "skipped",
        "execution_state": "skipped",
        "offer_count": 0,
        "skipped_reason": reason,
    }


def _leg_result_from_outcomes(
    query: dict[str, Any], outcomes: list[Any]
) -> dict[str, Any]:
    if not outcomes:
        return _skipped_leg_result(query, "provider_returned_no_outcome")
    outcome = outcomes[0]
    summary = dict(getattr(outcome, "summary", {}) or {})
    segment_result = getattr(outcome, "segment_result", None) or {}
    offers = list(segment_result.get("offers") or [])
    offer_count = int(summary.get("offer_count") or len(offers))
    result = {
        **_leg_identity(query),
        "provider": summary.get("provider") or query.get("provider"),
        "status": summary.get("status") or "ok",
        "execution_state": summary.get("execution_state") or "searched",
        "probe_id": summary.get("probe_id"),
        "cache_status": summary.get("cache_status"),
        "offer_count": offer_count,
        "offers": offers,
    }
    for name in (
        "source_type",
        "probe_type",
        "direct_only",
        "gateway_rank",
        "only_carriers",
        "preferred_carriers",
    ):
        if name in query:
            result[name] = query.get(name)
    failure = getattr(outcome, "failure", None)
    if failure is not None:
        result["failure"] = failure
        result["execution_state"] = "failed"
        result["offer_count"] = 0
    if result["status"] in {"skipped", "not_supported"}:
        result["skipped_reason"] = summary.get("reason") or result["status"]
    return {key: value for key, value in result.items() if value is not None}


def _merge_leg_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return _missing_leg_result("unknown_leg")
    merged = dict(results[0])
    offers = [
        offer
        for result in results
        for offer in result.get("offers") or []
        if isinstance(offer, dict)
    ]
    merged["offers"] = offers
    merged["offer_count"] = len(offers)
    merged["searched_dates"] = list(
        dict.fromkeys(
            str(result.get("date") or "")
            for result in results
            if str(result.get("date") or "")
        )
    )
    if offers:
        merged["status"] = "ok"
        merged["execution_state"] = "searched"
        merged.pop("failure", None)
        merged.pop("skipped_reason", None)
    elif all(result.get("skipped_reason") for result in results):
        merged["skipped_reason"] = "all_gateway_leg_dates_skipped"
    return merged
