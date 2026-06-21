"""Typed internal search-flow skeletons for canonical flight-search commands."""

from ._shared import as_tuple, classify_market, is_direct_only, resolve_country_code
from .evidence_plan import EvidencePlan, plan_evidence
from .flow_decision import FlowDecision, decide_flow
from .search_pipeline import LiveRouteSearchFlow, build_live_route_search_flow
from .search_request import SearchRequest, search_request_from_options
from .specs import ProbeSpec, SegmentSpec, probe_specs_from_segments, segment_specs_from_plan

__all__ = [
    "EvidencePlan",
    "FlowDecision",
    "LiveRouteSearchFlow",
    "SearchRequest",
    "ProbeSpec",
    "SegmentSpec",
    "as_tuple",
    "build_live_route_search_flow",
    "classify_market",
    "decide_flow",
    "is_direct_only",
    "plan_evidence",
    "resolve_country_code",
    "search_request_from_options",
    "probe_specs_from_segments",
    "segment_specs_from_plan",
]
