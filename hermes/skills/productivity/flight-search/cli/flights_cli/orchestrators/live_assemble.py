from __future__ import annotations

import argparse
from typing import Any

from ..execution.synthetic_control_runner import synthesize_moscow_gateway_control_results
from ..pipeline.search_pipeline import LiveRouteSearchFlow
from ..store import Store
from .live_assembly_runner import (
    LiveAssemblyRunner,
    city_code_primary_keys_for_deferred_airport,
    direct_route_intel_context,
    endpoint_group_code,
    fetch_kupibilet_search,
    hub_viability_summary,
    plan_has_svx_direct_control,
    preferred_keys_for_deferred_airport,
    provider_city_code_side,
)
from .route_plan_builder import (
    RoutePlanBuilder,
    city_code_first_segment_options,
    normalize_day_offsets,
    provider_policy_allows_kupibilet,
    resolve_date_window,
)

# Re-export fetch_kupibilet_search for backward compatibility.
# Tests and callers that patch ``flights_cli.orchestrators.live_assemble.fetch_kupibilet_search``
# should now patch ``flights_cli.orchestrators.live_assembly_runner.fetch_kupibilet_search``
# instead, because LiveAssemblyRunner reads the hook from its own module.
# The re-export here is kept so that ``from live_assemble import fetch_kupibilet_search``
# still works for any code that imported it before the split.

# Re-export planner-only helpers for backward compatibility.
# Code that imported these from live_assemble before the extraction will
# continue to work; new code should import from route_plan_builder directly.


def build_live_route_segment_plan(args: argparse.Namespace, store: Store, *, flow: LiveRouteSearchFlow | None = None) -> dict[str, Any]:
    return RoutePlanBuilder(args, store, flow=flow).build()


def run_live_route_assembly(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    return LiveAssemblyRunner(args, store, plan_builder=build_live_route_segment_plan).run()