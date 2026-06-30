from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

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
            gateway_leg_queries=[
                {
                    "origin": "SVX",
                    "destination": "IST",
                    "gateway": "IST",
                }
            ],
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
                    "route_family": "restricted_access_market",
                    "route_access_profile": "restricted_access_market",
                    "gateway_discovery_mode": "required",
                    "exhaustive": False,
                    "non_exhaustive_reason": "restricted_access_market_requires_gateway_discovery",
                }
            ],
        )
        self.assertEqual(search_plan["mandatory_controls"], [])
        gateway_discovery = search_plan["gateway_discovery"]
        self.assertEqual(gateway_discovery["enabled"], True)
        self.assertEqual(
            gateway_discovery["reason"],
            "route_access_profile_requires_gateway_discovery",
        )
        self.assertEqual(gateway_discovery["mode"], "required")
        self.assertEqual(
            gateway_discovery["route_access_profile"], "restricted_access_market"
        )
        self.assertEqual(
            gateway_discovery["route_access_reasons"],
            [
                "airspace_restrictions",
                "carrier_access_restrictions",
                "provider_full_route_not_exhaustive",
            ],
        )
        self.assertEqual(gateway_discovery["prior_set"], "restricted_bridge_gateways")
        self.assertEqual(
            gateway_discovery["matched_rule_id"], "ru_to_restricted_regions"
        )
        self.assertEqual(gateway_discovery["market"], "restricted_bridge_gateways")
        self.assertEqual(gateway_discovery["candidate_count"], 2)
        self.assertEqual(
            [candidate["code"] for candidate in gateway_discovery["candidates"]],
            ["IST", "DXB"],
        )
        self.assertEqual(gateway_discovery["skipped_reasons"], [])
        self.assertIsNone(gateway_discovery["empty_reason"])
        self.assertEqual(
            [
                (
                    query["leg"],
                    query["origin"],
                    query["destination"],
                    query["provider"],
                    query["direct_only"],
                    query["connection_layer"],
                )
                for query in search_plan["gateway_leg_queries"][:2]
            ],
            [
                (
                    "origin_to_gateway",
                    "SVX",
                    "IST",
                    "kupibilet",
                    True,
                    "restricted_ru_bridge_control",
                ),
                (
                    "gateway_to_destination",
                    "IST",
                    "AMS",
                    "fli",
                    False,
                    "restricted_non_ru_access",
                ),
            ],
        )
        self.assertTrue(
            all(
                query["execution_state"] == "not_executed"
                for query in search_plan["gateway_leg_queries"]
            )
        )
        self.assertEqual(
            search_plan["fallback_segment_plan"]["segments"], route_plan["segments"]
        )
        self.assertEqual(
            search_plan["coverage_expectations"],
            [
                {
                    "type": "gateway_discovery_required",
                    "route_access_profile": "restricted_access_market",
                    "gateway_discovery_mode": "required",
                    "source_type": "provider_full_route",
                    "reason": "restricted access markets keep segment fallback coverage and gateway discovery diagnostics",
                }
            ],
        )

    def test_builder_marks_restricted_routes_and_keeps_china_normal(
        self,
    ) -> None:
        store = Store()
        cases = {
            "AMS": {
                "route_access_profile": "restricted_access_market",
                "gateway_discovery_mode": "required",
                "prior_set": "restricted_bridge_gateways",
                "matched_rule_id": "ru_to_restricted_regions",
            },
            "FRA": {
                "route_access_profile": "restricted_access_market",
                "gateway_discovery_mode": "required",
                "prior_set": "restricted_bridge_gateways",
                "matched_rule_id": "ru_to_restricted_regions",
            },
            "LON": {
                "route_access_profile": "restricted_access_market",
                "gateway_discovery_mode": "required",
                "prior_set": "restricted_bridge_gateways",
                "matched_rule_id": "ru_to_restricted_regions",
            },
            "PEK": {
                "route_access_profile": "normal_ru_touching_market",
                "gateway_discovery_mode": "optional_after_provider_failure",
                "prior_set": "default_ru_touching_gateways",
                "matched_rule_id": "default_ru_touching",
            },
        }

        for destination, expected in cases.items():
            with self.subTest(destination=destination):
                options = live_assembly_args(
                    origin="SVX",
                    destination=destination,
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
                gateway_discovery = search_plan["gateway_discovery"]
                for key, value in expected.items():
                    if key == "gateway_discovery_mode":
                        self.assertEqual(gateway_discovery["mode"], value)
                        continue
                    self.assertEqual(gateway_discovery[key], value)
                priors = store.gateway_priors_for_market(gateway_discovery["prior_set"])
                self.assertTrue(priors)
                self.assertTrue(
                    all(prior["source"] == "static_prior" for prior in priors)
                )
                self.assertEqual(
                    gateway_discovery["candidate_count"],
                    len(gateway_discovery["candidates"]),
                )
                self.assertEqual(
                    [
                        query["provider"]
                        for query in search_plan["primary_offer_queries"]
                    ],
                    ["kupibilet"],
                )
                if destination == "PEK":
                    self.assertNotEqual(gateway_discovery["mode"], "required")
                    self.assertEqual(search_plan["coverage_expectations"], [])
                    self.assertEqual(search_plan["gateway_leg_queries"], [])
                else:
                    self.assertEqual(
                        search_plan["primary_offer_queries"][0]["route_access_profile"],
                        "restricted_access_market",
                    )
                    self.assertEqual(
                        search_plan["primary_offer_queries"][0][
                            "gateway_discovery_mode"
                        ],
                        "required",
                    )
                    self.assertTrue(search_plan["gateway_leg_queries"])

    def test_builder_exposes_empty_gateway_discovery_when_priors_missing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing_priors_path = Path(tmp_dir) / "missing_gateway_priors.yaml"
            store = Store(gateway_priors_path=missing_priors_path)
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
        gateway_discovery = search_plan["gateway_discovery"]
        self.assertTrue(gateway_discovery["enabled"])
        self.assertEqual(gateway_discovery["mode"], "required")
        self.assertEqual(gateway_discovery["candidate_count"], 0)
        self.assertEqual(gateway_discovery["candidates"], [])
        self.assertEqual(
            gateway_discovery["empty_reason"], "no_gateway_candidates_discovered"
        )
        self.assertEqual(
            gateway_discovery["skipped_reasons"],
            ["no_gateway_candidates_discovered"],
        )
        self.assertEqual(search_plan["gateway_leg_queries"], [])

    def test_builder_bounds_gateway_leg_queries_by_config(
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
            gateway_discovery_limit=3,
            gateway_probe_batch_size=1,
            gateway_probe_max_batches=1,
            no_live_cache=True,
            no_direct_route_intel=True,
        )
        flow = build_live_route_search_flow(options, store)
        route_plan = build_live_route_segment_plan(options, store, flow=flow)

        search_plan = build_search_plan(
            options, store, flow=flow, fallback_route_plan=route_plan
        )

        validate_contract_payload("search_plan", search_plan)
        self.assertEqual(len(search_plan["gateway_leg_queries"]), 2)
        self.assertEqual(
            {
                (query["gateway"], query["provider"])
                for query in search_plan["gateway_leg_queries"]
            },
            {("IST", "kupibilet"), ("IST", "fli")},
        )

    def test_restricted_eu_to_ru_plans_access_leg_as_aggregate_not_fake_gateway_to_ru(
        self,
    ) -> None:
        store = Store()
        options = live_assembly_args(
            origin="NTE",
            destination="SVX",
            depart_date="2026-07-09",
            return_date=None,
            provider_policy="tutu",
            gateway_discovery_limit=1,
            gateway_probe_batch_size=1,
            gateway_probe_max_batches=1,
            no_live_cache=True,
            no_direct_route_intel=True,
        )
        flow = build_live_route_search_flow(options, store)
        route_plan = build_live_route_segment_plan(options, store, flow=flow)

        search_plan = build_search_plan(
            options, store, flow=flow, fallback_route_plan=route_plan
        )

        validate_contract_payload("search_plan", search_plan)
        self.assertEqual(search_plan["gateway_discovery"]["mode"], "required")
        self.assertEqual(
            [
                (
                    query["leg"],
                    query["origin"],
                    query["destination"],
                    query["provider"],
                    query["direct_only"],
                    query["probe_type"],
                    query["connection_layer"],
                    query["allows_intermediate_hubs"],
                )
                for query in search_plan["gateway_leg_queries"]
            ],
            [
                (
                    "origin_to_gateway",
                    "NTE",
                    "IST",
                    "tutu",
                    False,
                    "segment_hub_leg",
                    "restricted_non_ru_access",
                    True,
                ),
                (
                    "gateway_to_destination",
                    "IST",
                    "SVX",
                    "tutu",
                    True,
                    "segment_direct",
                    "restricted_ru_bridge_control",
                    False,
                ),
            ],
        )
        self.assertNotIn(
            ("AMS", "SVX"),
            {
                (query["origin"], query["destination"])
                for query in search_plan["gateway_leg_queries"]
            },
        )

    def test_builder_keeps_fli_out_of_both_policy_for_ru_touching_route(
        self,
    ) -> None:
        store = Store()
        options = live_assembly_args(
            origin="SVX",
            destination="AMS",
            depart_date="2026-08-15",
            return_date=None,
            provider_policy="both",
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
        self.assertEqual(
            [query["provider"] for query in search_plan["primary_offer_queries"]],
            ["kupibilet"],
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

    def test_builder_plans_non_ru_primary_route_with_fli_provider(
        self,
    ) -> None:
        store = Store()
        options = live_assembly_args(
            origin="IST",
            destination="AMS",
            depart_date="2026-08-15",
            return_date=None,
            routing_strategy="hub-list",
            hub=["LHR"],
            no_live_cache=True,
            no_direct_route_intel=True,
        )
        flow = build_live_route_search_flow(options, store)
        route_plan = build_live_route_segment_plan(options, store, flow=flow)

        search_plan = build_search_plan(
            options, store, flow=flow, fallback_route_plan=route_plan
        )

        validate_contract_payload("search_plan", search_plan)
        self.assertEqual(
            search_plan["primary_offer_queries"],
            [
                {
                    "role": "primary_offer_collection",
                    "source_type": "provider_full_route",
                    "probe_type": "full_route_aggregate",
                    "provider": "fli",
                    "direction": "outbound",
                    "origin": "IST",
                    "destination": "AMS",
                    "date": "2026-08-15",
                    "currency": "RUB",
                    "direct_only": False,
                    "limit": 10,
                    "execution_state": "not_executed",
                }
            ],
        )
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
