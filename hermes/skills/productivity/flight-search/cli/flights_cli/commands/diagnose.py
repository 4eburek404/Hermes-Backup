from __future__ import annotations

import argparse
from typing import Any

from ..contracts.registry import ROUTE_TRACE_SCHEMA_VERSION
from ..contracts.validation import validate_contract_payload
from ..errors import CliError
from ..execution.diagnostic_probe_runner import run_diagnostic_probe
from ..io import read_json_object
from ..orchestrators.search_workflow import SearchWorkflow
from ..pipeline.search_plan import SEARCH_PLAN_DIAGNOSTIC_SCHEMA_VERSION
from ..reporting.user_answer import (
    USER_ANSWER_RENDER_DIAGNOSTIC_SCHEMA_VERSION,
    validate_user_answer,
)
from ..store import Store
from .metadata import metadata_evidence_scope
from .search import (
    build_search_artifacts,
    prepare_search_request,
)


def _result_from_document(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    return data if isinstance(data, dict) else {}


def command_diagnose_plan(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    prepared = prepare_search_request(args.request)
    request = prepared.request
    search_plan = SearchWorkflow(store).plan(prepared.typed).to_dict()
    validate_contract_payload("search_plan", search_plan)
    return {
        "schema_version": SEARCH_PLAN_DIAGNOSTIC_SCHEMA_VERSION,
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
    evidence = execution.evidence.to_trace_dict()
    date_window_inventory = execution.projection_input.get("live_search", {}).get(
        "date_window_inventory"
    )
    if isinstance(date_window_inventory, dict):
        evidence["date_window_inventory"] = date_window_inventory
    result = {
        "schema_version": ROUTE_TRACE_SCHEMA_VERSION,
        "request": artifacts.request,
        "plan": execution.plan,
        "evidence": evidence,
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
        "schema_version": USER_ANSWER_RENDER_DIAGNOSTIC_SCHEMA_VERSION,
        "search_result_schema_version": result.get("schema_version"),
        "user_answer": user_answer,
        "rendered_text": user_answer.get("rendered_text"),
        "validation": validation,
    }
