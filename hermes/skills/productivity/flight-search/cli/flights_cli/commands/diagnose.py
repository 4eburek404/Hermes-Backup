from __future__ import annotations

import argparse
from typing import Any

from ..execution.diagnostic_probe_runner import run_diagnostic_probe
from ..io import read_json_object
from ..orchestrators.live_route_assembly import build_live_route_segment_plan
from ..orchestrators.search_plan_builder import build_search_plan
from ..pipeline.search_pipeline import build_live_route_search_flow
from ..pipeline.specs import probe_specs_from_segments, segment_specs_from_plan
from ..reporting.user_answer import validate_user_answer
from ..errors import CliError
from ..store import Store
from .metadata import metadata_evidence_scope
from .search import (
    build_search_artifacts,
    live_assembly_options_from_search_request,
    normalize_search_request,
    validate_search_request_dates,
)
from .common import validate_contract_payload


def _agent_report_from_document(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    report = (
        data.get("agent_report") if isinstance(data.get("agent_report"), dict) else data
    )
    return report if isinstance(report, dict) else {}


def command_diagnose_plan(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    request = normalize_search_request(read_json_object(args.request))
    validate_search_request_dates(request)
    live_assembly_options = live_assembly_options_from_search_request(request)
    flow = build_live_route_search_flow(live_assembly_options, store)
    plan = build_live_route_segment_plan(live_assembly_options, store, flow=flow)
    search_plan = build_search_plan(
        live_assembly_options, store, flow=flow, fallback_route_plan=plan
    )
    segments = segment_specs_from_plan(plan)
    probe_specs = probe_specs_from_segments(segments, live_assembly_options)
    provider_queries = [
        *[
            dict(query)
            for query in search_plan.get("primary_offer_queries") or []
            if isinstance(query, dict)
        ],
        *[
            dict(query)
            for query in search_plan.get("gateway_leg_queries") or []
            if isinstance(query, dict)
        ],
    ]
    return {
        "schema_version": "flight_search_plan_diagnostic.v1",
        "request": request,
        "evidence_scope": metadata_evidence_scope("routing metadata"),
        "segments": [segment.as_dict() for segment in segments],
        "probe_specs": [probe.as_dict() for probe in probe_specs],
        "provider_queries": provider_queries,
        "search_plan": search_plan,
        "plan": plan,
    }


def command_diagnose_probe(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    request = read_json_object(args.request)
    return run_diagnostic_probe(args.provider, request, store)


def command_diagnose_trace(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    request = normalize_search_request(read_json_object(args.request))
    validate_search_request_dates(request)
    artifacts = build_search_artifacts(request, store)
    result = {
        "schema_version": "flight_route_trace_diagnostic.v1",
        "request": artifacts["request"],
        "route_trace": artifacts["route_trace"],
        "agent_report": artifacts["agent_report"],
    }
    validate_contract_payload("route_trace", result)
    return result


def command_diagnose_render(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    del store
    payload = read_json_object(args.input)
    report = _agent_report_from_document(payload)
    user_answer = (
        report.get("user_answer")
        if isinstance(report.get("user_answer"), dict)
        else None
    )
    if user_answer is None:
        raise CliError(
            "diagnose render requires data.agent_report.user_answer",
            error_type="validation_error",
        )
    validation: dict[str, Any] = {"ok": True, "errors": []}
    try:
        validate_user_answer(user_answer)
    except CliError as exc:
        validation = {
            "ok": False,
            "errors": (exc.details or {}).get("errors") or [],
        }
    return {
        "schema_version": "flight_search_render_diagnostic.v1",
        "agent_report_schema_version": report.get("schema_version"),
        "user_answer": user_answer,
        "rendered_text": user_answer.get("rendered_text"),
        "validation": validation,
    }
