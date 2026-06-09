from __future__ import annotations

import argparse
from dataclasses import dataclass

from .evidence_plan import EvidencePlan, plan_evidence
from .flow_decision import FlowDecision, decide_flow
from .search_request import SearchRequest, search_request_from_live_args


@dataclass(frozen=True, slots=True)
class LiveRouteSearchFlow:
    """Typed internal skeleton behind the canonical search request flow."""

    request: SearchRequest
    flow_decision: FlowDecision
    evidence_plan: EvidencePlan


def build_live_route_search_flow(args: argparse.Namespace) -> LiveRouteSearchFlow:
    request = search_request_from_live_args(args)
    flow_decision = decide_flow(request)
    evidence_plan = plan_evidence(request, flow_decision)
    return LiveRouteSearchFlow(
        request=request,
        flow_decision=flow_decision,
        evidence_plan=evidence_plan,
    )
