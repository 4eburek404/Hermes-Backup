from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..adapters.providers.registry import (
    not_supported_probe_result,
    provider_adapter,
    providers_for_offer_query,
    route_query_provider_skip_reasons,
    unsupported_providers_for_offer_query,
)
from ..config import DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS
from ..domain.normalize import normalize_carrier_code
from ..errors import CliError
from ..ports.providers import ProbeType, ProviderName, ProviderProbeResult
from ..store import Store
from .failure_classifier import error_payload_from_cli_error
from .probe_intent import intent_from_aggregate_query, intent_from_control
from .probe_ledger import ProbeExecutionLedger


@dataclass(frozen=True, slots=True)
class AggregateControlOptions:
    provider_policy: str
    aggregate_control_limit: int
    only_carriers: tuple[str, ...]
    aggregate_control_carriers: tuple[str, ...]
    live_cache_ttl_seconds: int = DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS
    no_live_cache: bool = False
    timeout: int = 60


def _control_from_not_supported(
    result: ProviderProbeResult,
    *,
    direction: str,
    origin: str,
    destination: str,
    date_text: str,
    carriers: list[str],
) -> dict[str, Any]:
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
        "error": result.errors[0]
        if result.errors
        else {"type": "not_supported", "message": result.result_summary.get("reason")},
    }


def _control_from_skipped(
    *,
    provider: ProviderName,
    reason: str,
    direction: str,
    origin: str,
    destination: str,
    date_text: str,
    carriers: list[str],
) -> dict[str, Any]:
    return {
        "direction": direction,
        "origin": origin,
        "destination": destination,
        "date": date_text,
        "status": "skipped",
        "provider": provider,
        "filters": {"direct_only": False, "only_carriers": carriers},
        "offer_count": 0,
        "raw_offer_count": 0,
        "suppressed_three_plus_count": 0,
        "suppressed_airport_change_count": 0,
        "cache_status": "unknown",
        "reason": reason,
    }


def _aggregate_probe_type(carriers: list[str]) -> ProbeType:
    return "carrier_aggregate" if carriers else "full_route_aggregate"


def _aggregate_probe_id(
    *,
    provider: ProviderName,
    direction: str,
    origin: str,
    destination: str,
    date_text: str,
    carriers: list[str],
) -> str:
    return f"aggregate:{provider}:{direction}:{origin}-{destination}:{date_text}:{','.join(carriers) or 'all'}"


def _record_skipped_aggregate_control(
    *,
    base_query: dict[str, Any],
    provider: ProviderName,
    reason: str,
    direction: str,
    origin: str,
    destination: str,
    date_text: str,
    carriers: list[str],
    probe_ledger: ProbeExecutionLedger | None,
) -> dict[str, Any]:
    query = {
        **base_query,
        "provider": provider,
        "probe_id": _aggregate_probe_id(
            provider=provider,
            direction=direction,
            origin=origin,
            destination=destination,
            date_text=date_text,
            carriers=carriers,
        ),
    }
    intent = intent_from_aggregate_query(query, provider=provider)
    if probe_ledger is not None:
        probe_ledger.plan_intents([intent])
        probe_ledger.record_skipped(intent, reason=reason)
    return _control_from_skipped(
        provider=provider,
        reason=reason,
        direction=direction,
        origin=origin,
        destination=destination,
        date_text=date_text,
        carriers=carriers,
    )


def _graph_derived_control(
    base_query: dict[str, Any],
    offer_graph: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(offer_graph, dict):
        return None
    origin = str(base_query.get("origin") or "").upper()
    destination = str(base_query.get("destination") or "").upper()
    direction = str(base_query.get("direction") or "")
    date_text = str(base_query.get("date") or "")
    carriers = [str(code).upper() for code in base_query.get("only_carriers") or []]
    edges_by_id = {
        str(edge.get("id") or ""): edge
        for edge in offer_graph.get("edges") or []
        if isinstance(edge, dict)
    }
    matches: list[dict[str, Any]] = []
    source_providers: set[str] = set()
    for offer in offer_graph.get("offers") or []:
        if not isinstance(offer, dict):
            continue
        route = [str(code).upper() for code in offer.get("route") or [] if code]
        if not route or route[0] != origin or route[-1] != destination:
            continue
        if bool(base_query.get("direct_only", False)) and len(route) != 2:
            continue
        if direction and str(offer.get("direction") or direction) != direction:
            continue
        edge_ids = [str(edge_id) for edge_id in offer.get("edge_ids") or []]
        edges = [edges_by_id[edge_id] for edge_id in edge_ids if edge_id in edges_by_id]
        if date_text and not _offer_matches_departure_date(edges, date_text):
            continue
        if carriers and not all(
            _edge_matches_carriers(edge, carriers) for edge in edges
        ):
            continue
        provider = str(offer.get("provider") or "").lower()
        if provider:
            source_providers.add(provider)
        matches.append(
            {
                "id": offer.get("id"),
                "source_type": offer.get("source_type"),
                "provider": offer.get("provider"),
                "route": route,
                "price": offer.get("price"),
                "currency": offer.get("currency"),
            }
        )
    if not matches:
        return None
    limit_value = base_query.get("limit")
    top_offer_limit = int(limit_value) if limit_value is not None else 3
    return {
        "direction": direction,
        "origin": origin,
        "destination": destination,
        "date": date_text,
        "status": "graph_derived",
        "provider": "graph",
        "filters": {"direct_only": False, "only_carriers": carriers},
        "offer_count": len(matches),
        "raw_offer_count": len(matches),
        "suppressed_three_plus_count": 0,
        "suppressed_airport_change_count": 0,
        "cache_status": "graph",
        "top_offers": matches[:top_offer_limit],
        "source_type": "graph_derived_control",
        "source_providers": sorted(source_providers),
        "graph_derived": True,
    }


def _offer_matches_departure_date(edges: list[dict[str, Any]], date_text: str) -> bool:
    if not edges:
        return True
    first = edges[0]
    departure_at = str(first.get("departure_at") or "")
    if not departure_at:
        return True
    return departure_at.startswith(date_text)


def _edge_matches_carriers(edge: dict[str, Any], carriers: list[str]) -> bool:
    values = {
        str(edge.get(name) or "").upper()
        for name in ("carrier", "marketing_carrier", "operating_carrier")
        if edge.get(name)
    }
    flight_number = str(edge.get("flight_number") or "").upper()
    if len(flight_number) >= 2:
        values.add(flight_number[:2])
    return bool(values & set(carriers))


def run_aggregate_controls(
    options: AggregateControlOptions,
    plan: dict[str, Any],
    kupibilet_fetcher: Any | None = None,
    probe_ledger: ProbeExecutionLedger | None = None,
    store: Store | None = None,
    offer_graph: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    limit = max(0, int(options.aggregate_control_limit or 0))
    if limit <= 0:
        return []
    active_store = store or Store()

    carrier_sets: list[list[str]] = []
    base_carriers = [
        normalize_carrier_code(code, "only-carrier") for code in options.only_carriers
    ]
    explicit_control_carriers = [
        [normalize_carrier_code(code, "aggregate-control-carrier")]
        for code in options.aggregate_control_carriers
    ]
    if base_carriers:
        carrier_sets.append(base_carriers)
    elif not explicit_control_carriers:
        carrier_sets.append([])
    for carriers in explicit_control_carriers:
        if carriers not in carrier_sets:
            carrier_sets.append(carriers)

    queries = [
        (
            "outbound",
            str(plan["origin"]).upper(),
            str(plan["destination"]).upper(),
            str(plan["dates"]["depart"]),
        ),
    ]
    if plan["dates"].get("return"):
        queries.append(
            (
                "return",
                str(plan["destination"]).upper(),
                str(plan["origin"]).upper(),
                str(plan["dates"]["return"]),
            )
        )

    controls: list[dict[str, Any]] = []
    cache_ttl_seconds = int(options.live_cache_ttl_seconds)
    use_live_cache = not bool(options.no_live_cache)
    for direction, origin, destination, date_text in queries:
        for carriers in carrier_sets:
            probe_type = _aggregate_probe_type(carriers)
            base_query = {
                "probe_type": probe_type,
                "direction": direction,
                "origin": origin,
                "destination": destination,
                "date": date_text,
                "currency": str(plan["currency"]).upper(),
                "only_carriers": carriers,
                "direct_only": False,
                "limit": limit,
                "timeout": int(options.timeout),
                "cache_ttl_seconds": cache_ttl_seconds,
                "use_cache": use_live_cache,
            }
            graph_control = _graph_derived_control(base_query, offer_graph)
            if graph_control is not None:
                query = {
                    **base_query,
                    "provider": "graph",
                    "probe_id": _aggregate_probe_id(
                        provider="graph",
                        direction=direction,
                        origin=origin,
                        destination=destination,
                        date_text=date_text,
                        carriers=carriers,
                    ),
                    "source_type": "graph_derived_control",
                }
                intent = intent_from_aggregate_query(query, provider="graph")
                if probe_ledger is not None:
                    probe_ledger.plan_intents([intent])
                    probe_ledger.record_searched(
                        intent,
                        status="graph_derived",
                        provider="graph",
                        offer_count=graph_control.get("offer_count"),
                        cache_status="graph",
                    )
                controls.append(graph_control)
                continue
            provider_names = providers_for_offer_query(
                base_query, active_store, options.provider_policy
            )
            unsupported_provider_names = unsupported_providers_for_offer_query(
                base_query, active_store, options.provider_policy
            )
            skipped_provider_reasons = route_query_provider_skip_reasons(
                base_query, active_store, options.provider_policy
            )

            tutu_available = False
            for provider_name in provider_names:
                if tutu_available:
                    controls.append(
                        _record_skipped_aggregate_control(
                            base_query=base_query,
                            provider=provider_name,
                            reason="tutu_mcp_available",
                            direction=direction,
                            origin=origin,
                            destination=destination,
                            date_text=date_text,
                            carriers=carriers,
                            probe_ledger=probe_ledger,
                        )
                    )
                    continue
                adapter = provider_adapter(
                    provider_name,
                    store=active_store,
                    kupibilet_fetcher=kupibilet_fetcher,
                )
                query = {
                    **base_query,
                    "provider": adapter.name,
                    "probe_id": _aggregate_probe_id(
                        provider=adapter.name,
                        direction=direction,
                        origin=origin,
                        destination=destination,
                        date_text=date_text,
                        carriers=carriers,
                    ),
                }
                intent = intent_from_aggregate_query(query, provider=adapter.name)
                if probe_ledger is not None:
                    probe_ledger.plan_intents([intent])
                try:
                    result = adapter.search_aggregate(query)
                except CliError as exc:
                    error = error_payload_from_cli_error(exc)
                    if probe_ledger is not None:
                        probe_ledger.record_failed(
                            intent, provider=adapter.name, error=error
                        )
                    controls.append(
                        {
                            "direction": direction,
                            "origin": origin,
                            "destination": destination,
                            "date": date_text,
                            "status": "error",
                            "provider": adapter.name,
                            "filters": {
                                "direct_only": False,
                                "only_carriers": carriers,
                            },
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
                if result.provider == "tutu" and result.execution_state == "searched":
                    tutu_available = True

            for provider_name in unsupported_provider_names:
                if tutu_available:
                    controls.append(
                        _record_skipped_aggregate_control(
                            base_query=base_query,
                            provider=provider_name,
                            reason="tutu_mcp_available",
                            direction=direction,
                            origin=origin,
                            destination=destination,
                            date_text=date_text,
                            carriers=carriers,
                            probe_ledger=probe_ledger,
                        )
                    )
                    continue
                query = {
                    **base_query,
                    "provider": provider_name,
                    "probe_id": _aggregate_probe_id(
                        provider=provider_name,
                        direction=direction,
                        origin=origin,
                        destination=destination,
                        date_text=date_text,
                        carriers=carriers,
                    ),
                }
                intent = intent_from_aggregate_query(query, provider=provider_name)
                if probe_ledger is not None:
                    probe_ledger.plan_intents([intent])
                result = not_supported_probe_result(
                    provider=provider_name,
                    probe_type=probe_type,
                    query=query,
                    reason=f"{provider_name} does not support {probe_type} probes",
                    probe_id=str(query["probe_id"]),
                )
                if probe_ledger is not None:
                    probe_ledger.record_provider_result(intent, result)
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

            for provider_name, reason in skipped_provider_reasons.items():
                controls.append(
                    _record_skipped_aggregate_control(
                        base_query=base_query,
                        provider=provider_name,
                        reason=reason,
                        direction=direction,
                        origin=origin,
                        destination=destination,
                        date_text=date_text,
                        carriers=carriers,
                        probe_ledger=probe_ledger,
                    )
                )
    return controls


def evaluate_graph_coverage_controls(
    plan: dict[str, Any],
    offer_graph: dict[str, Any],
    *,
    probe_ledger: ProbeExecutionLedger | None = None,
) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    for control in plan.get("coverage_controls") or []:
        if not isinstance(control, dict):
            continue
        if control.get("type") != "city_pair_direct":
            continue
        base_query = {
            "probe_type": str(control.get("type") or "city_pair_direct"),
            "direction": str(control.get("direction") or "outbound"),
            "origin": str(control.get("origin") or "").upper(),
            "destination": str(control.get("destination") or "").upper(),
            "date": str(control.get("date") or ""),
            "currency": str(plan.get("currency") or "").upper(),
            "only_carriers": list(control.get("only_carriers") or []),
            "direct_only": True,
            "limit": 1,
        }
        graph_control = _graph_derived_control(base_query, offer_graph)
        if graph_control is None:
            continue
        graph_control["type"] = control.get("type")
        graph_control["negative_evidence"] = control.get("negative_evidence")
        graph_control["source_type"] = "graph_derived_policy_control"
        graph_control["control_policy"] = "coverage_controls"
        intent = intent_from_control(
            {
                **control,
                "provider": "graph",
                "probe_id": f"graph-control:{base_query['direction']}:{base_query['origin']}-{base_query['destination']}:{base_query['date']}",
                "source_type": "graph_derived_policy_control",
            },
            provider="graph",
        )
        if probe_ledger is not None:
            probe_ledger.plan_intents([intent])
            probe_ledger.record_searched(
                intent,
                status="graph_derived",
                provider="graph",
                offer_count=graph_control.get("offer_count"),
                cache_status="graph",
            )
        controls.append(graph_control)
    return controls
