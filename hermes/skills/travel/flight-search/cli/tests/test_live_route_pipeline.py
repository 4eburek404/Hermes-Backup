from __future__ import annotations

import json
import unittest
from datetime import timedelta
from unittest.mock import patch

from flights_cli.config import DEFAULT_DIRECT_CATALOG_LIMIT
from flights_cli.orchestrators.search_workflow import SearchWorkflow
from flights_cli.orchestrators.search_plan_builder import (
    build_planning_state,
    build_route_context,
)
from flights_cli.pipeline.search_plan import (
    DecisionPolicy,
    ExecutionPolicy,
    GatewayPolicy,
    OutputPolicy,
    ProviderAttemptPlan,
    RoutePlan,
    SearchPhases,
    SearchPlan,
)
from flights_cli.store import Store
from helpers import future_departure_date, live_assembly_args


def execute_projection(*args: object, **kwargs: object) -> dict:
    request, store = args
    return SearchWorkflow(store).run_artifacts(request).projection_input


def live_args(**overrides: object):
    defaults = {
        "origin": "SVX",
        "destination": "CDG",
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
    limits = dict(legacy.get("execution_limits") or {})
    return SearchPlan(
        route=route,
        phases=SearchPhases(primary=primary),
        gateway_policy=GatewayPolicy(),
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
    def test_live_route_args_adapt_to_typed_search_flow(self) -> None:
        depart = future_departure_date()
        args = live_assembly_args(
            origin="SVX",
            destination="CDG",
            depart_date=depart.isoformat(),
            return_date=(depart + timedelta(days=4)).isoformat(),
            profile="business",
            no_live_cache=True,
        )

        flow = build_planning_state(args)

        self.assertEqual(flow.request.origin, "SVX")
        self.assertEqual(flow.request.destination, "CDG")
        self.assertEqual(flow.request.depart_date, depart.isoformat())
        self.assertEqual(
            flow.request.return_date, (depart + timedelta(days=4)).isoformat()
        )
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
        depart = future_departure_date()
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
            result = execute_projection(
                live_args(depart_date=depart.isoformat()), Store()
            )

        self.assertEqual(build_flow.call_count, 1)
        self.assertIn("live_search", result)
        self.assertEqual(result["live_search"]["provider_policy"], "auto")
        route_plan = result["live_search"]["plan"]
        self.assertEqual(route_plan["origin"], "SVX")
        self.assertEqual(route_plan["destination"], "CDG")
        self.assertEqual(
            route_plan["dates"], {"depart": depart.isoformat(), "return": None}
        )
        search_plan = result["live_search"]["diagnostics"]["search_plan"]
        self.assertEqual(set(result["live_search"]["diagnostics"]), {"search_plan"})
        self.assertEqual(search_plan["schema_version"], "flight_search_plan.v6")
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
        self.assertEqual(set(result["live_search"]["diagnostics"]), {"search_plan"})
        self.assertEqual(
            result["live_search"]["primary_offer_results"],
            primary_results,
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
        self.assertEqual(set(result["live_search"]["diagnostics"]), {"search_plan"})

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


if __name__ == "__main__":
    unittest.main()
