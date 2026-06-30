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


def minimal_route_plan(destination: str) -> dict[str, object]:
    return {
        "origin": "SVX",
        "destination": destination,
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


def provider_returned_route(destination: str) -> list[dict[str, object]]:
    final_airport = "LHR" if destination == "LON" else destination
    return [
        {
            "role": "primary_offer_collection",
            "source_type": "provider_full_route",
            "provider": "kupibilet",
            "status": "ok",
            "execution_state": "searched",
            "offer_count": 1,
            "top_offers": [
                {
                    "id": f"kb-svx-ist-{destination.lower()}",
                    "segments": [
                        {"origin": "SVX", "destination": "IST"},
                        {"origin": "IST", "destination": final_airport},
                    ],
                }
            ],
        }
    ]


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
        self.assertIn("candidate_count", search_plan["gateway_discovery"])
        self.assertIn("candidates", search_plan["gateway_discovery"])
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
        aggregate_results = [
            {
                "provider": "kupibilet",
                "status": "ok",
                "top_offers": [
                    {
                        "id": "legacy-aggregate-1",
                        "segments": [
                            {"origin": "SVX", "destination": "BEG"},
                            {"origin": "BEG", "destination": "CDG"},
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
                return_value=aggregate_results,
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
        offer_graph = result["live_search"]["diagnostics"]["offer_graph"]
        self.assertEqual(offer_graph["schema_version"], "flight_offer_graph.v1")
        self.assertEqual(
            offer_graph,
            result["live_search"]["offer_graph"],
        )
        self.assertEqual(
            [(edge["origin"], edge["destination"]) for edge in offer_graph["edges"]],
            [("SVX", "IST"), ("IST", "CDG")],
        )
        offer_candidates = result["live_search"]["diagnostics"]["offer_candidates"]
        self.assertEqual(
            offer_candidates,
            result["live_search"]["offer_candidates"],
        )
        self.assertEqual(
            offer_candidates["schema_version"],
            "flight_offer_candidate_envelope.v1",
        )
        self.assertEqual(
            offer_candidates["candidates"][0]["source_type"],
            "provider_full_route",
        )
        self.assertIsNone(offer_candidates["candidates"][0]["price"])
        self.assertIsNone(offer_candidates["candidates"][0]["currency"])
        self.assertEqual(offer_candidates["candidates"][0]["price_basis"], "unknown")
        mixed_ranking = result["live_search"]["diagnostics"]["mixed_candidate_ranking"]
        self.assertEqual(mixed_ranking, result["live_search"]["mixed_candidate_ranking"])
        self.assertEqual(
            mixed_ranking["schema_version"],
            "flight_mixed_candidate_ranking.v1",
        )
        self.assertEqual(mixed_ranking["ranked_candidates"][0]["rank"], 1)
        frontier = result["live_search"]["diagnostics"]["decision_frontier"]
        self.assertEqual(frontier, result["live_search"]["decision_frontier"])
        self.assertEqual(frontier["schema_version"], "flight_decision_frontier.v1")
        self.assertNotIn("rank_components", frontier["options"][0])
        self.assertNotIn("rank_key", frontier["options"][0])
        self.assertIn("gateway_leg_results", result["live_search"])
        self.assertEqual(result["live_search"]["aggregate_controls"], aggregate_results)
        self.assertEqual(
            result["live_search"]["diagnostics"]["primary_offer_results"],
            primary_results,
        )
        gateway_discovery = result["live_search"]["diagnostics"]["gateway_discovery"]
        self.assertEqual(gateway_discovery["market"], "ru_to_western_europe_bridge")
        self.assertEqual(
            [candidate["code"] for candidate in gateway_discovery["candidates"][:2]],
            ["IST", "BEG"],
        )
        self.assertEqual(
            [signal["source"] for signal in gateway_discovery["candidates"][0]["signals"]],
            ["static_prior", "provider_returned_route"],
        )
        search_plan_gateway_discovery = result["live_search"]["diagnostics"][
            "search_plan"
        ]["gateway_discovery"]
        self.assertEqual(
            [candidate["code"] for candidate in search_plan_gateway_discovery["candidates"][:2]],
            ["IST", "BEG"],
        )
        self.assertEqual(search_plan_gateway_discovery["candidate_count"], 3)

    def test_gateway_leg_results_are_returned_as_diagnostics_only(self) -> None:
        plan = minimal_route_plan("AMS")
        search_plan = {
            "schema_version": "flight_search_plan.v1",
            "primary_offer_queries": [],
            "mandatory_controls": [],
            "gateway_discovery": {
                "enabled": True,
                "reason": "route_access_profile_requires_gateway_discovery",
                "mode": "required",
                "route_access_profile": "restricted_access_market",
                "route_access_reasons": [],
                "candidate_count": 1,
                "candidates": [],
                "skipped_reasons": [],
                "empty_reason": None,
            },
            "gateway_leg_queries": [
                *[
                    {
                        "role": "gateway_leg_probe",
                        "source_type": "gateway_discovery_candidate",
                        "probe_type": "segment_direct",
                        "direction": "outbound",
                        "leg": leg,
                        "origin": origin,
                        "destination": destination,
                        "date": "2026-08-16",
                        "currency": "RUB",
                        "direct_only": True,
                        "gateway": "IST",
                        "gateway_rank": 1,
                        "provider": provider,
                        "execution_state": "not_executed",
                    }
                    for leg, origin, destination, provider in (
                        ("origin_to_gateway", "SVX", "IST", "kupibilet"),
                        ("gateway_to_destination", "IST", "AMS", "fli"),
                    )
                ]
            ],
            "fallback_segment_plan": {"segments": []},
            "coverage_expectations": [],
        }

        def dispatch_gateway(**kwargs: object) -> list[SegmentProbeOutcome]:
            spec = kwargs["spec"]
            return [
                SegmentProbeOutcome(
                    summary={
                        "status": "ok",
                        "provider": spec["provider"],
                        "offer_count": 1,
                        "cache_status": "disabled",
                    },
                    segment_result={
                        "direction": spec["direction"],
                        "leg": spec["leg"],
                        "offers": [{"id": f"{spec['origin']}-{spec['destination']}"}],
                    },
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
                "flights_cli.execution.gateway_leg_probe_executor.dispatch_segment_probe",
                side_effect=dispatch_gateway,
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
            result = run_live_route_assembly(live_args(destination="AMS"), Store())

        gateway_results = result["live_search"]["gateway_leg_results"]
        self.assertEqual(gateway_results["searched_gateways"], 1)
        self.assertEqual(gateway_results["viable_gateways"], 1)
        self.assertEqual(
            result["live_search"]["diagnostics"]["gateway_leg_results"],
            gateway_results,
        )
        offer_graph = result["live_search"]["diagnostics"]["offer_graph"]
        self.assertEqual(offer_graph["schema_version"], "flight_offer_graph.v1")
        self.assertEqual(offer_graph, result["live_search"]["offer_graph"])
        self.assertEqual(len(offer_graph["edges"]), 2)
        self.assertEqual(len(offer_graph["connections"]), 1)
        offer_candidates = result["live_search"]["diagnostics"]["offer_candidates"]
        self.assertEqual(offer_candidates, result["live_search"]["offer_candidates"])
        self.assertEqual(
            offer_candidates["candidates"][0]["source_type"],
            "gateway_separate_ticket",
        )
        mixed_ranking = result["live_search"]["diagnostics"]["mixed_candidate_ranking"]
        self.assertEqual(mixed_ranking, result["live_search"]["mixed_candidate_ranking"])
        self.assertEqual(
            mixed_ranking["ranked_candidates"][0]["source_type"],
            "gateway_separate_ticket",
        )
        self.assertEqual(result.get("segment_results"), [])

    def test_restricted_route_discovery_does_not_leak_raw_diagnostics_to_rendered_text(
        self,
    ) -> None:
        for destination in ("AMS", "FRA", "LON"):
            with self.subTest(destination=destination):
                plan = minimal_route_plan(destination)
                route_results = provider_returned_route(destination)

                def run_with_primary(
                    primary_results: list[dict[str, object]],
                ) -> dict[str, object]:
                    with (
                        patch(
                            "flights_cli.orchestrators.live_route_assembly.build_live_route_segment_plan",
                            return_value=plan,
                        ),
                        patch(
                            "flights_cli.orchestrators.live_assembly_runner.run_primary_offer_queries",
                            return_value=primary_results,
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
                        return run_live_route_assembly(
                            live_args(destination=destination, agent_report=True),
                            Store(),
                        )

                baseline = run_with_primary([])
                with_provider_route = run_with_primary(route_results)

                search_plan = with_provider_route["live_search"]["diagnostics"][
                    "search_plan"
                ]
                gateway_plan = search_plan["gateway_discovery"]
                self.assertEqual(
                    gateway_plan["route_access_profile"], "restricted_access_market"
                )
                self.assertEqual(gateway_plan["mode"], "required")
                self.assertEqual(gateway_plan["prior_set"], "restricted_bridge_gateways")
                self.assertEqual(gateway_plan["market"], "restricted_bridge_gateways")

                gateway_diagnostics = with_provider_route["live_search"][
                    "diagnostics"
                ]["gateway_discovery"]
                self.assertEqual(gateway_diagnostics["market"], "restricted_bridge_gateways")
                candidates = gateway_plan["candidates"]
                self.assertEqual(gateway_plan["candidate_count"], len(candidates))
                self.assertEqual(candidates[0]["code"], "IST")
                self.assertEqual(
                    [signal["source"] for signal in candidates[0]["signals"]],
                    ["static_prior", "provider_returned_route"],
                )
                self.assertEqual(candidates[0]["signals"][1]["provider"], "kupibilet")
                self.assertEqual(
                    candidates[0]["signals"][1]["offer_id"],
                    f"kb-svx-ist-{destination.lower()}",
                )
                self.assertTrue(
                    any(candidate["code"] == "DXB" for candidate in candidates)
                )
                self.assertEqual(gateway_plan["skipped_reasons"], [])
                self.assertIsNone(gateway_plan["empty_reason"])

                baseline_text = baseline["agent_report"]["user_answer"][
                    "rendered_text"
                ]
                with_provider_text = with_provider_route["agent_report"][
                    "user_answer"
                ]["rendered_text"]
                self.assertTrue(baseline_text)
                self.assertIn("Проверил 1 gateway: IST.", baseline_text)
                self.assertIn(
                    "Проверил KupiBilet по всему маршруту и 1 gateway: IST.",
                    with_provider_text,
                )
                self.assertNotIn("provider_returned_route", with_provider_text)
                self.assertNotIn("restricted_bridge_gateways", with_provider_text)


if __name__ == "__main__":
    unittest.main()
