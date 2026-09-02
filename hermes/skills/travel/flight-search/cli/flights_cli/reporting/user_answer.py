from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..contracts.registry import current_contract
from .catalog_projection import (
    build_catalog_contract,
    infer_answer_mode,
)
from .catalog_rendering import render_user_answer
from .catalog_semantics import route_requested_round_trip

USER_ANSWER_SCHEMA_VERSION = current_contract("user_answer")["schema_version"]

__all__ = (
    "UserAnswerInput",
    "build_user_answer",
    "render_user_answer",
)


@dataclass(frozen=True, slots=True)
class UserAnswerInput:
    route: dict[str, Any]
    source_boundaries: list[str]
    evidence_status: dict[str, Any]
    primary_options: list[dict[str, Any]]
    alternative_options: list[dict[str, Any]]
    stop_policy: dict[str, Any]
    stop_policy_status: dict[str, Any]


def build_user_answer(answer_input: UserAnswerInput) -> dict[str, Any]:
    recommended = answer_input.primary_options
    priority = answer_input.alternative_options
    route = answer_input.route
    stop_policy = answer_input.stop_policy
    stop_diagnostics = answer_input.stop_policy_status
    two_stop_tier_used = bool(stop_diagnostics.get("used_two_stop_tier"))

    is_round_trip_request = route_requested_round_trip(route)
    selected_option_count = len(recommended) + len(priority)
    catalog = build_catalog_contract(
        recommended,
        priority,
        is_round_trip_request=is_round_trip_request,
        catalog_limit=max(1, selected_option_count),
    )
    answer_mode = infer_answer_mode(options=catalog.get("items") or [])
    route_contract = {
        "origin": route.get("origin"),
        "destination": route.get("destination"),
        "dates": route.get("dates") if isinstance(route.get("dates"), dict) else {},
    }
    catalog_ids = [
        str(item.get("option_id") or "")
        for item in catalog.get("items") or []
        if isinstance(item, dict) and str(item.get("option_id") or "")
    ]
    answer = {
        "schema_version": USER_ANSWER_SCHEMA_VERSION,
        "answer_mode": answer_mode,
        "catalog": catalog,
        "primary_option_id": catalog_ids[0] if catalog_ids else None,
        "alternative_option_ids": catalog_ids[1:],
        "stop_policy_status": {
            "policy": str(
                stop_policy.get("name")
                or stop_diagnostics.get("policy")
                or "business_default"
            ),
            "max_reported_connections": int(
                stop_diagnostics["max_reported_connections"]
            ),
            "two_stop_tier_used": two_stop_tier_used,
            "three_plus_suppressed_count": int(
                stop_diagnostics.get("three_plus_suppressed_count") or 0
            ),
            "garbage_options_suppressed": bool(
                stop_diagnostics.get("garbage_options_hidden_from_answer")
            ),
        },
        "evidence_status": dict(answer_input.evidence_status),
        "required_caveats": {
            "source_boundaries_included": True,
            "coverage_incompleteness_acknowledged": True,
            "provider_failures_acknowledged": True,
            "purchase_screen_verification_required": True,
        },
    }
    answer["rendered_text"] = render_user_answer(answer, route_contract)
    return answer
