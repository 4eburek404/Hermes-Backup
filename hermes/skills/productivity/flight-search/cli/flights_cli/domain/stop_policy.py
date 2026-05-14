from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

StopTier = Literal["T0_DIRECT", "T1_ONE_STOP", "T2_TWO_STOP", "T3_THREE_PLUS"]


@dataclass(frozen=True)
class StopPolicy:
    name: str
    preferred_max_connections: int = 1
    fallback_max_connections: int = 2
    hard_max_connections: int = 2
    allow_two_stop_fallback: bool = True
    suppress_three_plus: bool = True


@dataclass(frozen=True)
class StopPolicyDecision:
    stop_tier: StopTier
    max_connections_per_journey: int
    eligible_for_preferred_generation: bool
    eligible_for_fallback_generation: bool
    reportable_by_stop_policy: bool
    requires_fallback_mode: bool
    suppressed: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "stop_tier": self.stop_tier,
            "max_connections_per_journey": self.max_connections_per_journey,
            "eligible_for_preferred_generation": self.eligible_for_preferred_generation,
            "eligible_for_fallback_generation": self.eligible_for_fallback_generation,
            "reportable_by_stop_policy": self.reportable_by_stop_policy,
            "requires_fallback_mode": self.requires_fallback_mode,
            "suppressed": self.suppressed,
            "reason": self.reason,
        }


BUSINESS_DEFAULT_STOP_POLICY = StopPolicy(name="business_default")
STRICT_DIRECT_ONE_STOP_POLICY = StopPolicy(
    name="strict_direct_one_stop",
    fallback_max_connections=1,
    hard_max_connections=1,
    allow_two_stop_fallback=False,
)
DEBUG_ALL_STOP_POLICY = StopPolicy(
    name="debug_all",
    preferred_max_connections=2,
    fallback_max_connections=99,
    hard_max_connections=99,
    allow_two_stop_fallback=True,
    suppress_three_plus=False,
)


STOP_POLICY_ALIASES = {
    "business-default": BUSINESS_DEFAULT_STOP_POLICY,
    "business_default": BUSINESS_DEFAULT_STOP_POLICY,
    "allow-two-stop-fallback": BUSINESS_DEFAULT_STOP_POLICY,
    "allow_two_stop_fallback": BUSINESS_DEFAULT_STOP_POLICY,
    "strict-direct-one-stop": STRICT_DIRECT_ONE_STOP_POLICY,
    "strict_direct_one_stop": STRICT_DIRECT_ONE_STOP_POLICY,
    "debug-all": DEBUG_ALL_STOP_POLICY,
    "debug_all": DEBUG_ALL_STOP_POLICY,
}


def stop_policy_from_args(args: Any) -> StopPolicy:
    raw_name = str(getattr(args, "stop_policy", "") or "business-default")
    base = STOP_POLICY_ALIASES.get(raw_name, BUSINESS_DEFAULT_STOP_POLICY)
    if raw_name in {"debug-all", "debug_all"} and bool(getattr(args, "agent_brief", False)):
        base = BUSINESS_DEFAULT_STOP_POLICY
    max_connections = getattr(args, "max_connections", None)
    fallback_max_connections = getattr(args, "fallback_max_connections", None)
    if max_connections is None and fallback_max_connections is None:
        return base
    preferred = base.preferred_max_connections if max_connections is None else int(max_connections)
    fallback = base.fallback_max_connections if fallback_max_connections is None else int(fallback_max_connections)
    hard = min(base.hard_max_connections, fallback) if base.suppress_three_plus else fallback
    return StopPolicy(
        name=base.name,
        preferred_max_connections=preferred,
        fallback_max_connections=fallback,
        hard_max_connections=hard,
        allow_two_stop_fallback=base.allow_two_stop_fallback and fallback > preferred,
        suppress_three_plus=base.suppress_three_plus,
    )


def stop_policy_payload(policy: StopPolicy) -> dict[str, Any]:
    return {
        "name": policy.name,
        "preferred_max_connections": policy.preferred_max_connections,
        "fallback_max_connections": policy.fallback_max_connections,
        "hard_max_connections": policy.hard_max_connections,
        "two_stop_allowed_only_if_no_preferred": policy.allow_two_stop_fallback,
        "three_plus_reportable": not policy.suppress_three_plus,
    }


def reportable_max_connections(policy: StopPolicy, preferred_available: bool) -> int:
    if preferred_available:
        return policy.preferred_max_connections
    if policy.allow_two_stop_fallback:
        return policy.fallback_max_connections
    return policy.preferred_max_connections


def stop_tier_from_count(connection_count: int) -> StopTier:
    count = max(0, int(connection_count))
    if count == 0:
        return "T0_DIRECT"
    if count == 1:
        return "T1_ONE_STOP"
    if count == 2:
        return "T2_TWO_STOP"
    return "T3_THREE_PLUS"


def max_connections_from_metrics(metrics: dict[str, Any] | int) -> int:
    if isinstance(metrics, int):
        return max(0, metrics)
    return max(0, int(metrics.get("max_connections_per_journey") or metrics.get("connection_count") or metrics.get("change_count") or 0))


def decide_stop_policy(
    metrics: dict[str, Any] | int,
    policy: StopPolicy,
    *,
    preferred_available: bool = False,
    fallback_mode: bool = False,
) -> StopPolicyDecision:
    max_connections = max_connections_from_metrics(metrics)
    stop_tier = stop_tier_from_count(max_connections)
    suppressed = False
    reason = "preferred_stop_tier"
    if policy.suppress_three_plus and max_connections >= 3:
        suppressed = True
        reason = "three_plus_suppressed"
    elif max_connections > policy.hard_max_connections:
        suppressed = True
        reason = "hard_max_connections_exceeded"

    eligible_preferred = not suppressed and max_connections <= policy.preferred_max_connections
    eligible_fallback = not suppressed and max_connections <= policy.fallback_max_connections
    if not policy.allow_two_stop_fallback and not eligible_preferred:
        eligible_fallback = False

    requires_fallback_mode = not eligible_preferred
    reportable = eligible_preferred or (
        eligible_fallback and requires_fallback_mode and (fallback_mode or not preferred_available)
    )

    if suppressed:
        pass
    elif eligible_preferred:
        reason = "preferred_stop_tier"
    elif reportable:
        reason = "fallback_stop_tier"
    elif eligible_fallback and preferred_available:
        reason = "fallback_suppressed_because_preferred_exists"
    elif eligible_fallback:
        reason = "fallback_requires_fallback_mode"
    else:
        reason = "fallback_max_connections_exceeded"

    return StopPolicyDecision(
        stop_tier=stop_tier,
        max_connections_per_journey=max_connections,
        eligible_for_preferred_generation=eligible_preferred,
        eligible_for_fallback_generation=eligible_fallback,
        reportable_by_stop_policy=reportable,
        requires_fallback_mode=requires_fallback_mode,
        suppressed=suppressed,
        reason=reason,
    )
