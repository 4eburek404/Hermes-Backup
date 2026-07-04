from __future__ import annotations

import argparse
from typing import Any

from ..config import DEFAULT_CURRENCY, DEFAULT_PROFILE
from ..contracts.registry import current_contract
from ..domain.normalize import parse_iso_date
from ..io import read_json_object
from ..orchestrators.live_route_assembly import run_live_route_assembly
from ..pipeline.options import LiveAssemblyOptions, search_request_to_options
from ..store import Store
from .common import validate_contract_payload

_SEARCH_RESULT_CONTRACT = current_contract("search_result")
SEARCH_RESULT_SCHEMA_VERSION = _SEARCH_RESULT_CONTRACT["schema_version"]


def normalize_search_request(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized.setdefault(
        "schema_version", current_contract("search_request")["schema_version"]
    )
    normalized["origin"] = str(normalized.get("origin") or "").upper()
    normalized["destination"] = str(normalized.get("destination") or "").upper()
    normalized["currency"] = str(normalized.get("currency") or DEFAULT_CURRENCY).upper()
    normalized["profile"] = str(normalized.get("profile") or DEFAULT_PROFILE)
    normalized["ticketing"] = str(normalized.get("ticketing") or "separate")
    normalized["provider_policy"] = str(
        normalized.get("provider_policy") or "auto"
    ).lower()
    return normalized


def live_assembly_options_from_search_request(
    payload: dict[str, Any],
) -> LiveAssemblyOptions:
    validate_contract_payload("search_request", payload, error_type="validation_error")
    return search_request_to_options(payload)


def validate_search_request_dates(payload: dict[str, Any]) -> None:
    parse_iso_date(str(payload.get("depart_date") or ""), "depart-date")
    if payload.get("return_date"):
        parse_iso_date(str(payload.get("return_date") or ""), "return-date")


def build_search_result(
    request: dict[str, Any], route_result: dict[str, Any]
) -> dict[str, Any]:
    public_route_result = dict(route_result)
    agent_report = (
        public_route_result.pop("agent_report")
        if isinstance(public_route_result.get("agent_report"), dict)
        else None
    )
    result = {
        "schema_version": SEARCH_RESULT_SCHEMA_VERSION,
        "wire_version": SEARCH_RESULT_SCHEMA_VERSION,
        "request": request,
        "agent_report": agent_report,
        "route_result": public_route_result,
    }
    validate_contract_payload("search_result", result)
    return result


def command_search(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    request = normalize_search_request(read_json_object(args.request))
    validate_search_request_dates(request)
    live_assembly_options = live_assembly_options_from_search_request(request)
    route_result = run_live_route_assembly(live_assembly_options, store)
    return build_search_result(request, route_result)
