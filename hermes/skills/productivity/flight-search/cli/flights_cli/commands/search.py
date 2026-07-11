from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any

from ..contracts.registry import current_contract
from ..domain.normalize import parse_iso_date
from ..io import read_json_object
from ..execution.search_executor import SearchRunArtifacts, execute_search
from ..pipeline.result_builder import build_result_projection
from ..pipeline.result_contract import FlightSearchResult, validate_flight_search_result
from ..pipeline.search_request import SearchRequest
from ..store import Store
from .common import validate_contract_payload
from ..errors import CliError

_SEARCH_RESULT_CONTRACT = current_contract("search_result")
SEARCH_RESULT_SCHEMA_VERSION = _SEARCH_RESULT_CONTRACT["schema_version"]


@dataclass(frozen=True, slots=True)
class PreparedSearchRequest:
    typed: SearchRequest

    @property
    def request(self) -> dict[str, Any]:
        return self.typed.to_payload()


@dataclass(frozen=True, slots=True)
class SearchArtifacts:
    request: dict[str, Any]
    execution: SearchRunArtifacts
    projection: dict[str, Any]


def normalize_search_request(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized.setdefault(
        "schema_version", current_contract("search_request")["schema_version"]
    )
    for name in ("origin", "destination", "currency"):
        if name in normalized:
            normalized[name] = str(normalized[name]).upper()
    if "provider_policy" in normalized:
        normalized["provider_policy"] = str(normalized["provider_policy"]).lower()
    route_value = normalized.get("route_options")
    if isinstance(route_value, dict):
        route = dict(route_value)
        for name in ("hubs", "origin_airports", "destination_airports"):
            if isinstance(route.get(name), list):
                route[name] = [str(item).upper() for item in route[name]]
        if "routing_strategy" in route:
            route["routing_strategy"] = str(route["routing_strategy"]).lower()
        normalized["route_options"] = route
    filters_value = normalized.get("filters")
    if isinstance(filters_value, dict):
        filters = dict(filters_value)
        for name in (
            "only_carriers",
            "exclude_carriers",
            "prefer_carriers",
            "avoid_carriers",
        ):
            if isinstance(filters.get(name), list):
                filters[name] = [str(item).upper() for item in filters[name]]
        normalized["filters"] = filters
    evidence_value = normalized.get("evidence")
    if isinstance(evidence_value, dict):
        evidence = dict(evidence_value)
        if isinstance(evidence.get("aggregate_control_carriers"), list):
            evidence["aggregate_control_carriers"] = [
                str(item).upper() for item in evidence["aggregate_control_carriers"]
            ]
        normalized["evidence"] = evidence
    return normalized


def search_request_from_payload(payload: dict[str, Any]) -> SearchRequest:
    normalized = normalize_search_request(payload)
    validate_contract_payload(
        "search_request", normalized, error_type="validation_error"
    )
    return SearchRequest.from_payload(normalized)


def validate_search_request_semantics(request: SearchRequest) -> None:
    depart = parse_iso_date(request.depart_date, "depart-date")
    if request.origin == request.destination:
        raise ValueError("origin and destination must differ")
    if request.return_date:
        return_date = parse_iso_date(request.return_date, "return-date")
        if return_date < depart:
            raise ValueError("return-date must be on or after depart-date")
    if request.date_window_end:
        window_end = parse_iso_date(request.date_window_end, "date-window-end")
        if window_end < depart:
            raise ValueError("date-window-end must be on or after depart-date")
        if request.return_date:
            raise ValueError("date-window-end cannot be combined with return-date")
    overlap = set(request.filters.only_carriers) & set(request.filters.exclude_carriers)
    if overlap:
        raise ValueError(
            f"carrier cannot be both required and excluded: {', '.join(sorted(overlap))}"
        )
    if (
        request.max_connections is not None
        and request.tier2_max_connections is not None
        and request.tier2_max_connections < request.max_connections
    ):
        raise ValueError("tier2-max-connections must not be below max-connections")


def prepare_search_request(request_path: str) -> PreparedSearchRequest:
    request = normalize_search_request(read_json_object(request_path))
    typed = search_request_from_payload(request)
    try:
        validate_search_request_semantics(typed)
    except ValueError as exc:
        raise CliError(str(exc), error_type="validation_error") from exc
    return PreparedSearchRequest(
        typed=typed,
    )


def build_search_artifacts(
    prepared: PreparedSearchRequest, store: Store
) -> SearchArtifacts:
    execution = execute_search(prepared.typed, store)
    projection = build_result_projection(execution.projection_input, store)
    return SearchArtifacts(
        request=prepared.request,
        execution=execution,
        projection=projection,
    )


def build_search_result(
    request: dict[str, Any],
    projection: dict[str, Any],
    catalog_refresh: dict[str, Any] | None = None,
) -> FlightSearchResult:
    refresh = catalog_refresh if isinstance(catalog_refresh, dict) else {}
    checked = refresh.get("checked") if isinstance(refresh.get("checked"), dict) else {}
    update = refresh.get("update") if isinstance(refresh.get("update"), dict) else {}
    evidence = dict(projection["evidence"])
    evidence["catalog_refresh"] = {
        "enabled": bool(refresh.get("enabled")),
        "refreshed": bool(refresh.get("refreshed")),
        "reason": str(refresh.get("reason") or "not_requested"),
        "checked_count": int(checked.get("checked_count") or 0),
        "stale_count": int(checked.get("stale_count") or 0),
        "updated_count": int(update.get("updated_count") or 0),
    }
    result: FlightSearchResult = {
        "schema_version": SEARCH_RESULT_SCHEMA_VERSION,
        "request": request,
        "route": projection["route"],
        "evidence": evidence,
        "frontier": projection["frontier"],
        "answer": projection["answer"],
    }
    validate_contract_payload("search_result", result)
    validate_flight_search_result(result)
    return result


def command_search(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    prepared = prepare_search_request(args.request)
    artifacts = build_search_artifacts(prepared, store)
    return build_search_result(
        artifacts.request,
        artifacts.projection,
        getattr(args, "catalog_refresh_metadata", None),
    )
