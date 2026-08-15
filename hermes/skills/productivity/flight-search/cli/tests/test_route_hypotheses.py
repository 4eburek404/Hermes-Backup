from __future__ import annotations

import unittest
import importlib.util
from typing import Any
from unittest.mock import patch

from flights_cli.pipeline.search_request import search_request_from_payload
from flights_cli.orchestrators.search_plan_builder import SearchPlanBuilder
from flights_cli.pipeline.search_plan import RouteLegTemplate
from flights_cli.execution.probe_dispatcher import SegmentProbeOutcome
from flights_cli.execution.probe_ledger import ProbeRunLedger
from flights_cli.execution.search_executor import SearchExecutor
from flights_cli.pipeline.offer_graph_builder import build_offer_graph
from flights_cli.pipeline.offer_graph_materializer import (
    materialize_offer_graph_candidates,
)
from flights_cli.store import Store


class RouteHypothesisRequestTests(unittest.TestCase):
    def test_v3_request_normalizes_to_empty_internal_route_hypotheses(self) -> None:
        request = search_request_from_payload(
            {
                "schema_version": "flight_search_request.v3",
                "origin": "PUS",
                "destination": "SVX",
                "depart_date": "2026-10-01",
            }
        )

        self.assertEqual(request.route_hypotheses, ())
        self.assertEqual(
            request.to_payload()["schema_version"], "flight_search_request.v4"
        )

    def test_v4_request_builds_immutable_route_leg_template(self) -> None:
        request = search_request_from_payload(
            {
                "schema_version": "flight_search_request.v4",
                "origin": "SVX",
                "destination": "AMS",
                "depart_date": "2026-10-01",
                "route_hypotheses": [
                    {
                        "airports": ["SVX", "IST", "AMS"],
                        "source": "web_route_discovery",
                    }
                ],
            }
        )

        plan = SearchPlanBuilder(Store()).build(request).to_dict()

        self.assertEqual(plan["schema_version"], "flight_search_plan.v6")
        self.assertNotIn("gateway", plan["phases"])
        self.assertEqual(
            plan["phases"]["route_legs"],
            [
                {
                    "hypothesis_id": "web_route_discovery:outbound:SVX-IST-AMS",
                    "direction": "outbound",
                    "required_airports": ["SVX", "IST", "AMS"],
                    "source": "web_route_discovery",
                    "leg_policies": ["exact_direct", "exact_direct"],
                    "trigger": "always",
                }
            ],
        )

    def test_arrival_window_derives_all_reachable_local_dates(self) -> None:
        module_name = "flights_cli.execution.route_leg_probe_executor"
        self.assertIsNotNone(importlib.util.find_spec(module_name))
        from flights_cli.execution.route_leg_probe_executor import reachable_local_dates

        self.assertEqual(
            reachable_local_dates("2026-10-01T23:30:00+03:00", 180),
            ["2026-10-01", "2026-10-02"],
        )
        self.assertEqual(
            reachable_local_dates("2026-10-01T23:30:00", 180),
            [],
        )

    def test_route_executor_derives_next_leg_dates_from_actual_arrival(self) -> None:
        module_name = "flights_cli.execution.route_leg_probe_executor"
        module = importlib.import_module(module_name)
        self.assertTrue(hasattr(module, "RouteLegProbeExecutor"))
        from flights_cli.execution.route_leg_probe_executor import (
            RouteLegProbeExecutor,
            RouteLegProbeOptions,
        )

        calls: list[dict[str, Any]] = []

        def dispatch(**kwargs: Any) -> list[SegmentProbeOutcome]:
            spec = kwargs["spec"]
            calls.append(spec)
            arrival = (
                "2026-10-01T23:30:00+03:00"
                if spec["leg_index"] == 0
                else f"{spec['date']}T12:00:00+03:00"
            )
            return [
                SegmentProbeOutcome(
                    summary={
                        "status": "ok",
                        "execution_state": "searched",
                        "provider": "tutu",
                        "offer_count": 1,
                    },
                    segment_result={
                        "offers": [
                            {
                                "id": f"{spec['leg_index']}-{spec['date']}",
                                "segments": [
                                    {
                                        "origin": spec["origin"],
                                        "destination": spec["destination"],
                                        "departure_at": f"{spec['date']}T08:00:00+03:00",
                                        "arrival_at": arrival,
                                    }
                                ],
                            }
                        ]
                    },
                )
            ]

        executor = RouteLegProbeExecutor(
            options=RouteLegProbeOptions(segment_limit=3, timeout=10, fail_fast=False),
            store=Store(),
            only_carriers=[],
            cache_ttl_seconds=0,
            use_live_cache=False,
            probe_ledger=ProbeRunLedger(),
        )
        template = RouteLegTemplate(
            hypothesis_id="web_route_discovery:outbound:SVX-IST-AMS",
            direction="outbound",
            required_airports=("SVX", "IST", "AMS"),
            source="web_route_discovery",
            leg_policies=("exact_direct", "exact_direct"),
            trigger="always",
        )

        with patch(f"{module_name}.dispatch_segment_probe", side_effect=dispatch):
            result = executor.run(
                [template],
                {
                    "route": {
                        "dates": {"depart": "2026-10-01", "return": None},
                        "currency": "RUB",
                        "provider_policy": "tutu",
                    },
                    "decision_policy": {"max_layover_min": 180},
                },
            )

        self.assertEqual(
            [(call["leg_index"], call["date"]) for call in calls],
            [(0, "2026-10-01"), (1, "2026-10-01"), (1, "2026-10-02")],
        )
        self.assertEqual(result["route_hypotheses"][0]["status"], "viable")

    def test_route_executor_stops_when_arrival_time_cannot_drive_next_leg(self) -> None:
        from flights_cli.execution.route_leg_probe_executor import (
            RouteLegProbeExecutor,
            RouteLegProbeOptions,
        )

        calls: list[dict[str, Any]] = []

        def dispatch(**kwargs: Any) -> list[SegmentProbeOutcome]:
            spec = kwargs["spec"]
            calls.append(spec)
            return [
                SegmentProbeOutcome(
                    summary={
                        "status": "ok",
                        "execution_state": "searched",
                        "provider": "tutu",
                    },
                    segment_result={
                        "offers": [
                            {
                                "id": "missing-arrival",
                                "segments": [
                                    {
                                        "origin": spec["origin"],
                                        "destination": spec["destination"],
                                    }
                                ],
                            }
                        ]
                    },
                )
            ]

        executor = RouteLegProbeExecutor(
            options=RouteLegProbeOptions(segment_limit=3, timeout=10, fail_fast=False),
            store=Store(),
            only_carriers=[],
            cache_ttl_seconds=0,
            use_live_cache=False,
        )
        template = RouteLegTemplate(
            hypothesis_id="web_route_discovery:outbound:SVX-IST-AMS",
            direction="outbound",
            required_airports=("SVX", "IST", "AMS"),
            source="web_route_discovery",
            leg_policies=("exact_direct", "exact_direct"),
            trigger="always",
        )

        with patch(
            "flights_cli.execution.route_leg_probe_executor.dispatch_segment_probe",
            side_effect=dispatch,
        ):
            result = executor.run(
                [template],
                {
                    "route": {
                        "dates": {"depart": "2026-10-01", "return": None},
                        "currency": "RUB",
                    },
                    "decision_policy": {"max_layover_min": 180},
                },
            )

        self.assertEqual(
            [(item["leg_index"], item["date"]) for item in calls], [(0, "2026-10-01")]
        )
        self.assertEqual(
            result["route_hypotheses"][0]["reason"],
            "route_leg_arrival_time_missing",
        )

    def test_search_executor_uses_route_leg_templates_without_mutating_plan(
        self,
    ) -> None:
        request = search_request_from_payload(
            {
                "schema_version": "flight_search_request.v4",
                "origin": "SVX",
                "destination": "AMS",
                "depart_date": "2026-10-01",
                "route_hypotheses": [
                    {
                        "airports": ["SVX", "IST", "AMS"],
                        "source": "web_route_discovery",
                    }
                ],
            }
        )
        plan = SearchPlanBuilder(Store()).build(request)
        original = plan.to_dict()
        executor_module = importlib.import_module(
            "flights_cli.execution.search_executor"
        )
        self.assertTrue(hasattr(executor_module, "RouteLegProbeExecutor"))
        route_result = {
            "route_hypotheses": [
                {
                    "hypothesis_id": "web_route_discovery:outbound:SVX-IST-AMS",
                    "status": "viable",
                    "legs": [],
                }
            ]
        }

        with (
            patch(
                "flights_cli.execution.search_executor.run_primary_offer_queries",
                return_value=[],
            ),
            patch.object(
                executor_module.RouteLegProbeExecutor,
                "run",
                return_value=route_result,
            ) as run_route_legs,
        ):
            evidence = SearchExecutor(Store()).execute(plan)

        self.assertEqual(evidence.gateway_leg_results, route_result)
        self.assertEqual(plan.to_dict(), original)
        run_route_legs.assert_called_once()

    def test_empty_primary_results_trigger_configured_route_legs(self) -> None:
        executor_module = importlib.import_module(
            "flights_cli.execution.search_executor"
        )

        for provider_policy in ("tutu", "kupibilet", "auto"):
            with self.subTest(provider_policy=provider_policy):
                request = search_request_from_payload(
                    {
                        "schema_version": "flight_search_request.v4",
                        "origin": "PUS",
                        "destination": "SVX",
                        "depart_date": "2026-09-10",
                        "provider_policy": provider_policy,
                        "route_hypotheses": [],
                    }
                )
                plan = SearchPlanBuilder(Store()).build(request)

                with (
                    patch(
                        "flights_cli.execution.search_executor.run_primary_offer_queries",
                        return_value=[],
                    ),
                    patch.object(
                        executor_module.RouteLegProbeExecutor,
                        "run",
                        return_value={"route_hypotheses": []},
                    ) as run_route_legs,
                ):
                    SearchExecutor(Store()).execute(plan)

                run_route_legs.assert_called_once()

    def test_connected_primary_offer_suppresses_configured_route_legs(self) -> None:
        request = search_request_from_payload(
            {
                "schema_version": "flight_search_request.v4",
                "origin": "PUS",
                "destination": "SVX",
                "depart_date": "2026-09-10",
                "provider_policy": "tutu",
                "route_hypotheses": [],
            }
        )
        plan = SearchPlanBuilder(Store()).build(request)
        connected_result = {
            "probe_id": "primary-002",
            "provider": "tutu",
            "direction": "outbound",
            "origin": "PUS",
            "destination": "SVX",
            "date": "2026-09-10",
            "status": "ok",
            "execution_state": "searched",
            "filters": {
                "direct_only": False,
                "origin_airports": ["PUS"],
                "destination_airports": ["SVX"],
                "only_carriers": [],
            },
            "top_offers": [
                {
                    "id": "connected-primary",
                    "segments": [
                        {
                            "origin": "PUS",
                            "destination": "IST",
                            "departure_at": "2026-09-10T08:00:00+09:00",
                            "arrival_at": "2026-09-10T14:00:00+03:00",
                        },
                        {
                            "origin": "IST",
                            "destination": "SVX",
                            "departure_at": "2026-09-10T18:00:00+03:00",
                            "arrival_at": "2026-09-11T01:00:00+05:00",
                        },
                    ],
                }
            ],
        }
        executor_module = importlib.import_module(
            "flights_cli.execution.search_executor"
        )

        with (
            patch(
                "flights_cli.execution.search_executor.run_primary_offer_queries",
                side_effect=[[], [connected_result]],
            ),
            patch.object(
                executor_module.RouteLegProbeExecutor, "run"
            ) as run_route_legs,
        ):
            evidence = SearchExecutor(Store()).execute(plan)

        run_route_legs.assert_not_called()
        self.assertEqual(
            evidence.gateway_leg_results["route_hypotheses"][0]["reason"],
            "gateway_trigger_not_satisfied",
        )

    def test_primary_failure_still_triggers_configured_route_legs(self) -> None:
        request = search_request_from_payload(
            {
                "schema_version": "flight_search_request.v4",
                "origin": "PUS",
                "destination": "SVX",
                "depart_date": "2026-09-10",
                "provider_policy": "tutu",
                "route_hypotheses": [],
            }
        )
        plan = SearchPlanBuilder(Store()).build(request)
        failed_result = {
            "probe_id": "primary-001",
            "provider": "tutu",
            "direction": "outbound",
            "origin": "PUS",
            "destination": "SVX",
            "date": "2026-09-10",
            "status": "error",
            "execution_state": "failed",
        }
        executor_module = importlib.import_module(
            "flights_cli.execution.search_executor"
        )

        with (
            patch(
                "flights_cli.execution.search_executor.run_primary_offer_queries",
                side_effect=[[failed_result], []],
            ),
            patch.object(
                executor_module.RouteLegProbeExecutor,
                "run",
                return_value={"route_hypotheses": []},
            ) as run_route_legs,
        ):
            SearchExecutor(Store()).execute(plan)

        run_route_legs.assert_called_once()

    def test_hypothesis_over_stop_policy_is_audited_without_execution(self) -> None:
        request = search_request_from_payload(
            {
                "schema_version": "flight_search_request.v4",
                "origin": "SVX",
                "destination": "AMS",
                "depart_date": "2026-10-01",
                "route_options": {"max_connections": 0},
                "route_hypotheses": [
                    {
                        "airports": ["SVX", "IST", "AMS"],
                        "source": "web_route_discovery",
                    }
                ],
            }
        )
        plan = SearchPlanBuilder(Store()).build(request)
        executor_module = importlib.import_module(
            "flights_cli.execution.search_executor"
        )

        with (
            patch(
                "flights_cli.execution.search_executor.run_primary_offer_queries",
                return_value=[],
            ),
            patch.object(
                executor_module.RouteLegProbeExecutor, "run"
            ) as run_route_legs,
        ):
            evidence = SearchExecutor(Store()).execute(plan)

        run_route_legs.assert_not_called()
        self.assertEqual(
            evidence.gateway_leg_results["route_hypotheses"][0]["reason"],
            "hypothesis_exceeds_stop_policy",
        )

    def test_materializer_never_combines_legs_from_different_hypotheses(self) -> None:
        graph = {
            "offers": [
                {
                    "id": "h1-leg0",
                    "source_type": "gateway_leg",
                    "origin": "SVX",
                    "destination": "IST",
                    "direction": "outbound",
                    "hypothesis_id": "h1",
                    "leg_index": 0,
                    "required_airports": ["SVX", "IST", "NRT"],
                    "edge_ids": ["h1-edge0"],
                },
                {
                    "id": "h2-leg1",
                    "source_type": "gateway_leg",
                    "origin": "IST",
                    "destination": "AMS",
                    "direction": "outbound",
                    "hypothesis_id": "h2",
                    "leg_index": 1,
                    "required_airports": ["ALA", "IST", "AMS"],
                    "edge_ids": ["h2-edge1"],
                },
            ],
            "edges": [
                {
                    "id": "h1-edge0",
                    "origin": "SVX",
                    "destination": "IST",
                    "direction": "outbound",
                    "ticketing_boundary": "separate_ticket_leg",
                    "departure_at": "2026-10-01T08:00:00+03:00",
                    "arrival_at": "2026-10-01T12:00:00+03:00",
                },
                {
                    "id": "h2-edge1",
                    "origin": "IST",
                    "destination": "AMS",
                    "direction": "outbound",
                    "ticketing_boundary": "separate_ticket_leg",
                    "departure_at": "2026-10-01T15:00:00+03:00",
                    "arrival_at": "2026-10-01T18:00:00+02:00",
                },
            ],
        }

        envelope = materialize_offer_graph_candidates(
            graph, requested_origin="SVX", requested_destination="AMS"
        )

        self.assertEqual(envelope["candidates"], [])

    def test_route_hypothesis_evidence_materializes_only_its_declared_chain(
        self,
    ) -> None:
        graph = build_offer_graph(
            primary_offer_results=[],
            gateway_leg_results={
                "route_hypotheses": [
                    {
                        "hypothesis_id": "web_route_discovery:outbound:SVX-IST-AMS",
                        "direction": "outbound",
                        "required_airports": ["SVX", "IST", "AMS"],
                        "status": "viable",
                        "legs": [
                            {
                                "leg_index": 0,
                                "origin": "SVX",
                                "destination": "IST",
                                "attempts": [
                                    {
                                        "provider": "tutu",
                                        "offer_count": 1,
                                        "offers": [
                                            {
                                                "id": "svx-ist",
                                                "price": 100,
                                                "currency": "RUB",
                                                "segments": [
                                                    {
                                                        "origin": "SVX",
                                                        "destination": "IST",
                                                        "departure_at": "2026-10-01T08:00:00+05:00",
                                                        "arrival_at": "2026-10-01T12:00:00+03:00",
                                                    }
                                                ],
                                            }
                                        ],
                                    }
                                ],
                            },
                            {
                                "leg_index": 1,
                                "origin": "IST",
                                "destination": "AMS",
                                "attempts": [
                                    {
                                        "provider": "tutu",
                                        "offer_count": 1,
                                        "offers": [
                                            {
                                                "id": "ist-ams",
                                                "price": 200,
                                                "currency": "RUB",
                                                "segments": [
                                                    {
                                                        "origin": "IST",
                                                        "destination": "AMS",
                                                        "departure_at": "2026-10-01T14:00:00+03:00",
                                                        "arrival_at": "2026-10-01T16:00:00+02:00",
                                                    }
                                                ],
                                            }
                                        ],
                                    }
                                ],
                            },
                        ],
                    }
                ]
            },
        )

        envelope = materialize_offer_graph_candidates(
            graph, requested_origin="SVX", requested_destination="AMS"
        )

        self.assertEqual(envelope["coverage"]["candidate_count"], 1)
        self.assertEqual(envelope["candidates"][0]["price"], 300)


if __name__ == "__main__":
    unittest.main()
