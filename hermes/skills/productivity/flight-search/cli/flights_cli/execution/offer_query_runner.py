from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Mapping

from ..adapters.providers.registry import provider_adapter
from ..config import DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS
from ..domain.normalize import normalize_airport_scope
from ..domain.vocabulary import RequiredControl
from ..errors import CliError
from ..ports.providers import ProviderProbeResult
from ..store import Store
from .failure_classifier import error_payload_from_cli_error
from .probe_intent import intent_from_aggregate_query
from .probe_ledger import ProbeExecutionLedger


@dataclass(frozen=True, slots=True)
class PrimaryOfferQueryOptions:
    live_cache_ttl_seconds: int = DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS
    no_live_cache: bool = False
    timeout: int = 60


def _probe_id(query: Mapping[str, Any], provider: str) -> str:
    supplied = str(query.get("probe_id") or "").strip()
    if supplied:
        return supplied
    direction = str(query.get("direction") or "outbound")
    origin = str(query.get("origin") or "").upper()
    destination = str(query.get("destination") or "").upper()
    date_text = str(query.get("date") or "")
    phase = "direct" if bool(query.get("direct_only")) else "fallback"
    return f"primary_offer:{provider}:{phase}:{direction}:{origin}-{destination}:{date_text}"


def _required_int(query: Mapping[str, Any], name: str) -> int:
    value = query.get(name)
    if value is None:
        raise CliError(
            f"primary offer query missing required {name}",
            error_type="validation_error",
            details={"field": name, "role": query.get("role")},
        )
    return int(value)


def _normalized_query(
    query: Mapping[str, Any],
    *,
    provider: str,
    options: PrimaryOfferQueryOptions,
) -> dict[str, Any]:
    only_carriers = [
        str(code).strip().upper() for code in (query.get("only_carriers") or []) if code
    ]
    origin_airports = normalize_airport_scope(
        list(query.get("origin_airports") or []), "origin-airport"
    )
    destination_airports = normalize_airport_scope(
        list(query.get("destination_airports") or []), "destination-airport"
    )
    return {
        **dict(query),
        "provider": provider,
        "probe_id": _probe_id(query, provider),
        "probe_type": str(
            query.get("probe_type") or RequiredControl.FULL_ROUTE_AGGREGATE
        ),
        "direction": str(query.get("direction") or "outbound"),
        "origin": str(query.get("origin") or "").upper(),
        "destination": str(query.get("destination") or "").upper(),
        "date": str(query.get("date") or ""),
        "currency": str(query.get("currency") or "RUB").upper(),
        "only_carriers": only_carriers,
        "origin_airports": origin_airports,
        "destination_airports": destination_airports,
        "direct_only": bool(query.get("direct_only", False)),
        "limit": _required_int(query, "limit"),
        "timeout": int(query.get("timeout") or options.timeout),
        "cache_ttl_seconds": int(
            query.get("cache_ttl_seconds") or options.live_cache_ttl_seconds
        ),
        "use_cache": bool(query.get("use_cache", not options.no_live_cache)),
    }


def _base_result(query: Mapping[str, Any]) -> dict[str, Any]:
    fields = {
        "role",
        "source_type",
        "probe_type",
        "provider",
        "direction",
        "origin",
        "destination",
        "date",
        "currency",
        "route_family",
        "exhaustive",
        "non_exhaustive_reason",
    }
    return {key: query.get(key) for key in fields if key in query}


def _result_from_provider_result(
    query: Mapping[str, Any], result: ProviderProbeResult
) -> dict[str, Any]:
    summary = result.result_summary if isinstance(result.result_summary, dict) else {}
    payload = {
        **_base_result(query),
        "provider": result.provider,
        "probe_id": result.probe_id or query.get("probe_id"),
        "probe_type": result.probe_type,
        "status": summary.get("status") or result.execution_state,
        "execution_state": result.execution_state,
        "cache_status": result.cache_status,
        "filters": summary.get("filters")
        or {
            "direct_only": bool(query.get("direct_only", False)),
            "only_carriers": list(query.get("only_carriers") or []),
        },
        "offer_count": summary.get("offer_count", len(result.offers)),
        "raw_offer_count": summary.get("raw_offer_count"),
        "omitted_offer_count": summary.get("omitted_offer_count"),
        "top_offers": summary.get("top_offers", list(result.offers)),
        "source_boundary": result.source_boundary,
    }
    if result.errors:
        payload["error"] = result.errors[0]
    return {key: value for key, value in payload.items() if value is not None}


def _skipped_result(query: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        **_base_result(query),
        "provider": query.get("provider"),
        "probe_id": query.get("probe_id"),
        "status": "skipped",
        "execution_state": "skipped",
        "reason": reason,
        "offer_count": 0,
        "raw_offer_count": 0,
        "top_offers": [],
        "cache_status": "unknown",
    }


def _failed_result(
    query: Mapping[str, Any], *, provider: str, error: dict[str, Any]
) -> dict[str, Any]:
    return {
        **_base_result(query),
        "provider": provider,
        "probe_id": query.get("probe_id"),
        "status": "error",
        "execution_state": "failed",
        "offer_count": 0,
        "raw_offer_count": 0,
        "top_offers": [],
        "cache_status": "unknown",
        "error": error,
    }


def _fallback_group_key(query: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        query.get("role"),
        query.get("source_type"),
        query.get("probe_type"),
        query.get("direction"),
        query.get("origin"),
        query.get("destination"),
        query.get("date"),
        query.get("return_date"),
        query.get("currency"),
        bool(query.get("direct_only", False)),
        tuple(query.get("only_carriers") or []),
        tuple(query.get("origin_airports") or []),
        tuple(query.get("destination_airports") or []),
    )


def _should_execute_query(query: Mapping[str, Any]) -> tuple[bool, str | None]:
    if str(query.get("role") or "") != "primary_offer_collection":
        return False, "not_primary_offer_collection"
    if str(query.get("source_type") or "") != "provider_full_route":
        return False, "not_provider_full_route_offer_query"
    if not str(query.get("provider") or "").strip():
        return False, "missing_provider"
    return True, None


def _execute_aggregate_query(
    adapter: Any, query: dict[str, Any]
) -> ProviderProbeResult:
    return adapter.search_aggregate(query)


def _record_query_outcome(
    *,
    query: dict[str, Any],
    provider: str,
    intent: Any,
    outcome: ProviderProbeResult | CliError,
    probe_ledger: ProbeExecutionLedger | None,
) -> dict[str, Any]:
    if isinstance(outcome, CliError):
        error = error_payload_from_cli_error(outcome)
        if probe_ledger is not None:
            probe_ledger.record_failed(intent, provider=provider, error=error)
        return _failed_result(query, provider=provider, error=error)
    if probe_ledger is not None:
        probe_ledger.record_provider_result(intent, outcome)
    return _result_from_provider_result(query, outcome)


def run_primary_offer_queries(
    queries: list[dict[str, Any]],
    options: PrimaryOfferQueryOptions,
    *,
    store: Store,
    kupibilet_fetcher: Any | None = None,
    probe_ledger: ProbeExecutionLedger | None = None,
) -> list[dict[str, Any]]:
    prepared: list[tuple[int, dict[str, Any], str, Any]] = []
    groups: dict[tuple[Any, ...], list[tuple[int, dict[str, Any], str, Any]]] = {}
    for index, source_query in enumerate(queries):
        provider = str(source_query.get("provider") or "").strip().lower()
        query = _normalized_query(source_query, provider=provider, options=options)
        intent = intent_from_aggregate_query(query, provider=provider)
        if probe_ledger is not None:
            probe_ledger.plan_intents([intent])
        item = (index, query, provider, intent)
        prepared.append(item)
        groups.setdefault(_fallback_group_key(query), []).append(item)

    outcomes: dict[int, dict[str, Any]] = {}
    for group_items in groups.values():
        runnable: list[tuple[int, dict[str, Any], str, Any]] = []
        for index, query, provider, intent in group_items:
            should_execute, skip_reason = _should_execute_query(query)
            if should_execute:
                runnable.append((index, query, provider, intent))
                continue
            if probe_ledger is not None:
                probe_ledger.record_skipped(intent, reason=skip_reason)
            outcomes[index] = _skipped_result(query, str(skip_reason))

        primary_pair = [item for item in runnable if item[2] in {"tutu", "kupibilet"}]
        resolved: list[tuple[int, dict[str, Any], str, Any, Any]] = []
        for index, query, provider, intent in primary_pair:
            try:
                adapter = provider_adapter(
                    provider,
                    store=store,
                    kupibilet_fetcher=(
                        kupibilet_fetcher if provider == "kupibilet" else None
                    ),
                )
            except CliError as exc:
                outcomes[index] = _record_query_outcome(
                    query=query,
                    provider=provider,
                    intent=intent,
                    outcome=exc,
                    probe_ledger=probe_ledger,
                )
            else:
                resolved.append((index, query, provider, intent, adapter))

        pair_outcomes: dict[int, ProviderProbeResult | CliError] = {}
        if len(resolved) > 1:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {
                    index: executor.submit(_execute_aggregate_query, adapter, query)
                    for index, query, _provider, _intent, adapter in resolved
                }
                for index, _query, _provider, _intent, _adapter in resolved:
                    try:
                        pair_outcomes[index] = futures[index].result()
                    except CliError as exc:
                        pair_outcomes[index] = exc
        else:
            for index, query, _provider, _intent, adapter in resolved:
                try:
                    pair_outcomes[index] = _execute_aggregate_query(adapter, query)
                except CliError as exc:
                    pair_outcomes[index] = exc

        tutu_searched = False
        for index, query, provider, intent, _adapter in resolved:
            result = pair_outcomes[index]
            outcomes[index] = _record_query_outcome(
                query=query,
                provider=provider,
                intent=intent,
                outcome=result,
                probe_ledger=probe_ledger,
            )
            if (
                provider == "tutu"
                and isinstance(result, ProviderProbeResult)
                and result.execution_state == "searched"
            ):
                tutu_searched = True

        for index, query, provider, intent in runnable:
            if provider in {"tutu", "kupibilet"}:
                continue
            if (
                provider == "fli"
                and not bool(query.get("direct_only"))
                and tutu_searched
            ):
                reason = "provider_fallback_not_needed"
                if probe_ledger is not None:
                    probe_ledger.record_skipped(intent, reason=reason)
                outcomes[index] = _skipped_result(query, reason)
                continue
            try:
                adapter = provider_adapter(provider, store=store)
                result: ProviderProbeResult | CliError = adapter.search_aggregate(query)
            except CliError as exc:
                result = exc
            outcomes[index] = _record_query_outcome(
                query=query,
                provider=provider,
                intent=intent,
                outcome=result,
                probe_ledger=probe_ledger,
            )

    return [outcomes[index] for index, _query, _provider, _intent in prepared]
