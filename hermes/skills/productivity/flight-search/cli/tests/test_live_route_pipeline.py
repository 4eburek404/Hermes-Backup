from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from flights_cli.config import DEFAULT_DIRECT_CATALOG_LIMIT
from flights_cli.execution.probe_dispatcher import SegmentProbeOutcome
from flights_cli.orchestrators.live_assembly_runner import _direct_evidence_by_direction
from flights_cli.orchestrators.live_route_assembly import run_live_route_assembly
from flights_cli.pipeline.search_pipeline import build_live_route_search_flow
from flights_cli.services.agent_report import build_validated_agent_report
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
        "aggregate_control_limit": 0,
        "coverage_mode": "targeted",
        "coverage_control_limit": 12,
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


def count_key(payload: object, key: str) -> int:
    if isinstance(payload, dict):
        return sum(
            (1 if item_key == key else 0) + count_key(value, key)
            for item_key, value in payload.items()
        )
    if isinstance(payload, list):
        return sum(count_key(item, key) for item in payload)
    return 0


class LiveRoutePipelineTests(unittest.TestCase):
    def test_direct_evidence_uses_round_trip_journey_directions(self) -> None:
        plan = minimal_route_plan("LED")
        plan["dates"] = {"depart": "2026-09-05", "return": "2026-09-12"}
        primary_results = [
            {
                "role": "primary_offer_collection",
                "source_type": "provider_full_route",
                "provider": "tutu",
                "direction": "outbound",
                "origin": "SVX",
                "destination": "LED",
                "top_offers": [
                    {
                        "id": "tutu-rt-1",
                        "segments": [{"origin": "SVX", "destination": "LED"}],
                        "journeys": [
                            {
                                "direction": "outbound",
                                "segments": [{"origin": "SVX", "destination": "LED"}],
                            },
                            {
                                "direction": "return",
                                "segments": [{"origin": "LED", "destination": "SVX"}],
                            },
                        ],
                    }
                ],
            }
        ]

        self.assertEqual(
            _direct_evidence_by_direction(plan, primary_results),
            {"outbound": True, "return": True},
        )

    def test_live_route_args_adapt_to_typed_search_flow(self) -> None:
        args = live_assembly_args(
            origin="SVX",
            destination="CDG",
            depart_date="2026-08-16",
            return_date="2026-08-20",
            profile="business",
            no_live_cache=True,
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
        self.assertEqual(flow.evidence_plan.max_segment_searches, 300)

    def test_live_assembly_runner_uses_typed_flow_without_public_report_shape_change(
        self,
    ) -> None:
        with (
            patch(
                "flights_cli.orchestrators.live_assembly_runner.build_live_route_search_flow",
                wraps=build_live_route_search_flow,
            ) as build_flow,
            patch(
                "flights_cli.orchestrators.live_assembly_runner.run_primary_offer_queries",
                return_value=[],
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
        route_plan = result["live_search"]["plan"]
        self.assertEqual(route_plan["origin"], "SVX")
        self.assertEqual(route_plan["destination"], "CDG")
        self.assertEqual(route_plan["dates"], {"depart": "2026-08-16", "return": None})
        self.assertEqual(route_plan["segments"], [])
        search_plan = result["live_search"]["diagnostics"]["search_plan"]
        self.assertEqual(
            set(result["live_search"]["diagnostics"]),
            {"search_plan", "wave_diagnostics"},
        )
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

    def test_primary_offer_queries_execute_before_frontier_scoring(self) -> None:
        events: list[str] = []
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
                    "limit": DEFAULT_DIRECT_CATALOG_LIMIT,
                    "route_family": "ru_to_western_europe_bridge",
                }
            ],
            "mandatory_controls": [],
            "gateway_discovery": {"enabled": False, "reason": None},
            "gateway_leg_queries": [],
            "fallback_segment_plan": {"segments": []},
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
                        "id": "aggregate-1",
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

        with (
            patch(
                "flights_cli.orchestrators.live_assembly_runner.build_search_plan",
                return_value=search_plan,
            ),
            patch(
                "flights_cli.orchestrators.live_assembly_runner.run_primary_offer_queries",
                side_effect=run_primary,
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

        self.assertEqual(events, ["primary"])
        self.assertEqual(
            result["live_search"]["primary_offer_results"], primary_results
        )
        offer_graph = result["live_search"]["offer_graph"]
        self.assertEqual(offer_graph["schema_version"], "flight_offer_graph.v1")
        self.assertEqual(
            [(edge["origin"], edge["destination"]) for edge in offer_graph["edges"]],
            [("SVX", "IST"), ("IST", "CDG")],
        )
        mixed_ranking = result["live_search"]["mixed_candidate_ranking"]
        self.assertEqual(
            mixed_ranking["schema_version"],
            "flight_mixed_candidate_ranking.v1",
        )
        self.assertEqual(mixed_ranking["ranked_candidates"][0]["rank"], 1)
        self.assertEqual(
            set(result["live_search"]["candidate_input_ids"]),
            {candidate["id"] for candidate in mixed_ranking["ranked_candidates"]},
        )
        self.assertEqual(
            mixed_ranking["ranked_candidates"][0]["source_type"],
            "provider_full_route",
        )
        self.assertIsNone(mixed_ranking["ranked_candidates"][0]["price"])
        self.assertIsNone(mixed_ranking["ranked_candidates"][0]["currency"])
        self.assertEqual(
            mixed_ranking["ranked_candidates"][0]["price_basis"], "unknown"
        )
        frontier = result["decision_frontier"]
        self.assertEqual(frontier["schema_version"], "flight_decision_frontier.v1")
        self.assertNotIn("rank_components", frontier["options"][0])
        self.assertNotIn("rank_key", frontier["options"][0])
        self.assertNotIn("decision_frontier", result["live_search"])
        self.assertIn("gateway_leg_results", result["live_search"])
        self.assertEqual(result["live_search"]["aggregate_controls"], aggregate_results)
        self.assertEqual(
            set(result["live_search"]["diagnostics"]),
            {"search_plan", "wave_diagnostics"},
        )
        self.assertEqual(
            result["live_search"]["primary_offer_results"],
            primary_results,
        )
        search_plan_gateway_discovery = result["live_search"]["diagnostics"][
            "search_plan"
        ]["gateway_discovery"]
        self.assertEqual(
            search_plan_gateway_discovery["market"], "ru_to_western_europe_bridge"
        )
        self.assertEqual(
            [
                candidate["code"]
                for candidate in search_plan_gateway_discovery["candidates"][:2]
            ],
            ["IST", "BEG"],
        )
        self.assertEqual(
            [
                signal["source"]
                for signal in search_plan_gateway_discovery["candidates"][0]["signals"]
            ],
            ["static_prior", "provider_returned_route"],
        )
        self.assertEqual(
            [
                candidate["code"]
                for candidate in search_plan_gateway_discovery["candidates"][:2]
            ],
            ["IST", "BEG"],
        )
        self.assertEqual(search_plan_gateway_discovery["candidate_count"], 3)

    def test_direct_presence_gate_skips_gateway_queries_after_wave0_evidence(
        self,
    ) -> None:
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
                    "limit": DEFAULT_DIRECT_CATALOG_LIMIT,
                }
            ],
            "mandatory_controls": [],
            "gateway_discovery": {"enabled": True, "reason": "fixture"},
            "gateway_leg_queries": [
                {
                    "role": "gateway_leg_probe",
                    "source_type": "gateway_discovery_candidate",
                    "probe_type": "segment_hub_leg",
                    "direction": "outbound",
                    "leg": "origin_to_gateway",
                    "origin": "SVX",
                    "destination": "IST",
                    "date": "2026-08-16",
                    "currency": "RUB",
                    "direct_only": False,
                    "gateway": "IST",
                    "provider": "kupibilet",
                    "execution_state": "not_executed",
                }
            ],
            "fallback_segment_plan": {"segments": []},
            "coverage_expectations": [],
        }
        primary_results = [
            {
                "role": "primary_offer_collection",
                "source_type": "provider_full_route",
                "provider": "kupibilet",
                "direction": "outbound",
                "origin": "SVX",
                "destination": "CDG",
                "status": "ok",
                "execution_state": "searched",
                "offer_count": 1,
                "top_offers": [
                    {
                        "id": "kb-direct",
                        "price": 22000,
                        "currency": "RUB",
                        "segments": [{"origin": "SVX", "destination": "CDG"}],
                    }
                ],
            }
        ]

        with (
            patch(
                "flights_cli.orchestrators.live_assembly_runner.build_search_plan",
                return_value=search_plan,
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
                "flights_cli.orchestrators.live_assembly_runner.SearchWavePlanner.run",
                return_value={
                    "searched_gateways": 0,
                    "viable_gateways": 0,
                    "failed_gateways": 0,
                    "not_searched_budget": 0,
                    "gateways": [],
                    "wave_diagnostics": {
                        "schema_version": "flight_search_wave_diagnostics.v1",
                        "stop_reason": "no_gateway_leg_queries",
                    },
                },
            ) as wave_run,
            patch(
                "flights_cli.orchestrators.live_assembly_runner.hub_viability_summary",
                return_value=[],
            ),
        ):
            result = run_live_route_assembly(
                live_args(provider_policy="kupibilet"), Store()
            )

        wave_run.assert_called_once()
        self.assertEqual(wave_run.call_args.args[0], [])
        gate = result["live_search"]["direct_presence_gate"]
        self.assertEqual(gate["direct_evidence_present"], {"outbound": True})
        self.assertEqual(gate["direct_mode"], {"outbound": True})
        self.assertEqual(gate["skipped_gateway_probe_count"], 1)
        skipped = result["live_search"]["probe_ledger"]["skipped_controls"]
        self.assertTrue(any(item.get("reason") == "direct_mode" for item in skipped))

    def test_live_search_payload_is_deduplicated(self) -> None:
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
                    "limit": DEFAULT_DIRECT_CATALOG_LIMIT,
                }
            ],
            "mandatory_controls": [],
            "gateway_discovery": {"enabled": False, "reason": None},
            "gateway_leg_queries": [],
            "fallback_segment_plan": {"segments": []},
            "coverage_expectations": [],
        }

        with (
            patch(
                "flights_cli.orchestrators.live_assembly_runner.build_search_plan",
                return_value=search_plan,
            ),
            patch(
                "flights_cli.orchestrators.live_assembly_runner.run_primary_offer_queries",
                return_value=provider_returned_route("CDG"),
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

        serialized = json.dumps(result, sort_keys=True, separators=(",", ":"))
        self.assertLess(len(serialized.encode("utf-8")), 80_000)
        self.assertEqual(result["schema_version"], "flight_route_trace_diagnostic.v1")
        self.assertEqual(count_key(result, "decision_frontier"), 1)
        self.assertIn("decision_frontier", result)
        self.assertNotIn("decision_frontier", result["live_search"])
        self.assertEqual(
            set(result["live_search"]["diagnostics"]),
            {"search_plan", "wave_diagnostics"},
        )

    def test_route_connection_options_flow_into_decision_scorer(self) -> None:
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
                    "limit": DEFAULT_DIRECT_CATALOG_LIMIT,
                }
            ],
            "mandatory_controls": [],
            "gateway_discovery": {"enabled": False, "reason": None},
            "gateway_leg_queries": [],
            "fallback_segment_plan": {"segments": []},
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
                        "id": "kb-two-connection",
                        "segments": [
                            {"origin": "SVX", "destination": "IST"},
                            {"origin": "IST", "destination": "AMS"},
                            {"origin": "AMS", "destination": "CDG"},
                        ],
                    }
                ],
            }
        ]

        with (
            patch(
                "flights_cli.orchestrators.live_assembly_runner.build_search_plan",
                return_value=search_plan,
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
            result = run_live_route_assembly(
                live_args(
                    provider_policy="kupibilet",
                    max_connections=1,
                    tier2_max_connections=2,
                ),
                Store(),
            )

        coverage = result["live_search"]["mixed_candidate_ranking"]["coverage"]
        ranked = result["live_search"]["mixed_candidate_ranking"]["ranked_candidates"][
            0
        ]
        self.assertEqual(coverage["max_connections_per_journey"], 2)
        self.assertEqual(coverage["preferred_connections_per_journey"], 1)
        self.assertEqual(ranked["rank_components"]["max_connections_per_journey"], 0)
        self.assertEqual(
            ranked["rank_components"]["preferred_connections_per_journey"], 1
        )

    def test_gateway_leg_results_are_returned_top_level_only(self) -> None:
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
            set(result["live_search"]["diagnostics"]),
            {"search_plan", "wave_diagnostics"},
        )
        offer_graph = result["live_search"]["offer_graph"]
        self.assertEqual(offer_graph["schema_version"], "flight_offer_graph.v1")
        self.assertEqual(len(offer_graph["edges"]), 2)
        self.assertEqual(len(offer_graph["connections"]), 1)
        mixed_ranking = result["live_search"]["mixed_candidate_ranking"]
        self.assertEqual(
            mixed_ranking["ranked_candidates"][0]["source_type"],
            "gateway_separate_ticket",
        )
        self.assertEqual(
            set(result["live_search"]["candidate_input_ids"]),
            {candidate["id"] for candidate in mixed_ranking["ranked_candidates"]},
        )

    def test_restricted_route_discovery_does_not_leak_raw_diagnostics_to_rendered_text(
        self,
    ) -> None:
        for destination in ("AMS", "FRA", "LON"):
            with self.subTest(destination=destination):
                plan = minimal_route_plan(destination)
                provider_results = provider_returned_route(destination)

                def run_with_primary(
                    primary_results: list[dict[str, object]],
                ) -> dict[str, object]:
                    gateway_leg_results = {
                        "searched_gateways": 1,
                        "viable_gateways": 0,
                        "failed_gateways": 0,
                        "gateways": [
                            {
                                "gateway": "IST",
                                "searched": True,
                                "viable": False,
                                "origin_leg": {"provider": "tutu", "offer_count": 0},
                                "destination_leg": {
                                    "provider": "fli",
                                    "offer_count": 0,
                                },
                            }
                        ],
                    }
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
                            "flights_cli.orchestrators.live_assembly_runner.SearchWavePlanner.run",
                            return_value=gateway_leg_results,
                        ),
                        patch(
                            "flights_cli.orchestrators.live_assembly_runner.hub_viability_summary",
                            return_value=[],
                        ),
                    ):
                        return run_live_route_assembly(
                            live_args(destination=destination),
                            Store(),
                        )

                baseline = run_with_primary([])
                with_provider_route = run_with_primary(provider_results)
                baseline_report = build_validated_agent_report(baseline, Store())
                provider_route_report = build_validated_agent_report(
                    with_provider_route, Store()
                )

                search_plan = with_provider_route["live_search"]["diagnostics"][
                    "search_plan"
                ]
                gateway_plan = search_plan["gateway_discovery"]
                self.assertEqual(
                    gateway_plan["route_access_profile"], "restricted_access_market"
                )
                self.assertEqual(gateway_plan["mode"], "required")
                self.assertEqual(
                    gateway_plan["prior_set"], "restricted_bridge_gateways"
                )
                self.assertEqual(gateway_plan["market"], "restricted_bridge_gateways")
                self.assertEqual(
                    set(with_provider_route["live_search"]["diagnostics"]),
                    {"search_plan", "wave_diagnostics"},
                )
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

                self.assertEqual(
                    set(baseline_report["frontier"]), {"decision_frontier"}
                )
                self.assertEqual(
                    set(provider_route_report["frontier"]),
                    {"decision_frontier"},
                )


if __name__ == "__main__":
    unittest.main()
