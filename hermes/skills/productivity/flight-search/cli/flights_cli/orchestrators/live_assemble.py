from __future__ import annotations

from typing import Any

from ..execution.synthetic_control_runner import synthesize_moscow_gateway_control_results
from ..pipeline.options import LiveAssemblyOptions, argparse_args_to_options
from ..pipeline.search_pipeline import LiveRouteSearchFlow
from ..store import Store
from .live_assembly_runner import LiveAssemblyRunner
from .route_plan_builder import RoutePlanBuilder

# Re-export surface — these names are imported by tests and apps that
# originally used live_assemble before the extraction. New code should
# import from the real source modules directly.
__all__ = [
    # Public API
    "build_live_route_segment_plan",
    "run_live_route_assembly",
    # Re-exported for backward compatibility (test_kupibilet imports this)
    "synthesize_moscow_gateway_control_results",
]


def _as_options(source: LiveAssemblyOptions | Any) -> LiveAssemblyOptions:
    if isinstance(source, LiveAssemblyOptions):
        return source
    return argparse_args_to_options(source)


def build_live_route_segment_plan(source: LiveAssemblyOptions | Any, store: Store, *, flow: LiveRouteSearchFlow | None = None) -> dict[str, Any]:
    return RoutePlanBuilder(_as_options(source), store, flow=flow).build()


def run_live_route_assembly(args: Any, store: Store) -> dict[str, Any]:
    return LiveAssemblyRunner(args, store, plan_builder=build_live_route_segment_plan).run()
