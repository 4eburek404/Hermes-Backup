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


def stop_policy_to_dict(policy: StopPolicy) -> dict[str, Any]:
    return {
        "name": policy.name,
        "preferred_max_connections": policy.preferred_max_connections,
        "fallback_max_connections": policy.fallback_max_connections,
        "hard_max_connections": policy.hard_max_connections,
        "allow_two_stop_fallback": policy.allow_two_stop_fallback,
        "suppress_three_plus": policy.suppress_three_plus,
    }


BUSINESS_DEFAULT_STOP_POLICY = StopPolicy(
    name="business_default",
    preferred_max_connections=1,
    fallback_max_connections=2,
    hard_max_connections=2,
    allow_two_stop_fallback=True,
    suppress_three_plus=True,
)

STRICT_DIRECT_ONE_STOP = StopPolicy(
    name="strict_direct_one_stop",
    preferred_max_connections=1,
    fallback_max_connections=1,
    hard_max_connections=1,
    allow_two_stop_fallback=False,
    suppress_three_plus=True,
)

ALLOW_TWO_STOP_FALLBACK = StopPolicy(
    name="allow_two_stop_fallback",
    preferred_max_connections=1,
    fallback_max_connections=2,
    hard_max_connections=2,
    allow_two_stop_fallback=True,
    suppress_three_plus=True,
)

DEBUG_ALL = StopPolicy(
    name="debug_all",
    preferred_max_connections=1,
    fallback_max_connections=3,
    hard_max_connections=4,
    allow_two_stop_fallback=True,
    suppress_three_plus=False,
)
