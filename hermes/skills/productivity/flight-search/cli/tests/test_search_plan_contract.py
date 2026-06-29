from __future__ import annotations

import copy
import unittest

from flights_cli.apps.common import validate_contract_payload
from flights_cli.orchestrators.live_route_assembly import build_live_route_segment_plan
from flights_cli.orchestrators.search_plan_builder import build_search_plan
from flights_cli.pipeline.search_plan import (
    SEARCH_PLAN_SCHEMA_VERSION,
    FallbackSegmentPlan,
    GatewayDiscovery,
    SearchPlan,
)
from flights_cli.pipeline.search_pipeline import build_live_route_search_flow
from flights_cli.store import Store
from helpers import live_assembly_args


class SearchPlanContractTests(unittest.TestCase):
    def test_model_serializes_contract_shape(self) -> None:
        plan = SearchPlan(
            primary_offer_queries=[{"origin": "SVX", "destination": "PEK"}],
            mandatory_controls=[{"type": "full_route_aggregate"}],
            gateway_discovery=GatewayDiscovery(enabled=False, reason=None),
            fallback_segment_plan=FallbackSegmentPlan(
                segments=[
                    {
                        "direction": "outbound",
                        "leg": "direct_outbound",
                        "origin": "SVX",
                        "destination": "PEK",
                        "date": "2026-08-15",
                    }
                ]
            ),
            coverage_expectations=[{"type": "bounded_live_controls_only"}],
        ).to_dict()

        self.assertEqual(plan["schema_version"], SEARCH_PLAN_SCHEMA_VERSION)
        validate_contract_payload("search_plan", plan)

    def test_builder_populates_primary_offer_queries_and_fallback_segments(
        self,
    ) -> None:
        store = Store()
        options = live_assembly_args(
            origin="SVX",
            destination="AMS",
            depart_date="2026-08-15",
            return_date=None,
            routing_strategy="hub-list",
            hub=["IST"],
            no_live_cache=True,
            no_direct_route_intel=True,
        )
        flow = build_live_route_search_flow(options, store)
        route_plan = build_live_route_segment_plan(options, store, flow=flow)

        search_plan = build_search_plan(
            options, store, flow=flow, fallback_route_plan=route_plan
        )

        validate_contract_payload("search_plan", search_plan)
        self.assertEqual(search_plan["schema_version"], "flight_search_plan.v1")
        self.assertEqual(
            search_plan["primary_offer_queries"],
            [
                {
                    "role": "primary_offer_collection",
                    "source_type": "provider_full_route",
                    "probe_type": "full_route_aggregate",
                    "provider": "kupibilet",
                    "direction": "outbound",
                    "origin": "SVX",
                    "destination": "AMS",
                    "date": "2026-08-15",
                    "currency": "RUB",
                    "direct_only": False,
                    "limit": 10,
                    "execution_state": "not_executed",
                    "route_family": "ru_to_western_europe_bridge",
                    "exhaustive": False,
                    "non_exhaustive_reason": "provider_full_route_aggregate_is_primary_collection_not_coverage_proof",
                }
            ],
        )
        self.assertEqual(search_plan["mandatory_controls"], [])
        self.assertEqual(
            search_plan["gateway_discovery"], {"enabled": False, "reason": None}
        )
        self.assertEqual(
            search_plan["fallback_segment_plan"]["segments"], route_plan["segments"]
        )
        self.assertEqual(
            search_plan["coverage_expectations"],
            [
                {
                    "type": "primary_offer_collection_not_exhaustive",
                    "route_family": "ru_to_western_europe_bridge",
                    "source_type": "provider_full_route",
                    "reason": "keep segment fallback coverage for RU to Western Europe bridge routes",
                }
            ],
        )

    def test_builder_does_not_add_primary_aggregate_for_direct_inventory(
        self,
    ) -> None:
        store = Store()
        for label, overrides in {
            "strict_direct_only": {
                "max_connections": 0,
                "tier2_max_connections": 0,
            },
            "date_window_direct_inventory": {
                "max_connections": 0,
                "tier2_max_connections": 0,
                "date_window_end": "2026-08-16",
            },
        }.items():
            with self.subTest(label=label):
                options = live_assembly_args(
                    origin="SVX",
                    destination="AMS",
                    depart_date="2026-08-15",
                    return_date=None,
                    no_live_cache=True,
                    no_direct_route_intel=True,
                    **overrides,
                )
                flow = build_live_route_search_flow(options, store)
                route_plan = build_live_route_segment_plan(options, store, flow=flow)

                search_plan = build_search_plan(
                    options, store, flow=flow, fallback_route_plan=route_plan
                )

                validate_contract_payload("search_plan", search_plan)
                self.assertEqual(search_plan["primary_offer_queries"], [])
                self.assertEqual(search_plan["coverage_expectations"], [])
                self.assertEqual(
                    search_plan["fallback_segment_plan"]["segments"],
                    route_plan["segments"],
                )
                self.assertTrue(route_plan["segments"])
                self.assertTrue(
                    all(
                        segment.get("route_family") == "direct_inventory"
                        for segment in route_plan["segments"]
                    )
                )

    def test_builder_skips_primary_aggregate_when_provider_lacks_support(
        self,
    ) -> None:
        store = Store()
        options = live_assembly_args(
            origin="IST",
            destination="LHR",
            depart_date="2026-08-15",
            return_date=None,
            provider_policy="fli",
            routing_strategy="hub-list",
            hub=["AMS"],
            no_live_cache=True,
            no_direct_route_intel=True,
        )
        flow = build_live_route_search_flow(options, store)
        route_plan = build_live_route_segment_plan(options, store, flow=flow)

        search_plan = build_search_plan(
            options, store, flow=flow, fallback_route_plan=route_plan
        )

        validate_contract_payload("search_plan", search_plan)
        self.assertEqual(search_plan["primary_offer_queries"], [])
        self.assertEqual(search_plan["coverage_expectations"], [])
        self.assertEqual(
            search_plan["fallback_segment_plan"]["segments"], route_plan["segments"]
        )
        self.assertTrue(route_plan["segments"])

    def test_builder_does_not_share_mutable_segment_state(self) -> None:
        store = Store()
        options = live_assembly_args(
            origin="SVX",
            destination="AMS",
            depart_date="2026-08-15",
            return_date=None,
            routing_strategy="hub-list",
            hub=["IST"],
            no_live_cache=True,
            no_direct_route_intel=True,
        )
        route_plan = build_live_route_segment_plan(options, store)
        original_segments = copy.deepcopy(route_plan["segments"])

        search_plan = build_search_plan(options, store, fallback_route_plan=route_plan)
        route_plan["segments"][0]["origin"] = "MUT"

        self.assertEqual(
            search_plan["fallback_segment_plan"]["segments"], original_segments
        )


if __name__ == "__main__":
    unittest.main()
