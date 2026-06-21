from __future__ import annotations

import argparse
from typing import Any

from ..domain.vocabulary import Leg
from ..adapters.providers.registry import provider_adapter
from ..orchestrators.live_assemble import build_live_route_segment_plan
from ..reporting.projections.human_answer_mirror import build_human_answer_mirror
from ..reporting.user_answer import build_user_answer
from ..store import Store
from .common import read_json_document
from .search import live_assembly_options_from_search_request, normalize_search_request


def _agent_report_from_document(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    report = data.get("agent_report") if isinstance(data.get("agent_report"), dict) else data
    return report if isinstance(report, dict) else {}


def command_diagnose_plan(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    request = normalize_search_request(read_json_document(args.request))
    live_assembly_args = live_assembly_options_from_search_request(request).to_argparse_namespace()
    return {
        "schema_version": "flight_search_plan_diagnostic.v1",
        "request": request,
        "plan": build_live_route_segment_plan(live_assembly_args, store),
    }


def command_diagnose_probe(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    request = read_json_document(args.request)
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
    payload = read_json_document(args.input)
    report = _agent_report_from_document(payload)
    human_answer = build_human_answer_mirror(report)
    user_answer = report.get("user_answer") if isinstance(report.get("user_answer"), dict) else None
    if user_answer is None:
        user_answer = build_user_answer(report, rendered_text=str(human_answer.get("text") or ""))
    return {
        "schema_version": "flight_search_render_diagnostic.v1",
        "agent_report_schema_version": report.get("schema_version"),
        "human_answer": human_answer,
        "user_answer": user_answer,
    }
