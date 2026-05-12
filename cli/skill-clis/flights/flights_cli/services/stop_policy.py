from __future__ import annotations

from typing import Any

from ..domain.stop_metrics import candidate_stop_metrics
from ..domain.stop_policy import (
    ALLOW_TWO_STOP_FALLBACK,
    BUSINESS_DEFAULT_STOP_POLICY,
    DEBUG_ALL,
    STRICT_DIRECT_ONE_STOP,
    StopPolicy,
    stop_policy_to_dict,
)


def stop_policy_from_name(name: str) -> StopPolicy:
    normalized = (str(name) if name is not None else "").strip().lower().replace("_", "-")
    if normalized == "business-default":
        return BUSINESS_DEFAULT_STOP_POLICY
    if normalized == "strict-direct-one-stop":
        return STRICT_DIRECT_ONE_STOP
    if normalized == "allow-two-stop-fallback":
        return ALLOW_TWO_STOP_FALLBACK
    if normalized == "debug-all":
        return DEBUG_ALL
    raise ValueError(f"unknown stop policy: {name!r}")


def _coerce_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
        if parsed < 0:
            return fallback
        return parsed
    except (TypeError, ValueError):
        return fallback


def _normalize_policy_name(value: str | None) -> str:
    return str(value or "").strip().replace("_", "-").lower()


def stop_policy_from_args(args: Any) -> StopPolicy:
    policy_name = _normalize_policy_name(getattr(args, "stop_policy", "business-default"))
    try:
        base = stop_policy_from_name(policy_name)
    except ValueError:
        base = BUSINESS_DEFAULT_STOP_POLICY

    max_connections = _coerce_int(getattr(args, "max_connections", None), base.preferred_max_connections)
    fallback_max_connections = _coerce_int(
        getattr(args, "fallback_max_connections", None),
        base.fallback_max_connections,
    )
    max_connections = max(0, max_connections)
    fallback_max_connections = max(0, fallback_max_connections)
    if fallback_max_connections < max_connections:
        fallback_max_connections = max_connections

    allow_two_stop_fallback = base.allow_two_stop_fallback
    suppress_three_plus = base.suppress_three_plus
    hard_max_connections = base.hard_max_connections

    if allow_two_stop_fallback:
        hard_max_connections = max(hard_max_connections, fallback_max_connections)
    else:
        fallback_max_connections = max_connections

    if suppress_three_plus:
        hard_max_connections = min(hard_max_connections, 2)
        fallback_max_connections = min(fallback_max_connections, 2)
        max_connections = min(max_connections, 2)

    if base.name == "debug_all" and bool(getattr(args, "agent_brief", False)):
        suppress_three_plus = True
        hard_max_connections = 2
        fallback_max_connections = min(fallback_max_connections, 2)
        max_connections = min(max_connections, 1)

    return StopPolicy(
        name=base.name,
        preferred_max_connections=max_connections,
        fallback_max_connections=fallback_max_connections,
        hard_max_connections=hard_max_connections,
        allow_two_stop_fallback=allow_two_stop_fallback,
        suppress_three_plus=suppress_three_plus,
    )


def _is_candidate_viable(candidate: dict[str, Any]) -> bool:
    if "validation" in candidate and isinstance(candidate["validation"], dict) and "ok" in candidate["validation"]:
        return bool(candidate["validation"]["ok"])
    if "ok" in candidate:
        return bool(candidate["ok"])
    return True


def _allowed_max_connections(candidates: list[dict[str, Any]], policy: StopPolicy) -> int:
    has_preferred = any(
        item["viable"] and item["max_connections_per_journey"] <= policy.preferred_max_connections
        for item in candidates
    )
    if has_preferred:
        return policy.preferred_max_connections
    if policy.allow_two_stop_fallback:
        return policy.fallback_max_connections
    return policy.preferred_max_connections


def _candidate_stop_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    summary = candidate_stop_metrics(candidate)
    return {
        "max_connections_per_journey": int(summary["max_connections_per_journey"]),
        "stop_tier": summary["stop_tier"],
        "three_plus_connection_journey_count": int(summary["three_plus_connection_journey_count"]),
    }


def apply_stop_policy_frontier(
    candidates: list[dict[str, Any]],
    policy: StopPolicy,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for record in candidates:
        candidate = record
        summary = _candidate_stop_summary(candidate)
        records.append(
            {
                **candidate,
                "max_connections_per_journey": summary["max_connections_per_journey"],
                "three_plus_connection_journey_count": summary["three_plus_connection_journey_count"],
                "stop_tier": summary["stop_tier"],
                "viable": _is_candidate_viable(candidate),
            }
        )

    preferred_viable_count = sum(
        1
        for item in records
        if item["viable"] and item["max_connections_per_journey"] <= policy.preferred_max_connections
    )
    fallback_viable_count = sum(
        1
        for item in records
        if item["viable"]
        and policy.preferred_max_connections < item["max_connections_per_journey"] <= policy.fallback_max_connections
    )
    used_fallback = bool(
        not preferred_viable_count and policy.allow_two_stop_fallback and fallback_viable_count > 0
    )
    allowed_max = _allowed_max_connections(records, policy)
    hard_max = policy.hard_max_connections
    if policy.suppress_three_plus:
        hard_max = min(2, hard_max)

    diagnostics = {
        "preferred_max_connections": policy.preferred_max_connections,
        "fallback_max_connections": policy.fallback_max_connections,
        "hard_max_connections": policy.hard_max_connections,
        "allowed_max_connections": allowed_max,
        "preferred_candidate_count": preferred_viable_count,
        "two_stop_candidate_count": fallback_viable_count,
        "used_fallback_two_stop": used_fallback,
        "three_plus_suppressed_count": 0,
        "two_stop_suppressed_because_preferred_exists": 0,
        "suppressed_by_policy_count": 0,
    }

    accepted: list[dict[str, Any]] = []
    for item in records:
        max_connections = item["max_connections_per_journey"]
        if max_connections > hard_max:
            diagnostics["three_plus_suppressed_count"] += 1
            diagnostics["suppressed_by_policy_count"] += 1
            continue
        if max_connections > allowed_max:
            diagnostics["suppressed_by_policy_count"] += 1
            if (
                item["max_connections_per_journey"] == 2
                and preferred_viable_count > 0
                and policy.allow_two_stop_fallback
            ):
                diagnostics["two_stop_suppressed_because_preferred_exists"] += 1
            continue
        accepted.append(item)

    diagnostics.update(stop_policy_summary(policy, diagnostics))
    return accepted, diagnostics


def stop_policy_summary(policy: StopPolicy, diagnostics: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = stop_policy_to_dict(policy)
    if diagnostics is not None:
        payload["applied"] = True
        payload["used_fallback"] = bool(diagnostics.get("used_fallback_two_stop"))
        payload["suppressed_three_plus"] = int(diagnostics.get("three_plus_suppressed_count", 0))
        payload["suppressed_by_policy"] = int(diagnostics.get("suppressed_by_policy_count", 0))
        payload["preferred_candidate_count"] = int(diagnostics.get("preferred_candidate_count", 0))
        payload["two_stop_candidate_count"] = int(diagnostics.get("two_stop_candidate_count", 0))
        payload["two_stop_suppressed"] = int(diagnostics.get("two_stop_suppressed_because_preferred_exists", 0))
    return payload
