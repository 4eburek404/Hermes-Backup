from __future__ import annotations

import unittest
from unittest.mock import patch

from flights_cli.execution.probe_dispatcher import SegmentProbeOutcome
from flights_cli.orchestrators.live_route_assembly import run_live_route_assembly
from flights_cli.pipeline.search_pipeline import build_live_route_search_flow
from flights_cli.store import Store
from helpers import live_assembly_args


def live_args(**overrides: object):
    defaults = {
        "origin": "SVX",
        "destination": "CDG",
        "depart_date": "2026-08-16",
        "return_date": None,
        "profile": "business",
        "provider_policy": "auto",
        "max_segment_searches": 10,
        "live_cache_ttl_seconds": 0,
        "no_live_cache": True,
        "direct_route_index_ttl_seconds": 0,
        "no_direct_route_intel": True,
        "include_segment_results": 0,
        "aggregate_control_limit": 0,
        "coverage_mode": "targeted",
        "coverage_control_limit": 12,
        "agent_report": False,
        "agent_brief": False,
    }
    defaults.update(overrides)
    return live_assembly_args(**defaults)


class LiveRoutePipelineTests(unittest.TestCase):
    def test_live_route_args_adapt_to_typed_search_flow(self) -> None:
        args = live_assembly_args(
            origin="SVX",
            destination="CDG",
            depart_date="2026-08-16",
            return_date="2026-08-20",
            profile="business",
            agent_brief=True,
            no_live_cache=True,
            no_direct_route_intel=True,
        )

        flow = build_live_route_search_flow(args)

        self.assertEqual(flow.request.command_name, "search")
        self.assertEqual(flow.request.origin, "SVX")
        self.assertEqual(flow.request.destination, "CDG")
        self.assertEqual(flow.request.depart_date, "2026-08-16")
        self.assertEqual(flow.request.return_date, "2026-08-20")
        self.assertEqual(flow.request.currency, "RUB")
        self.assertEqual(flow.request.profile, "business")
        self.assertEqual(flow.request.provider_policy, "auto")
        self.assertEqual(flow.flow_decision.intent_class, "route_recommendation")
        self.assertEqual(flow.flow_decision.evidence_class, "shopping_advisory")
        self.assertEqual(flow.flow_decision.provider_policy, "auto")
        self.assertFalse(flow.evidence_plan.live_cache_enabled)
        self.assertFalse(flow.evidence_plan.direct_route_intel_enabled)
        self.assertEqual(flow.evidence_plan.max_segment_searches, 300)

    def test_live_assembly_runner_uses_typed_flow_without_public_report_shape_change(
        self,
    ) -> None:
        plan = {
            "origin": "SVX",
            "destination": "CDG",
            "dates": {"depart": "2026-08-16", "return": None},
            "currency": "RUB",
            "profile": "business",
            "ticketing": "separate",
            "routing_strategy": "auto",
            "hubs": [],
            "route_graph": {"nodes": [], "edges": [], "strategy": "auto"},
            "route_families": [],
            "segments": [],
            "coverage_mode": "targeted",
            "coverage_limits": {},
            "coverage_controls": [],
            "metrics": {"segment_search_count": 0},
        }

        with (
            patch(
                "flights_cli.orchestrators.live_assembly_runner.build_live_route_search_flow",
                wraps=build_live_route_search_flow,
            ) as build_flow,
            patch(
                "flights_cli.orchestrators.live_route_assembly.build_live_route_segment_plan",
                return_value=plan,
            ),
            patch(
                "flights_cli.orchestrators.live_assembly_runner.empty_assembled_result",
                return_value={},
            ),
            patch(
                "flights_cli.orchestrators.live_assembly_runner.run_aggregate_controls",
                return_value=[],
            ),
            patch(
                "flights_cli.orchestrators.live_assembly_runner.hub_viability_summary",
                return_value=[],
            ),
        ):
            result = run_live_route_assembly(live_args(), Store())

        self.assertEqual(build_flow.call_count, 1)
        self.assertIn("live_search", result)
        self.assertEqual(result["live_search"]["provider_policy"], "auto")
        self.assertEqual(
            result["live_search"]["plan"],
            {key: value for key, value in plan.items() if key != "segments"},
        )
        search_plan = result["live_search"]["diagnostics"]["search_plan"]
        self.assertEqual(search_plan["schema_version"], "flight_search_plan.v1")
        self.assertEqual(search_plan["fallback_segment_plan"]["segments"], [])
        self.assertEqual(result["live_search"]["segment_searches"], [])
        self.assertEqual(result["live_search"]["aggregate_controls"], [])
        self.assertNotIn("flow_decision", result)
        self.assertNotIn("evidence_plan", result)
        self.assertNotIn("search_request", result)
        self.assertNotIn("flow_decision", result["live_search"])
        self.assertNotIn("evidence_plan", result["live_search"])
        self.assertNotIn("search_request", result["live_search"])

    def test_primary_offer_queries_execute_before_segment_probes(self) -> None:
        events: list[str] = []
        plan = {
            "origin": "SVX",
            "destination": "CDG",
            "dates": {"depart": "2026-08-16", "return": None},
            "currency": "RUB",
            "profile": "business",
            "ticketing": "separate",
            "routing_strategy": "auto",
            "hubs": [],
            "route_graph": {"nodes": [], "edges": [], "strategy": "auto"},
            "route_families": [],
            "segments": [
                {
                    "direction": "outbound",
                    "leg": "origin_to_hub",
                    "origin": "SVX",
                    "destination": "IST",
                    "date": "2026-08-16",
                }
            ],
            "coverage_mode": "targeted",
            "coverage_limits": {},
            "coverage_controls": [],
            "metrics": {"segment_search_count": 1},
        }
        search_plan = {
            "schema_version": "flight_search_plan.v1",
            "primary_offer_queries": [
                {
                    "role": "primary_offer_collection",
                    "source_type": "provider_full_route",
                    "probe_type": "full_route_aggregate",
                    "provider": "kupibilet",
                    "direction": "outbound",
                    "origin": "SVX",
                    "destination": "CDG",
                    "date": "2026-08-16",
                    "currency": "RUB",
                    "direct_only": False,
                    "limit": 10,
                    "route_family": "ru_to_western_europe_bridge",
                }
            ],
            "mandatory_controls": [],
            "gateway_discovery": {"enabled": False, "reason": None},
            "fallback_segment_plan": {"segments": list(plan["segments"])},
            "coverage_expectations": [],
        }
        primary_results = [
            {
                "role": "primary_offer_collection",
                "source_type": "provider_full_route",
                "provider": "kupibilet",
                "status": "ok",
                "execution_state": "searched",
                "offer_count": 1,
                "top_offers": [
                    {
                        "id": "kb-through-1",
                        "segments": [
                            {"origin": "SVX", "destination": "IST"},
                            {"origin": "IST", "destination": "CDG"},
                        ],
                    }
                ],
            }
        ]

        def run_primary(*_: object, **__: object) -> list[dict[str, object]]:
            events.append("primary")
            return primary_results

        def dispatch_segment(**_: object) -> list[SegmentProbeOutcome]:
            events.append("segment")
            return [
                SegmentProbeOutcome(
                    summary={"status": "ok", "provider": "kupibilet", "offer_count": 0}
                )
            ]

        with (
            patch(
                "flights_cli.orchestrators.live_route_assembly.build_live_route_segment_plan",
                return_value=plan,
            ),
            patch(
                "flights_cli.orchestrators.live_assembly_runner.build_search_plan",
                return_value=search_plan,
            ),
            patch(
                "flights_cli.orchestrators.live_assembly_runner.run_primary_offer_queries",
                side_effect=run_primary,
            ),
            patch(
                "flights_cli.orchestrators.live_assembly_runner.dispatch_segment_probe",
                side_effect=dispatch_segment,
            ),
            patch(
                "flights_cli.orchestrators.live_assembly_runner.empty_assembled_result",
                return_value={},
            ),
            patch(
                "flights_cli.orchestrators.live_assembly_runner.run_aggregate_controls",
                return_value=[],
            ),
            patch(
                "flights_cli.orchestrators.live_assembly_runner.hub_viability_summary",
                return_value=[],
            ),
        ):
            result = run_live_route_assembly(
                live_args(provider_policy="kupibilet"), Store()
            )

        self.assertEqual(events, ["primary", "segment"])
        self.assertEqual(result["live_search"]["primary_offer_results"], primary_results)
        self.assertEqual(
            result["live_search"]["diagnostics"]["primary_offer_results"],
            primary_results,
        )
        gateway_discovery = result["live_search"]["diagnostics"]["gateway_discovery"]
        self.assertEqual(gateway_discovery["market"], "ru_to_western_europe_bridge")
        self.assertEqual(gateway_discovery["candidates"][0]["code"], "IST")
        self.assertEqual(
            [signal["source"] for signal in gateway_discovery["candidates"][0]["signals"]],
            ["static_prior", "provider_returned_route"],
        )


if __name__ == "__main__":
    unittest.main()
