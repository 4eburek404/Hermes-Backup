from __future__ import annotations

import argparse
from typing import Any

from ..execution.diagnostic_probe_runner import run_diagnostic_probe
from ..io import read_json_object
from ..orchestrators.search_plan_builder import build_search_plan
from ..reporting.user_answer import validate_user_answer
from ..errors import CliError
from ..store import Store
from .metadata import metadata_evidence_scope
from .search import (
    build_search_artifacts,
    prepare_search_request,
)
from .common import validate_contract_payload


def _result_from_document(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    return data if isinstance(data, dict) else {}


def command_diagnose_plan(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    prepared = prepare_search_request(args.request)
    request = prepared.request
    search_plan = build_search_plan(prepared.typed, store)
    validate_contract_payload("search_plan", search_plan)
    return {
        "schema_version": "flight_search_plan_diagnostic.v2",
        "request": request,
        "evidence_scope": metadata_evidence_scope("routing metadata"),
        "plan": search_plan,
    }


def command_diagnose_probe(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    request = read_json_object(args.request)
    return run_diagnostic_probe(args.provider, request, store)


def command_diagnose_trace(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    prepared = prepare_search_request(args.request)
    artifacts = build_search_artifacts(prepared, store)
    execution = artifacts.execution
    result = {
        "schema_version": "flight_route_trace_diagnostic.v4",
        "request": artifacts.request,
        "plan": execution.plan,
        "evidence": execution.evidence.to_trace_dict(),
        "decision": {
            "offer_graph": execution.decision.offer_graph,
            "candidate_envelope": execution.decision.offer_candidates,
            "scorer": execution.decision.scored_decisions.get("scorer") or {},
            "frontier": execution.decision.decision_frontier,
        },
        "answer": artifacts.projection["answer"],
    }
    validate_contract_payload("route_trace", result)
    return result


def command_diagnose_render(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    del store
    payload = read_json_object(args.input)
    result = _result_from_document(payload)
    user_answer = (
        result.get("answer") if isinstance(result.get("answer"), dict) else None
    )
    if user_answer is None:
        raise CliError(
            "diagnose render requires data.answer",
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
        "search_result_schema_version": result.get("schema_version"),
        "user_answer": user_answer,
        "rendered_text": user_answer.get("rendered_text"),
        "validation": validation,
    }
