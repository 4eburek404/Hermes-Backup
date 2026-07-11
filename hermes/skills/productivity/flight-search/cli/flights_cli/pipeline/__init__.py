"""Typed internal search-flow skeletons for canonical flight-search commands."""

from ._shared import as_tuple, classify_market, is_direct_only, resolve_country_code
from .evidence_plan import EvidencePlan, plan_evidence
from .flow_decision import FlowDecision, decide_flow
from .search_request import SearchRequest

__all__ = [
    "EvidencePlan",
    "FlowDecision",
    "SearchRequest",
    "as_tuple",
    "classify_market",
    "decide_flow",
    "is_direct_only",
    "plan_evidence",
    "resolve_country_code",
]
