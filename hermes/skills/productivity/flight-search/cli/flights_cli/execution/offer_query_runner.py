from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..adapters.providers.registry import provider_adapter
from ..config import DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS
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
    return f"primary_offer:{provider}:{direction}:{origin}-{destination}:{date_text}"


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
    )


def _should_execute_query(query: Mapping[str, Any]) -> tuple[bool, str | None]:
    if str(query.get("role") or "") != "primary_offer_collection":
        return False, "not_primary_offer_collection"
    if str(query.get("source_type") or "") != "provider_full_route":
        return False, "not_provider_full_route_offer_query"
    if not str(query.get("provider") or "").strip():
        return False, "missing_provider"
    return True, None


def run_primary_offer_queries(
    queries: list[dict[str, Any]],
    options: PrimaryOfferQueryOptions,
    *,
    store: Store,
    kupibilet_fetcher: Any | None = None,
    probe_ledger: ProbeExecutionLedger | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    tutu_available_groups: set[tuple[Any, ...]] = set()
    for source_query in queries:
        provider = str(source_query.get("provider") or "").strip().lower()
        query = _normalized_query(source_query, provider=provider, options=options)
        intent = intent_from_aggregate_query(query, provider=provider)
        if probe_ledger is not None:
            probe_ledger.plan_intents([intent])
        fallback_group = _fallback_group_key(query)
        if provider != "tutu" and fallback_group in tutu_available_groups:
            if probe_ledger is not None:
                probe_ledger.record_skipped(intent, reason="tutu_mcp_available")
            results.append(_skipped_result(query, "tutu_mcp_available"))
            continue

        should_execute, skip_reason = _should_execute_query(query)
        if not should_execute:
            if probe_ledger is not None:
                probe_ledger.record_skipped(intent, reason=skip_reason)
            results.append(_skipped_result(query, str(skip_reason)))
            continue

        try:
            adapter = provider_adapter(
                provider,
                store=store,
                kupibilet_fetcher=kupibilet_fetcher,
            )
            result = adapter.search_aggregate(query)
        except CliError as exc:
            error = error_payload_from_cli_error(exc)
            if probe_ledger is not None:
                probe_ledger.record_failed(intent, provider=provider, error=error)
            results.append(_failed_result(query, provider=provider, error=error))
            continue

        if probe_ledger is not None:
            probe_ledger.record_provider_result(intent, result)
        results.append(_result_from_provider_result(query, result))
        if result.provider == "tutu" and result.execution_state == "searched":
            tutu_available_groups.add(fallback_group)
    return results
