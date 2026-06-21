from __future__ import annotations

from typing import Any

from ..execution.synthetic_control_runner import synthesize_moscow_gateway_control_results
from ..pipeline.options import LiveAssemblyOptions
from ..pipeline.search_pipeline import LiveRouteSearchFlow
from ..store import Store
from .live_assembly_runner import LiveAssemblyRunner
from .route_plan_builder import RoutePlanBuilder

__all__ = [
    "build_live_route_segment_plan",
    "run_live_route_assembly",
    "synthesize_moscow_gateway_control_results",
]


def build_live_route_segment_plan(options: LiveAssemblyOptions, store: Store, *, flow: LiveRouteSearchFlow | None = None) -> dict[str, Any]:
    return RoutePlanBuilder(options, store, flow=flow).build()


def run_live_route_assembly(options: LiveAssemblyOptions, store: Store) -> dict[str, Any]:
    return LiveAssemblyRunner(options, store, plan_builder=build_live_route_segment_plan).run()
