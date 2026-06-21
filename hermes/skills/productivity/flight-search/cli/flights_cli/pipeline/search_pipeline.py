from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from .evidence_plan import EvidencePlan, plan_evidence
from .flow_decision import FlowDecision, decide_flow
from .options import LiveAssemblyOptions, argparse_args_to_options
from .search_request import SearchRequest, search_request_from_options


@dataclass(frozen=True, slots=True)
class LiveRouteSearchFlow:
    """Typed internal skeleton behind the canonical search request flow."""

    request: SearchRequest
    flow_decision: FlowDecision
    evidence_plan: EvidencePlan


def _as_options(source: LiveAssemblyOptions | Any) -> LiveAssemblyOptions:
    if isinstance(source, LiveAssemblyOptions):
        return source
    return argparse_args_to_options(source)


def build_live_route_search_flow(
    source: LiveAssemblyOptions | Any,
    store: Any | None = None,
    *,
    today_provider: Callable[[], date] | None = None,
) -> LiveRouteSearchFlow:
    options = _as_options(source)
    request = search_request_from_options(options)
    flow_decision = decide_flow(request, store)
    evidence_plan = plan_evidence(request, flow_decision, today_provider=today_provider)
    return LiveRouteSearchFlow(
        request=request,
        flow_decision=flow_decision,
        evidence_plan=evidence_plan,
    )
