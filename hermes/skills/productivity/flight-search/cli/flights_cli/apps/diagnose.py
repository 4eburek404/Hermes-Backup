from __future__ import annotations

import argparse
from typing import Any

from ..commands.metadata import metadata_evidence_scope
from ..domain.vocabulary import Leg
from ..adapters.providers.registry import provider_adapter
from ..io import read_json_object
from ..orchestrators.live_route_assembly import build_live_route_segment_plan
from ..pipeline.specs import probe_specs_from_segments, segment_specs_from_plan
from ..reporting.projections.human_answer_mirror import build_human_answer_mirror
from ..reporting.user_answer import build_user_answer
from ..store import Store
from .search import live_assembly_options_from_search_request, normalize_search_request


def _agent_report_from_document(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    report = data.get("agent_report") if isinstance(data.get("agent_report"), dict) else data
    return report if isinstance(report, dict) else {}


def command_diagnose_plan(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    request = normalize_search_request(read_json_object(args.request))
    live_assembly_options = live_assembly_options_from_search_request(request)
    plan = build_live_route_segment_plan(live_assembly_options, store)
    segments = segment_specs_from_plan(plan)
    probe_specs = probe_specs_from_segments(segments, live_assembly_options)
    return {
        "schema_version": "flight_search_plan_diagnostic.v1",
        "request": request,
        "evidence_scope": metadata_evidence_scope("routing metadata"),
        "segments": [segment.as_dict() for segment in segments],
        "probe_specs": [probe.as_dict() for probe in probe_specs],
        "plan": plan,
    }


def command_diagnose_probe(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    request = read_json_object(args.request)
    query = request.get("query") if isinstance(request.get("query"), dict) else dict(request)
    query.setdefault("currency", request.get("currency") or "RUB")
    query.setdefault("probe_id", request.get("probe_id") or f"diagnose-{args.provider}")
    query.setdefault("direction", request.get("direction") or "outbound")
    query.setdefault("leg", request.get("leg") or Leg.DIRECT_OUTBOUND)
    adapter = provider_adapter(args.provider, store=store)
    probe_type = str(request.get("probe_type") or query.get("probe_type") or "segment_direct")
    if probe_type in {"full_route_aggregate", "carrier_aggregate"}:
        result = adapter.search_aggregate(query)
    else:
        result = adapter.search_segment(query)
    return {
        "schema_version": "flight_search_probe_diagnostic.v1",
        "provider": args.provider,
        "probe_type": probe_type,
        "probe": result.as_dict(),
    }


def command_diagnose_render(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    del store
    payload = read_json_object(args.input)
    report = _agent_report_from_document(payload)
    user_answer = report.get("user_answer") if isinstance(report.get("user_answer"), dict) else None
    if user_answer is None:
        user_answer = build_user_answer(report)
    mirror_report = {**report, "user_answer": user_answer}
    human_answer = build_human_answer_mirror(mirror_report)
    return {
        "schema_version": "flight_search_render_diagnostic.v1",
        "agent_report_schema_version": report.get("schema_version"),
        "human_answer": human_answer,
        "user_answer": user_answer,
    }
