"""Compatibility surface for candidate scoring and frontier selection.

The implementation is owned by candidate_scoring, candidate_validation, and
frontier_selection.  This module intentionally contains no ranking policy.
"""

from .candidate_scoring import (
    MIXED_CANDIDATE_RANKING_SCHEMA_VERSION,
    rank_mixed_candidates,
)
from .frontier_selection import (
    DECISION_FRONTIER_SCHEMA_VERSION,
    build_decision_frontier,
)

__all__ = [
    "DECISION_FRONTIER_SCHEMA_VERSION",
    "MIXED_CANDIDATE_RANKING_SCHEMA_VERSION",
    "build_decision_frontier",
    "rank_mixed_candidates",
]
