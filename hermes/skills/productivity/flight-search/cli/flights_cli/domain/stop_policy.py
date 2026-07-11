from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


StopTier = Literal["T0_DIRECT", "T1_ONE_STOP", "T2_TWO_STOP", "T3_THREE_PLUS"]


@dataclass(frozen=True)
class StopPolicy:
    name: str
    preferred_max_connections: int = 1
    tier2_max_connections: int = 2
    hard_max_connections: int = 2
    allow_two_stop_tier: bool = True
    suppress_three_plus: bool = True


BUSINESS_DEFAULT_STOP_POLICY = StopPolicy(name="business_default")


def stop_policy_payload(policy: StopPolicy) -> dict[str, Any]:
    return {
        "name": policy.name,
        "preferred_max_connections": policy.preferred_max_connections,
        "tier2_max_connections": policy.tier2_max_connections,
        "hard_max_connections": policy.hard_max_connections,
        "two_stop_allowed_only_if_no_preferred": policy.allow_two_stop_tier,
        "three_plus_reportable": not policy.suppress_three_plus,
    }
