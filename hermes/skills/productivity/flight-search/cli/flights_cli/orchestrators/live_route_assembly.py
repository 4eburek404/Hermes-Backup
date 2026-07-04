from __future__ import annotations

from typing import Any

from ..pipeline.options import LiveAssemblyOptions
from ..pipeline.search_pipeline import LiveRouteSearchFlow, build_live_route_search_flow
from ..store import Store
from .live_assembly_runner import LiveAssemblyRunner
from .search_plan_builder import build_runtime_route_plan

__all__ = [
    "build_live_route_segment_plan",
    "run_live_route_assembly",
]


def build_live_route_segment_plan(
    options: LiveAssemblyOptions,
    store: Store,
    *,
    flow: LiveRouteSearchFlow | None = None,
) -> dict[str, Any]:
    live_flow = flow or build_live_route_search_flow(options, store)
    return build_runtime_route_plan(options, live_flow, store)


def run_live_route_assembly(
    options: LiveAssemblyOptions, store: Store
) -> dict[str, Any]:
    return LiveAssemblyRunner(options, store).run()
