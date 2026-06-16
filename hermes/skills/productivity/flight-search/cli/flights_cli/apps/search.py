from __future__ import annotations

import argparse
from typing import Any

from ..config import (
    DEFAULT_COVERAGE_CONTROL_LIMIT,
    DEFAULT_CURRENCY,
    DEFAULT_DIRECT_ROUTE_INDEX_TTL_SECONDS,
    DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS,
    DEFAULT_ROUTE_ASSEMBLE_LIMIT_PER_PAIR,
    DEFAULT_ROUTING_STRATEGY,
    FLI_MCP_DEFAULT_URL,
)
from ..contracts.registry import current_contract
from ..orchestrators.live_assemble import run_live_route_assembly
from ..store import Store
from .common import read_json_document, validate_contract_payload

_SEARCH_RESULT_CONTRACT = current_contract("search_result")
SEARCH_RESULT_SCHEMA_VERSION = _SEARCH_RESULT_CONTRACT["schema_version"]


def _list_option(container: dict[str, Any], name: str, default: list[Any] | None = None) -> list[Any] | None:
    value = container.get(name)
    if value is None:
        return default
    if isinstance(value, list):
        return value
    return [value]


def _int_option(container: dict[str, Any], name: str, default: int | None) -> int | None:
    value = container.get(name)
    if value is None:
        return default
    return int(value)


def _bool_option(container: dict[str, Any], name: str, default: bool = False) -> bool:
    value = container.get(name)
    if value is None:
        return default
    return bool(value)


def normalize_search_request(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized.setdefault("schema_version", current_contract("search_request")["schema_version"])
    normalized["origin"] = str(normalized.get("origin") or "").upper()
    normalized["destination"] = str(normalized.get("destination") or "").upper()
    normalized["currency"] = str(normalized.get("currency") or DEFAULT_CURRENCY).upper()
    normalized["profile"] = str(normalized.get("profile") or "balanced")
    normalized["ticketing"] = str(normalized.get("ticketing") or "separate")
    normalized["provider_policy"] = str(normalized.get("provider_policy") or "auto").lower()
    return normalized


def live_assembly_args_from_search_request(payload: dict[str, Any]) -> argparse.Namespace:
    request = normalize_search_request(payload)
    validate_contract_payload("search_request", request, error_type="validation_error")
    route = request.get("route_options") if isinstance(request.get("route_options"), dict) else {}
    evidence = request.get("evidence") if isinstance(request.get("evidence"), dict) else {}
    filters = request.get("filters") if isinstance(request.get("filters"), dict) else {}
    output = request.get("output") if isinstance(request.get("output"), dict) else {}
    return argparse.Namespace(
        command_name="search",
        origin=request["origin"],
        destination=request["destination"],
        depart_date=str(request["depart_date"]),
        return_date=request.get("return_date"),
        hub=_list_option(route, "hubs"),
        routing_strategy=str(route.get("routing_strategy") or DEFAULT_ROUTING_STRATEGY),
        origin_airport=_list_option(route, "origin_airports"),
        destination_airport=_list_option(route, "destination_airports"),
        max_airports_per_city=_int_option(route, "max_airports_per_city", 6),
        currency=request["currency"],
        coverage_mode=str(route.get("coverage_mode") or "targeted"),
        coverage_control=_list_option(route, "coverage_controls"),
        coverage_control_limit=_int_option(route, "coverage_control_limit", DEFAULT_COVERAGE_CONTROL_LIMIT),
        ticketing=request["ticketing"],
        profile=request["profile"],
        min_same_airport_min=_int_option(route, "min_same_airport_min", 120),
        min_cross_airport_min=_int_option(route, "min_cross_airport_min", 300),
        stop_policy=str(route.get("stop_policy") or "business-default"),
        date_window_end=route.get("date_window_end"),
        max_connections=_int_option(route, "max_connections", None),
        tier2_max_connections=_int_option(route, "tier2_max_connections", None),
        include_stop_policy_diagnostics=_bool_option(output, "include_stop_policy_diagnostics", False),
        segment_limit=_int_option(evidence, "segment_limit", 30),
        timeout=_int_option(evidence, "timeout", 60),
        outbound_second_leg_day_offset=_list_option(evidence, "outbound_second_leg_day_offsets"),
        return_second_leg_day_offset=_list_option(evidence, "return_second_leg_day_offsets"),
        limit_per_pair=_int_option(output, "limit_per_pair", DEFAULT_ROUTE_ASSEMBLE_LIMIT_PER_PAIR),
        candidate_pool_limit=_int_option(output, "candidate_pool_limit", 5000),
        max_candidates=_int_option(output, "max_candidates", 50),
        max_reasons=_int_option(output, "max_reasons", 5),
        include_candidates=_int_option(output, "include_candidates", 5),
        include_ranked_candidates=_int_option(output, "include_ranked_candidates", 5),
        include_rejected_pairs=_int_option(output, "include_rejected_pairs", 20),
        include_segment_results=_int_option(output, "include_segment_results", 0),
        aggregate_control_limit=_int_option(evidence, "aggregate_control_limit", 0),
        aggregate_control_carrier=_list_option(evidence, "aggregate_control_carriers"),
        max_segment_searches=_int_option(evidence, "max_segment_searches", 300),
        fail_fast=_bool_option(evidence, "fail_fast", False),
        live_cache_ttl_seconds=_int_option(evidence, "live_cache_ttl_seconds", DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS),
        no_live_cache=_bool_option(evidence, "no_live_cache", False),
        direct_route_index_ttl_seconds=_int_option(evidence, "direct_route_index_ttl_seconds", DEFAULT_DIRECT_ROUTE_INDEX_TTL_SECONDS),
        no_direct_route_intel=_bool_option(evidence, "no_direct_route_intel", False),
        agent_report=True,
        agent_brief=_bool_option(output, "agent_brief", True),
        only_carrier=_list_option(filters, "only_carriers"),
        exclude_carrier=_list_option(filters, "exclude_carriers"),
        prefer_carrier=_list_option(filters, "prefer_carriers"),
        avoid_carrier=_list_option(filters, "avoid_carriers"),
        include_filtered=_int_option(output, "include_filtered", 20),
        provider_policy=request["provider_policy"],
        fli_mcp_url=str(evidence.get("fli_mcp_url") or FLI_MCP_DEFAULT_URL),
    )


def build_search_result(request: dict[str, Any], route_result: dict[str, Any]) -> dict[str, Any]:
    result = {
        "schema_version": SEARCH_RESULT_SCHEMA_VERSION,
        "wire_version": SEARCH_RESULT_SCHEMA_VERSION,
        "request": request,
        "agent_report": route_result.get("agent_report") if isinstance(route_result.get("agent_report"), dict) else None,
        "route_result": route_result,
    }
    validate_contract_payload("search_result", result)
    return result


def command_search(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    request = normalize_search_request(read_json_document(args.request))
    live_assembly_args = live_assembly_args_from_search_request(request)
    route_result = run_live_route_assembly(live_assembly_args, store)
    return build_search_result(request, route_result)
