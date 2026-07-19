from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from flights_cli.config import DEFAULT_DIRECT_CATALOG_LIMIT
from flights_cli.execution.probe_dispatcher import SegmentProbeOutcome
from flights_cli.orchestrators.search_workflow import SearchWorkflow
from flights_cli.orchestrators.search_plan_builder import (
    build_planning_state,
    build_route_context,
)
from flights_cli.pipeline.result_builder import build_result_projection
from flights_cli.pipeline.direct_gate import direct_evidence_by_direction
from flights_cli.pipeline.search_plan import (
    DecisionPolicy,
    ExecutionPolicy,
    GatewayDiscovery,
    GatewayPolicy,
    OutputPolicy,
    ProviderAttemptPlan,
    RoutePlan,
    SearchPhases,
    SearchPlan,
)
from flights_cli.store import Store
from helpers import live_assembly_args


def execute_projection(*args: object, **kwargs: object) -> dict:
    request, store = args
    return SearchWorkflow(store).run_artifacts(request).projection_input


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
        "provider_policy": "auto",
        "routing_strategy": "auto",
        "route_mode": "hub_list",
        "market_class": "global_non_ru",
        "hubs": [],
        "route_families": [],
        "origin_airports": ["SVX"],
        "destination_airports": [destination],
        "airport_scope": None,
        "direct_only": False,
    }


def execution_limits() -> dict[str, object]:
    return {
        "max_segment_searches": 10,
        "segment_limit": 30,
        "live_cache_ttl_seconds": 0,
        "live_cache_enabled": False,
        "timeout": 60,
        "fail_fast": False,
    }


def typed_plan(legacy: dict[str, object]) -> SearchPlan:
    route = RoutePlan.from_dict(legacy["route_context"])  # type: ignore[arg-type]
    primary = tuple(
        ProviderAttemptPlan(
            probe_id=f"primary-{index:03d}",
            phase="primary",
            trigger="always" if query.get("direct_only") else "no_direct",
            provider=str(query.get("provider") or ""),
            probe_type=str(query.get("probe_type") or "full_route_aggregate"),
            direction=str(query.get("direction") or "outbound"),
            query={
                key: value
                for key, value in query.items()
                if key not in {"provider", "probe_type", "direction", "execution_state"}
            },
        )
        for index, query in enumerate(legacy.get("primary_offer_queries") or [], 1)
    )
    gateway = tuple(
        ProviderAttemptPlan(
            probe_id=f"gateway-{index:03d}",
            phase="gateway",
            trigger="required_if_no_direct",
            provider=str(query.get("provider") or ""),
            probe_type=str(query.get("probe_type") or "segment_direct"),
            direction=str(query.get("direction") or "outbound"),
            query={
                key: value
                for key, value in query.items()
                if key not in {"provider", "probe_type", "direction", "execution_state"}
            },
        )
        for index, query in enumerate(
            legacy.get("conditional_gateway_queries") or [], 1
        )
    )
    limits = dict(legacy.get("execution_limits") or {})
    discovery_payload = dict(legacy.get("gateway_discovery") or {})
    discovery = GatewayDiscovery.from_dict(discovery_payload)
    trigger = "required_if_no_direct" if discovery.enabled else "disabled"
    return SearchPlan(
        route=route,
        phases=SearchPhases(primary=primary, gateway=gateway),
        gateway_policy=GatewayPolicy(trigger=trigger, discovery=discovery),
        execution_policy=ExecutionPolicy(
            max_provider_attempts=int(limits.get("max_segment_searches") or 10),
            segment_limit=int(limits.get("segment_limit") or 30),
            live_cache_ttl_seconds=int(limits.get("live_cache_ttl_seconds") or 0),
            live_cache_enabled=bool(limits.get("live_cache_enabled")),
            timeout=int(limits.get("timeout") or 60),
            fail_fast=bool(limits.get("fail_fast")),
            gateway_discovery_limit=10,
            gateway_probe_batch_size=10,
            gateway_probe_max_batches=1,
        ),
        decision_policy=DecisionPolicy(
            max_connections_per_journey=2,
            preferred_connections=1,
            min_same_airport_connection_min=120,
            min_cross_airport_connection_min=300,
            max_layover_min=1440,
            preferred_layover_max_min=360,
        ),
        output_policy=OutputPolicy(
            catalog_limit=10,
            direct_catalog_limit=DEFAULT_DIRECT_CATALOG_LIMIT,
            max_gateway_alternatives=2,
            max_primary_gateway_options=4,
            max_options_per_first_carrier=2,
            max_round_trip_pairs=12,
        ),
    )


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
                        "segments": [
                            {
                                "origin": "SVX",
                                "destination": "LED",
                                "departure_at": "2026-09-05T10:00:00+05:00",
                                "arrival_at": "2026-09-05T12:30:00+03:00",
                            }
                        ],
                        "journeys": [
                            {
                                "direction": "outbound",
                                "segments": [
                                    {
                                        "origin": "SVX",
                                        "destination": "LED",
                                        "departure_at": "2026-09-05T10:00:00+05:00",
                                        "arrival_at": "2026-09-05T12:30:00+03:00",
                                    }
                                ],
                            },
                            {
                                "direction": "return",
                                "segments": [
                                    {
                                        "origin": "LED",
                                        "destination": "SVX",
                                        "departure_at": "2026-09-12T10:00:00+03:00",
                                        "arrival_at": "2026-09-12T14:30:00+05:00",
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ]

        self.assertEqual(
            direct_evidence_by_direction(plan, primary_results),
            {"outbound": True, "return": True},
        )

    def test_direct_evidence_rejects_impossible_segment_chronology(self) -> None:
        plan = minimal_route_plan("LED")
        primary_results = [
            {
                "direction": "outbound",
                "origin": "SVX",
                "destination": "LED",
                "execution_state": "searched",
                "top_offers": [
                    {
                        "segments": [
                            {
                                "origin": "SVX",
                                "destination": "LED",
                                "departure_at": "2026-09-05T12:00:00+05:00",
                                "arrival_at": "2026-09-05T11:00:00+05:00",
                                "carrier": "SU",
                            }
                        ]
                    }
                ],
            }
        ]

        self.assertEqual(
            direct_evidence_by_direction(plan, primary_results),
            {"outbound": False},
        )

    def test_direct_evidence_rejects_missing_segment_timing(self) -> None:
        plan = minimal_route_plan("LED")
        primary_results = [
            {
                "direction": "outbound",
                "execution_state": "searched",
                "top_offers": [
                    {
                        "segments": [
                            {
                                "origin": "SVX",
                                "destination": "LED",
                                "departure_at": "2026-08-16T08:00:00+05:00",
                                "arrival_at": None,
                                "carrier": "SU",
                            }
                        ]
                    }
                ],
            }
        ]

        self.assertEqual(
            direct_evidence_by_direction(plan, primary_results),
            {"outbound": False},
        )

    def test_direct_evidence_rejects_offer_outside_planned_date(self) -> None:
        plan = minimal_route_plan("LED")
        primary_results = [
            {
                "direction": "outbound",
                "execution_state": "searched",
                "top_offers": [
                    {
                        "segments": [
                            {
                                "origin": "SVX",
                                "destination": "LED",
                                "departure_at": "2026-08-17T10:00:00+05:00",
                                "arrival_at": "2026-08-17T12:30:00+03:00",
                            }
                        ]
                    }
                ],
            }
        ]

        self.assertEqual(
            direct_evidence_by_direction(plan, primary_results),
            {"outbound": False},
        )

    def test_direct_evidence_enforces_planned_carrier_scope(self) -> None:
        plan = minimal_route_plan("LED")
        primary_results = [
            {
                "direction": "outbound",
                "origin": "SVX",
                "destination": "LED",
                "execution_state": "searched",
                "top_offers": [
                    {
                        "segments": [
                            {
                                "origin": "SVX",
                                "destination": "LED",
                                "carrier": "DP",
                            }
                        ]
                    }
                ],
            }
        ]

        self.assertEqual(
            direct_evidence_by_direction(plan, primary_results, only_carriers=("SU",)),
            {"outbound": False},
        )

    def test_direct_evidence_does_not_expand_scope_from_provider_result(self) -> None:
        plan = minimal_route_plan("LED")
        primary_results = [
            {
                "direction": "outbound",
                "origin": "KZN",
                "destination": "LED",
                "execution_state": "searched",
                "top_offers": [
                    {
                        "segments": [
                            {"origin": "KZN", "destination": "LED", "carrier": "SU"}
                        ]
                    }
                ],
            }
        ]

        self.assertEqual(
            direct_evidence_by_direction(plan, primary_results),
            {"outbound": False},
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

        flow = build_planning_state(args)

        self.assertEqual(flow.request.origin, "SVX")
        self.assertEqual(flow.request.destination, "CDG")
        self.assertEqual(flow.request.depart_date, "2026-08-16")
        self.assertEqual(flow.request.return_date, "2026-08-20")
        self.assertEqual(flow.request.currency, "RUB")
        self.assertEqual(flow.request.profile, "business")
        self.assertEqual(flow.request.provider_policy, "auto")
        self.assertIs(flow.request, args)
        with self.assertRaises(AttributeError):
            flow.request.route.origin = "LED"
        self.assertEqual(flow.flow_decision.market_class, "ru_touching_international")
        self.assertEqual(flow.flow_decision.routing_strategy, "ru-priority")
        self.assertEqual(flow.request.max_segment_searches, 300)

    def test_search_executor_uses_typed_request(
        self,
    ) -> None:
        with (
            patch(
                "flights_cli.orchestrators.search_plan_builder.build_planning_state",
                wraps=build_planning_state,
            ) as build_flow,
            patch(
                "flights_cli.execution.search_executor.run_primary_offer_queries",
                return_value=[],
            ),
        ):
            result = execute_projection(live_args(), Store())

        self.assertEqual(build_flow.call_count, 1)
        self.assertIn("live_search", result)
        self.assertEqual(result["live_search"]["provider_policy"], "auto")
        route_plan = result["live_search"]["plan"]
        self.assertEqual(route_plan["origin"], "SVX")
        self.assertEqual(route_plan["destination"], "CDG")
        self.assertEqual(route_plan["dates"], {"depart": "2026-08-16", "return": None})
        search_plan = result["live_search"]["diagnostics"]["search_plan"]
        self.assertEqual(
            set(result["live_search"]["diagnostics"]),
            {"search_plan", "observed_gateway_diagnostics"},
        )
        self.assertEqual(search_plan["schema_version"], "flight_search_plan.v5")
        discovery = search_plan["gateway_policy"]["discovery"]
        self.assertIn("candidate_count", discovery)
        self.assertIn("candidates", discovery)
        self.assertEqual(result["live_search"]["segment_searches"], [])
        self.assertNotIn("flow_decision", result)
        self.assertNotIn("search_request", result)
        self.assertNotIn("flow_decision", result["live_search"])
        self.assertNotIn("search_request", result["live_search"])

    def test_primary_offer_queries_execute_before_frontier_scoring(self) -> None:
        events: list[str] = []
        search_plan = {
            "execution_limits": execution_limits(),
            "route_context": minimal_route_plan("CDG"),
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
            "gateway_discovery": {"enabled": False, "reason": None},
            "conditional_gateway_queries": [],
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
                            {
                                "origin": "SVX",
                                "destination": "IST",
                                "departure_at": "2026-08-16T08:00:00+05:00",
                                "arrival_at": "2026-08-16T10:30:00+03:00",
                            },
                            {
                                "origin": "IST",
                                "destination": "CDG",
                                "departure_at": "2026-08-16T13:00:00+03:00",
                                "arrival_at": "2026-08-16T15:30:00+02:00",
                            },
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
                "flights_cli.orchestrators.search_workflow.SearchWorkflow.plan",
                return_value=typed_plan(search_plan),
            ),
            patch(
                "flights_cli.execution.search_executor.run_primary_offer_queries",
                side_effect=run_primary,
            ),
        ):
            result = execute_projection(live_args(provider_policy="kupibilet"), Store())

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
        self.assertEqual(
            set(result["live_search"]["diagnostics"]),
            {"search_plan", "observed_gateway_diagnostics"},
        )
        self.assertEqual(
            result["live_search"]["primary_offer_results"],
            primary_results,
        )
        observed_gateway_discovery = result["live_search"]["diagnostics"][
            "observed_gateway_diagnostics"
        ]
        self.assertEqual(
            observed_gateway_discovery["market"], "ru_to_western_europe_bridge"
        )
        self.assertEqual(
            [
                candidate["code"]
                for candidate in observed_gateway_discovery["candidates"][:2]
            ],
            ["IST", "DXB"],
        )
        self.assertEqual(
            [
                signal["source"]
                for signal in observed_gateway_discovery["candidates"][0]["signals"]
            ],
            ["static_prior", "provider_returned_route"],
        )
        self.assertEqual(observed_gateway_discovery["candidate_count"], 2)

    def test_direct_presence_gate_skips_gateway_queries_after_direct_evidence(
        self,
    ) -> None:
        search_plan = {
            "execution_limits": execution_limits(),
            "route_context": minimal_route_plan("CDG"),
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
            "gateway_discovery": {
                "enabled": True,
                "reason": "fixture",
                "mode": "optional_after_provider_failure",
            },
            "conditional_gateway_queries": [
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
                        "segments": [
                            {
                                "origin": "SVX",
                                "destination": "CDG",
                                "departure_at": "2026-08-16T10:00:00+05:00",
                                "arrival_at": "2026-08-16T12:00:00+02:00",
                            }
                        ],
                    }
                ],
            }
        ]

        with (
            patch(
                "flights_cli.orchestrators.search_workflow.SearchWorkflow.plan",
                return_value=typed_plan(search_plan),
            ),
            patch(
                "flights_cli.execution.search_executor.run_primary_offer_queries",
                return_value=primary_results,
            ),
        ):
            result = execute_projection(live_args(provider_policy="kupibilet"), Store())

        gate = result["live_search"]["direct_presence_gate"]
        self.assertEqual(gate["direct_evidence_present"], {"outbound": True})
        self.assertEqual(gate["direct_mode"], {"outbound": True})
        self.assertEqual(gate["skipped_gateway_probe_count"], 1)
        skipped = result["live_search"]["probe_ledger"]["skipped_probes"]
        self.assertTrue(
            any(item.get("reason") == "direct_available" for item in skipped)
        )

    def test_live_search_payload_is_deduplicated(self) -> None:
        search_plan = {
            "execution_limits": execution_limits(),
            "route_context": minimal_route_plan("CDG"),
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
            "gateway_discovery": {"enabled": False, "reason": None},
            "conditional_gateway_queries": [],
            "coverage_expectations": [],
        }

        with (
            patch(
                "flights_cli.orchestrators.search_workflow.SearchWorkflow.plan",
                return_value=typed_plan(search_plan),
            ),
            patch(
                "flights_cli.execution.search_executor.run_primary_offer_queries",
                return_value=provider_returned_route("CDG"),
            ),
        ):
            result = execute_projection(live_args(provider_policy="kupibilet"), Store())

        serialized = json.dumps(result, sort_keys=True, separators=(",", ":"))
        self.assertLess(len(serialized.encode("utf-8")), 80_000)
        self.assertEqual(
            result["schema_version"], "flight_decision_projection_input.v1"
        )
        self.assertEqual(count_key(result, "decision_frontier"), 1)
        self.assertIn("decision_frontier", result)
        self.assertNotIn("decision_frontier", result["live_search"])
        self.assertEqual(
            set(result["live_search"]["diagnostics"]),
            {"search_plan", "observed_gateway_diagnostics"},
        )

    def test_route_connection_options_flow_into_decision_scorer(self) -> None:
        search_plan = {
            "execution_limits": execution_limits(),
            "route_context": build_route_context(
                live_args(
                    provider_policy="kupibilet",
                    max_connections=1,
                    tier2_max_connections=2,
                ),
                Store(),
            ),
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
            "gateway_discovery": {"enabled": False, "reason": None},
            "conditional_gateway_queries": [],
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
                "flights_cli.orchestrators.search_workflow.SearchWorkflow.plan",
                return_value=typed_plan(search_plan),
            ),
            patch(
                "flights_cli.execution.search_executor.run_primary_offer_queries",
                return_value=primary_results,
            ),
        ):
            result = execute_projection(
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
            "execution_limits": execution_limits(),
            "route_context": minimal_route_plan("AMS"),
            "primary_offer_queries": [],
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
            "conditional_gateway_queries": [
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
                        ("gateway_to_destination", "IST", "AMS", "tutu"),
                    )
                ]
            ],
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
                "flights_cli.orchestrators.search_plan_builder.build_route_context",
                return_value=plan,
            ),
            patch(
                "flights_cli.orchestrators.search_workflow.SearchWorkflow.plan",
                return_value=typed_plan(search_plan),
            ),
            patch(
                "flights_cli.execution.gateway_leg_probe_executor.dispatch_segment_probe",
                side_effect=dispatch_gateway,
            ),
        ):
            result = execute_projection(live_args(destination="AMS"), Store())

        gateway_results = result["live_search"]["gateway_leg_results"]
        self.assertEqual(gateway_results["searched_gateways"], 1)
        self.assertEqual(gateway_results["viable_gateways"], 1)
        self.assertEqual(
            set(result["live_search"]["diagnostics"]),
            {"search_plan", "observed_gateway_diagnostics"},
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
                    def phased_primary(
                        queries: list[dict[str, object]], *_: object, **__: object
                    ) -> list[dict[str, object]]:
                        if queries and bool(queries[0].get("direct_only")):
                            return []
                        return primary_results

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
                                    "provider": "tutu",
                                    "offer_count": 0,
                                },
                            }
                        ],
                    }
                    with (
                        patch(
                            "flights_cli.orchestrators.search_plan_builder.build_route_context",
                            return_value=plan,
                        ),
                        patch(
                            "flights_cli.execution.search_executor.run_primary_offer_queries",
                            side_effect=phased_primary,
                        ),
                        patch(
                            "flights_cli.execution.search_executor.GatewayLegProbeExecutor.run",
                            return_value=gateway_leg_results,
                        ),
                    ):
                        return execute_projection(
                            live_args(destination=destination),
                            Store(),
                        )

                baseline = run_with_primary([])
                with_provider_route = run_with_primary(provider_results)
                baseline_report = build_result_projection(baseline)
                provider_route_report = build_result_projection(with_provider_route)

                search_plan = with_provider_route["live_search"]["diagnostics"][
                    "search_plan"
                ]
                gateway_plan = search_plan["gateway_policy"]["discovery"]
                self.assertEqual(
                    gateway_plan["route_access_profile"], "restricted_access_market"
                )
                self.assertEqual(gateway_plan["mode"], "required")
                self.assertEqual(
                    gateway_plan["prior_set"], "restricted_bridge_gateways"
                )
                self.assertEqual(gateway_plan["market"], "restricted_bridge_gateways")
                self.assertEqual(
                    [
                        signal["source"]
                        for signal in gateway_plan["candidates"][0]["signals"]
                    ],
                    ["static_prior"],
                )
                self.assertEqual(
                    set(with_provider_route["live_search"]["diagnostics"]),
                    {"search_plan", "observed_gateway_diagnostics"},
                )
                observed = with_provider_route["live_search"]["diagnostics"][
                    "observed_gateway_diagnostics"
                ]
                candidates = observed["candidates"]
                self.assertEqual(observed["candidate_count"], len(candidates))
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
                self.assertEqual(observed["skipped_reasons"], [])
                self.assertIsNone(observed["empty_reason"])

                self.assertEqual(
                    set(baseline_report["frontier"]),
                    {"schema_version", "option_ids", "coverage_summary"},
                )
                self.assertEqual(
                    set(provider_route_report["frontier"]),
                    {"schema_version", "option_ids", "coverage_summary"},
                )


if __name__ == "__main__":
    unittest.main()
