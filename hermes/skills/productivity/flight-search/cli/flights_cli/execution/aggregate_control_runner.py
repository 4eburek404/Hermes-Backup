from __future__ import annotations

import argparse
from typing import Any

from ..adapters.providers.registry import provider_adapter
from ..config import DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS
from ..domain.normalize import normalize_carrier_code
from ..errors import CliError
from ..ports.providers import ProviderProbeResult
from .failure_classifier import error_payload_from_cli_error
from .probe_intent import intent_from_aggregate_query
from .probe_ledger import ProbeExecutionLedger


def _aggregate_provider_name(args: argparse.Namespace) -> str:
    policy = str(getattr(args, "provider_policy", "kupibilet") or "kupibilet").strip().lower()
    if policy == "fli":
        return "fli"
    return "kupibilet"


def _control_from_not_supported(result: ProviderProbeResult, *, direction: str, origin: str, destination: str, date_text: str, carriers: list[str]) -> dict[str, Any]:
    return {
        "direction": direction,
        "origin": origin,
        "destination": destination,
        "date": date_text,
        "status": "not_supported",
        "provider": result.provider,
        "filters": {"direct_only": False, "only_carriers": carriers},
        "offer_count": 0,
        "raw_offer_count": 0,
        "suppressed_three_plus_count": 0,
        "suppressed_airport_change_count": 0,
        "cache_status": result.cache_status,
        "error": result.errors[0] if result.errors else {"type": "not_supported", "message": result.result_summary.get("reason")},
    }


def run_aggregate_controls(
    args: argparse.Namespace,
    plan: dict[str, Any],
    kupibilet_fetcher: Any | None = None,
    probe_ledger: ProbeExecutionLedger | None = None,
) -> list[dict[str, Any]]:
    limit = max(0, int(getattr(args, "aggregate_control_limit", 0) or 0))
    if limit <= 0:
        return []

    carrier_sets: list[list[str]] = []
    base_carriers = [normalize_carrier_code(code, "only-carrier") for code in (getattr(args, "only_carrier", None) or [])]
    explicit_control_carriers = [
        [normalize_carrier_code(code, "aggregate-control-carrier")]
        for code in (getattr(args, "aggregate_control_carrier", None) or [])
    ]
    if base_carriers:
        carrier_sets.append(base_carriers)
    elif not explicit_control_carriers:
        carrier_sets.append([])
    for carriers in explicit_control_carriers:
        if carriers not in carrier_sets:
            carrier_sets.append(carriers)

    queries = [
        ("outbound", str(plan["origin"]).upper(), str(plan["destination"]).upper(), str(plan["dates"]["depart"])),
    ]
    if plan["dates"].get("return"):
        queries.append(("return", str(plan["destination"]).upper(), str(plan["origin"]).upper(), str(plan["dates"]["return"])))

    controls: list[dict[str, Any]] = []
    cache_ttl_seconds = int(getattr(args, "live_cache_ttl_seconds", DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS))
    use_live_cache = not bool(getattr(args, "no_live_cache", False))
    adapter = provider_adapter(_aggregate_provider_name(args), kupibilet_fetcher=kupibilet_fetcher)
    for direction, origin, destination, date_text in queries:
        for carriers in carrier_sets:
            query = {
                "probe_id": f"aggregate:{adapter.name}:{direction}:{origin}-{destination}:{date_text}:{','.join(carriers) or 'all'}",
                "probe_type": "carrier_aggregate" if carriers else "full_route_aggregate",
                "direction": direction,
                "origin": origin,
                "destination": destination,
                "date": date_text,
                "currency": str(plan["currency"]).upper(),
                "only_carriers": carriers,
                "direct_only": False,
                "limit": limit,
                "timeout": int(getattr(args, "timeout", 60)),
                "cache_ttl_seconds": cache_ttl_seconds,
                "use_cache": use_live_cache,
            }
            intent = intent_from_aggregate_query(query, provider=adapter.name)
            if probe_ledger is not None:
                probe_ledger.plan_intents([intent])
            try:
                result = adapter.search_aggregate(query)
            except CliError as exc:
                error = error_payload_from_cli_error(exc)
                if probe_ledger is not None:
                    probe_ledger.record_failed(intent, provider=adapter.name, error=error)
                controls.append(
                    {
                        "direction": direction,
                        "origin": origin,
                        "destination": destination,
                        "date": date_text,
                        "status": "error",
                        "provider": adapter.name,
                        "filters": {"direct_only": False, "only_carriers": carriers},
                        "offer_count": 0,
                        "raw_offer_count": 0,
                        "suppressed_three_plus_count": 0,
                        "suppressed_airport_change_count": 0,
                        "cache_status": "unknown",
                        "error": error,
                    }
                )
                continue
            if probe_ledger is not None:
                probe_ledger.record_provider_result(intent, result)
            if result.execution_state == "not_supported":
                controls.append(
                    _control_from_not_supported(
                        result,
                        direction=direction,
                        origin=origin,
                        destination=destination,
                        date_text=date_text,
                        carriers=carriers,
                    )
                )
                continue
            controls.append(dict(result.result_summary))
    return controls
