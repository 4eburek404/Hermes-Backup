from __future__ import annotations

import unittest
from unittest.mock import patch

from flights_cli.execution.probe_dispatcher import SegmentProbeOutcome
from flights_cli.orchestrators.live_route_assembly import (
    build_live_route_segment_plan,
    run_live_route_assembly,
)
from flights_cli.pipeline.search_pipeline import build_live_route_search_flow
from flights_cli.store import Store
from helpers import live_assembly_args


def ru_touching_args(**overrides: object):
    values: dict[str, object] = {
        "origin": "SVX",
        "destination": "CDG",
        "depart_date": "2026-08-16",
        "return_date": "2026-08-20",
        "profile": "business",
        "no_live_cache": True,
        "no_direct_route_intel": True,
        "coverage_mode": "targeted",
        "agent_brief": True,
    }
    values.update(overrides)
    return live_assembly_args(**values)


def _empty_ok_dispatch(spec, **_kwargs):
    summary = {
        "direction": spec.get("direction"),
        "leg": spec.get("leg"),
        "origin": spec.get("origin"),
        "destination": spec.get("destination"),
        "date": str(spec.get("date")),
        "status": "ok",
        "provider": "kupibilet",
        "offer_count": 0,
        "cache_status": "live",
    }
    segment_result = {
        "direction": spec.get("direction"),
        "leg": spec.get("leg"),
        "origin": spec.get("origin"),
        "destination": spec.get("destination"),
        "date": str(spec.get("date")),
        "offers": [],
    }
    return [SegmentProbeOutcome(summary=summary, segment_result=segment_result)]


def _gateway_specs(plan: dict) -> list[dict]:
    return [
        spec
        for spec in plan["segments"]
        if spec.get("leg") in {"gateway_to_destination", "destination_to_gateway"}
    ]


class MoscowGatewayPlanTests(unittest.TestCase):
    def test_ru_priority_plan_contains_moscow_gateway_destination_controls(
        self,
    ) -> None:
        plan = build_live_route_segment_plan(ru_touching_args(), Store())
        self.assertEqual(plan["routing_strategy"], "ru-priority")

        gateway_specs = _gateway_specs(plan)
        self.assertTrue(
            gateway_specs,
            "expected moscow gateway_to_destination specs in ru-priority plan",
        )
        outbound = [
            spec for spec in gateway_specs if spec.get("direction") == "outbound"
        ]
        returns = [spec for spec in gateway_specs if spec.get("direction") == "return"]
        self.assertTrue(outbound)
        self.assertTrue(returns)
        self.assertTrue(
            all(
                spec.get("route_family") == "moscow_gateway_control"
                for spec in gateway_specs
            )
        )
        outbound_origins = {str(spec.get("origin")) for spec in outbound}
        self.assertIn(
            "MOW",
            outbound_origins,
            "KupiBilet MOW city-code-first gateway probe expected",
        )
        exact_fallbacks = outbound_origins & {"SVO", "DME", "VKO"}
        self.assertTrue(
            exact_fallbacks, "exact Moscow airport fallback probes expected"
        )
        self.assertTrue(all(str(spec.get("date")) == "2026-08-16" for spec in outbound))
        self.assertTrue(all(str(spec.get("date")) == "2026-08-20" for spec in returns))
        return_destinations = {str(spec.get("destination")) for spec in returns}
        self.assertIn("MOW", return_destinations)

    def test_required_controls_include_moscow_gateway_direct(self) -> None:
        flow = build_live_route_search_flow(ru_touching_args())
        self.assertEqual(flow.flow_decision.routing_strategy, "ru-priority")
        self.assertIn("moscow_gateway_direct", flow.evidence_plan.required_controls)

    def test_gateway_discovery_flag_keeps_moscow_controls_as_control_layer(
        self,
    ) -> None:
        plan = build_live_route_segment_plan(
            ru_touching_args(use_gateway_discovery_for_fallback_hubs=True),
            Store(),
        )

        gateway_specs = _gateway_specs(plan)
        self.assertTrue(gateway_specs)
        self.assertTrue(
            all(
                spec.get("route_family") == "moscow_gateway_control"
                for spec in gateway_specs
            )
        )
        outbound_origins = {
            str(spec.get("origin"))
            for spec in gateway_specs
            if spec.get("direction") == "outbound"
        }
        self.assertIn("MOW", outbound_origins)
        self.assertTrue(outbound_origins & {"SVO", "DME", "VKO"})
        self.assertNotIn("IST", outbound_origins)

    def test_global_non_ru_does_not_inherit_moscow_gateway_controls(self) -> None:
        args = ru_touching_args(origin="CDG", destination="JFK", return_date=None)
        flow = build_live_route_search_flow(args)
        self.assertEqual(flow.flow_decision.market_class, "global_non_ru")
        self.assertNotIn("moscow_gateway_direct", flow.evidence_plan.required_controls)

        plan = build_live_route_segment_plan(args, Store())
        self.assertEqual(_gateway_specs(plan), [])

    def test_domestic_ru_does_not_add_moscow_gateway_destination_controls(self) -> None:
        args = ru_touching_args(origin="SVX", destination="LED", return_date=None)
        flow = build_live_route_search_flow(args)
        self.assertEqual(flow.flow_decision.market_class, "ru_domestic")
        self.assertNotIn("moscow_gateway_direct", flow.evidence_plan.required_controls)

        plan = build_live_route_segment_plan(args, Store())
        self.assertEqual(_gateway_specs(plan), [])

    def test_moscow_endpoint_route_does_not_duplicate_gateway_controls(self) -> None:
        args = ru_touching_args(origin="MOW", destination="IST", return_date=None)
        plan = build_live_route_segment_plan(args, Store())
        self.assertEqual(_gateway_specs(plan), [])


class MoscowGatewayLedgerTests(unittest.TestCase):
    def test_gateway_controls_reach_terminal_ledger_state(self) -> None:
        args = ru_touching_args()
        with patch(
            "flights_cli.orchestrators.live_assembly_runner.dispatch_segment_probe",
            side_effect=_empty_ok_dispatch,
        ):
            result = run_live_route_assembly(args, Store())

        diagnostics = result["live_search"]["probe_ledger"]
        gateway_planned = [
            control
            for control in diagnostics["planned_controls"]
            if control.get("leg")
            in {"gateway_to_destination", "destination_to_gateway"}
        ]
        self.assertTrue(
            gateway_planned, "gateway controls must be planned in the runtime ledger"
        )
        self.assertTrue(
            diagnostics["completeness"]["all_planned_controls_have_terminal_state"]
        )
        not_executed_legs = {
            control.get("leg") for control in diagnostics["not_executed_controls"]
        }
        self.assertNotIn("gateway_to_destination", not_executed_legs)
        self.assertNotIn("destination_to_gateway", not_executed_legs)


if __name__ == "__main__":
    unittest.main()
