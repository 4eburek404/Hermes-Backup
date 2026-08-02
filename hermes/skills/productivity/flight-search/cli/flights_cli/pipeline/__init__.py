"""Typed internal search-flow skeletons for canonical flight-search commands."""

from .flow_decision import FlowDecision, decide_flow
from .search_request import SearchRequest

__all__ = [
    "FlowDecision",
    "SearchRequest",
    "decide_flow",
]
