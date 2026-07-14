from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from flights_cli.commands.common import validate_contract_payload
from flights_cli.orchestrators.search_plan_builder import (
    build_planning_state,
    build_route_context,
    build_search_plan,
)
from flights_cli.pipeline.search_plan import (
    SEARCH_PLAN_SCHEMA_VERSION,
    GatewayDiscovery,
    SearchPlan,
)
from flights_cli.store import Store
from helpers import live_assembly_args


class SearchPlanContractTests(unittest.TestCase):
    def test_model_serializes_contract_shape(self) -> None:
        plan = SearchPlan(
            route_context={
                "origin": "SVX",
                "destination": "PEK",
                "dates": {"depart": "2026-08-15", "return": None},
                "currency": "RUB",
                "profile": "business",
                "ticketing": "separate",
                "provider_policy": "tutu",
                "routing_strategy": "hub-list",
                "route_mode": "hub_list",
                "market_class": "global_non_ru",
                "route_families": [{"id": "hub_list"}],
                "hubs": [],
                "origin_airports": ["SVX"],
                "destination_airports": ["PEK"],
                "airport_scope": None,
                "direct_only": False,
                "coverage_controls": [],
            },
            primary_offer_queries=(
                {
                    "role": "primary_offer_collection",
                    "source_type": "provider_full_route",
                    "probe_type": "full_route_aggregate",
                    "provider": "tutu",
                    "direction": "outbound",
                    "origin": "SVX",
                    "destination": "PEK",
                    "date": "2026-08-15",
                    "currency": "RUB",
                    "direct_only": False,
                    "execution_state": "not_executed",
                },
            ),
            gateway_discovery=GatewayDiscovery(enabled=False, reason=None),
            execution_limits={
                "max_segment_searches": 10,
                "search_wave_max_waves": 1,
                "search_wave_probe_limit": 2,
                "search_wave_top_k": 2,
                "aggregate_control_limit": 0,
                "segment_limit": 30,
                "live_cache_ttl_seconds": 0,
                "live_cache_enabled": False,
                "timeout": 60,
                "fail_fast": False,
            },
            output_limits={"catalog_limit": 10, "direct_catalog_limit": 30},
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
        )
        flow = build_planning_state(options, store)
        build_route_context(options, store, flow=flow)

        search_plan = build_search_plan(options, store, flow=flow)

        validate_contract_payload("search_plan", search_plan)
        self.assertEqual(search_plan["schema_version"], "flight_search_plan.v2")
        primary_queries = search_plan["primary_offer_queries"]
        self.assertEqual(
            [query["provider"] for query in primary_queries],
            ["tutu", "kupibilet", "tutu", "kupibilet"],
        )
        self.assertEqual(
            [query["direct_only"] for query in primary_queries],
            [True, True, False, False],
        )
        for query in primary_queries:
            with self.subTest(provider=query["provider"]):
                self.assertEqual(query["role"], "primary_offer_collection")
                self.assertEqual(query["source_type"], "provider_full_route")
                self.assertEqual(query["origin_airports"], ["SVX"])
                self.assertEqual(query["destination_airports"], ["AMS"])
                self.assertEqual(query["probe_type"], "full_route_aggregate")
                self.assertEqual(query["direction"], "outbound")
                self.assertEqual(query["origin"], "SVX")
                self.assertEqual(query["destination"], "AMS")
                self.assertEqual(query["date"], "2026-08-15")
                self.assertEqual(query["currency"], "RUB")
                self.assertIn(query["direct_only"], (True, False))
                self.assertEqual(query["limit"], options.evidence.primary_offer_limit)
                self.assertEqual(query["execution_state"], "not_executed")
                self.assertEqual(
                    query["route_access_profile"], "restricted_access_market"
                )
                self.assertEqual(query["gateway_discovery_mode"], "required")
                if query["direct_only"]:
                    self.assertEqual(query["route_family"], "direct_inventory")
                    self.assertTrue(query["exhaustive"])
                else:
                    self.assertEqual(query["route_family"], "restricted_access_market")
                    self.assertFalse(query["exhaustive"])
                    self.assertEqual(
                        query["non_exhaustive_reason"],
                        "restricted_access_market_requires_gateway_discovery",
                    )
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
                for query in search_plan["conditional_gateway_queries"]
                if not query["direct_only"]
            ],
            [
                (
                    "origin_to_gateway",
                    "SVX",
                    "IST",
                    "tutu",
                    False,
                    "restricted_ru_bridge_control",
                ),
                (
                    "gateway_to_destination",
                    "IST",
                    "AMS",
                    "tutu",
                    False,
                    "restricted_non_ru_access",
                ),
                (
                    "gateway_to_destination",
                    "IST",
                    "AMS",
                    "tutu",
                    False,
                    "restricted_non_ru_access",
                ),
            ],
        )
        self.assertTrue(
            all(
                query["execution_state"] == "not_executed"
                for query in search_plan["conditional_gateway_queries"]
                if not query["direct_only"]
            )
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
                )
                flow = build_planning_state(options, store)
                build_route_context(options, store, flow=flow)

                search_plan = build_search_plan(options, store, flow=flow)

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
                    ["tutu", "kupibilet", "tutu", "kupibilet"],
                )
                if destination == "PEK":
                    self.assertNotEqual(gateway_discovery["mode"], "required")
                    self.assertEqual(search_plan["coverage_expectations"], [])
                    self.assertTrue(search_plan["conditional_gateway_queries"])
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
                    self.assertTrue(search_plan["conditional_gateway_queries"])

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
            )
            flow = build_planning_state(options, store)
            build_route_context(options, store, flow=flow)

            search_plan = build_search_plan(options, store, flow=flow)

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
        self.assertEqual(search_plan["conditional_gateway_queries"], [])

    def test_builder_bounds_conditional_gateway_queries_by_config(
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
        )
        flow = build_planning_state(options, store)
        build_route_context(options, store, flow=flow)

        search_plan = build_search_plan(options, store, flow=flow)

        validate_contract_payload("search_plan", search_plan)
        self.assertEqual(len(search_plan["conditional_gateway_queries"]), 6)
        self.assertEqual(
            [
                (query["leg"], query["gateway"], query["provider"], query["date"])
                for query in search_plan["conditional_gateway_queries"]
                if not query["direct_only"]
            ],
            [
                ("origin_to_gateway", "IST", "tutu", "2026-08-15"),
                ("gateway_to_destination", "IST", "tutu", "2026-08-15"),
                ("gateway_to_destination", "IST", "tutu", "2026-08-16"),
            ],
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
        )
        flow = build_planning_state(options, store)
        build_route_context(options, store, flow=flow)

        search_plan = build_search_plan(options, store, flow=flow)

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
                for query in search_plan["conditional_gateway_queries"]
                if not query["direct_only"]
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
                    False,
                    "segment_hub_leg",
                    "restricted_ru_bridge_control",
                    True,
                ),
                (
                    "gateway_to_destination",
                    "IST",
                    "SVX",
                    "tutu",
                    False,
                    "segment_hub_leg",
                    "restricted_ru_bridge_control",
                    True,
                ),
            ],
        )
        self.assertNotIn(
            ("AMS", "SVX"),
            {
                (query["origin"], query["destination"])
                for query in search_plan["conditional_gateway_queries"]
            },
        )

    def test_optional_gateway_queries_are_preplanned_for_runtime_fallback(self) -> None:
        store = Store()
        options = live_assembly_args(
            origin="ALA",
            destination="SVX",
            depart_date="2026-09-17",
            return_date=None,
            provider_policy="tutu",
            no_live_cache=True,
        )

        search_plan = build_search_plan(options, store)

        self.assertEqual(
            search_plan["gateway_discovery"]["mode"],
            "optional_after_provider_failure",
        )
        self.assertEqual(len(search_plan["conditional_gateway_queries"]), 6)

    def test_builder_uses_tutu_primary_for_ru_touching_auto_full_route(
        self,
    ) -> None:
        store = Store()
        options = live_assembly_args(
            origin="SVX",
            destination="AMS",
            depart_date="2026-08-15",
            return_date=None,
            provider_policy="auto",
            routing_strategy="hub-list",
            hub=["IST"],
            no_live_cache=True,
        )
        flow = build_planning_state(options, store)
        build_route_context(options, store, flow=flow)

        search_plan = build_search_plan(options, store, flow=flow)

        validate_contract_payload("search_plan", search_plan)
        self.assertEqual(
            [query["provider"] for query in search_plan["primary_offer_queries"]],
            ["tutu", "kupibilet", "tutu", "kupibilet"],
        )
        self.assertEqual(
            [query["direct_only"] for query in search_plan["primary_offer_queries"]],
            [True, True, False, False],
        )

    def test_builder_adds_direct_primary_queries_for_direct_inventory(
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
                    **overrides,
                )
                flow = build_planning_state(options, store)
                build_route_context(options, store, flow=flow)

                search_plan = build_search_plan(options, store, flow=flow)

                validate_contract_payload("search_plan", search_plan)
                self.assertTrue(search_plan["primary_offer_queries"])
                self.assertTrue(
                    all(
                        query["direct_only"]
                        for query in search_plan["primary_offer_queries"]
                    )
                )
                self.assertTrue(
                    all(
                        query.get("route_family") == "direct_inventory"
                        for query in search_plan["primary_offer_queries"]
                    )
                )
                self.assertEqual(search_plan["coverage_expectations"], [])

    def test_builder_plans_non_ru_primary_route_with_tutu_and_kupibilet(
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
        )
        flow = build_planning_state(options, store)
        route_plan = build_route_context(options, store, flow=flow)

        search_plan = build_search_plan(options, store, flow=flow)

        validate_contract_payload("search_plan", search_plan)
        self.assertEqual(
            [query["provider"] for query in search_plan["primary_offer_queries"]],
            ["tutu", "kupibilet", "tutu", "kupibilet"],
        )
        for query in search_plan["primary_offer_queries"]:
            with self.subTest(provider=query["provider"]):
                self.assertEqual(query["role"], "primary_offer_collection")
                self.assertEqual(query["source_type"], "provider_full_route")
                self.assertEqual(query["probe_type"], "full_route_aggregate")
                self.assertEqual(query["direction"], "outbound")
                self.assertEqual(query["origin"], "IST")
                self.assertEqual(query["destination"], "AMS")
                self.assertEqual(query["date"], "2026-08-15")
                self.assertEqual(query["currency"], "RUB")
                self.assertIn(query["direct_only"], (True, False))
                self.assertEqual(query["limit"], options.evidence.primary_offer_limit)
                self.assertEqual(query["execution_state"], "not_executed")
        self.assertEqual(search_plan["coverage_expectations"], [])
        self.assertEqual(search_plan["route_context"], route_plan)

    def test_carrier_filters_flow_to_primary_offer_queries(self) -> None:
        store = Store()
        options = live_assembly_args(
            origin="IST",
            destination="AMS",
            depart_date="2026-08-15",
            return_date=None,
            provider_policy="auto",
            only_carrier="KL",
            prefer_carrier="AF",
            no_live_cache=True,
        )
        flow = build_planning_state(options, store)
        build_route_context(options, store, flow=flow)

        search_plan = build_search_plan(options, store, flow=flow)

        validate_contract_payload("search_plan", search_plan)
        self.assertGreater(len(search_plan["primary_offer_queries"]), 0)
        for query in search_plan["primary_offer_queries"]:
            with self.subTest(role=query["role"], leg=query.get("leg")):
                self.assertEqual(query["only_carriers"], ["KL"])
                self.assertEqual(query["preferred_carriers"], ["AF"])

    def test_explicit_airport_scope_flows_to_primary_queries(self) -> None:
        store = Store()
        options = live_assembly_args(
            origin="MOW",
            destination="LON",
            origin_airports=["SVO"],
            destination_airports=["LHR", "LGW"],
            depart_date="2026-08-15",
            return_date=None,
            provider_policy="tutu",
            no_live_cache=True,
        )
        flow = build_planning_state(options, store)
        build_route_context(options, store, flow=flow)

        search_plan = build_search_plan(options, store, flow=flow)

        self.assertTrue(search_plan["primary_offer_queries"])
        for query in search_plan["primary_offer_queries"]:
            self.assertEqual(query["origin_airports"], ["SVO"])
            self.assertEqual(query["destination_airports"], ["LHR", "LGW"])

    def test_return_direct_inventory_swaps_airport_scope(self) -> None:
        store = Store()
        options = live_assembly_args(
            origin="MOW",
            destination="LON",
            origin_airports=["SVO"],
            destination_airports=["LHR"],
            depart_date="2026-08-15",
            return_date="2026-08-22",
            max_connections=0,
            tier2_max_connections=0,
            provider_policy="tutu",
            no_live_cache=True,
        )
        flow = build_planning_state(options, store)
        build_route_context(options, store, flow=flow)

        search_plan = build_search_plan(options, store, flow=flow)

        queries = search_plan["primary_offer_queries"]
        outbound = next(query for query in queries if query["direction"] == "outbound")
        inbound = next(query for query in queries if query["direction"] == "return")
        self.assertEqual(outbound["origin_airports"], ["SVO"])
        self.assertEqual(outbound["destination_airports"], ["LHR"])
        self.assertEqual(inbound["origin_airports"], ["LHR"])
        self.assertEqual(inbound["destination_airports"], ["SVO"])

    def test_builder_copies_route_context_without_fallback_segment_state(self) -> None:
        store = Store()
        options = live_assembly_args(
            origin="SVX",
            destination="AMS",
            depart_date="2026-08-15",
            return_date=None,
            routing_strategy="hub-list",
            hub=["IST"],
            no_live_cache=True,
        )
        route_plan = build_route_context(options, store)

        search_plan = build_search_plan(options, store)
        route_plan["origin"] = "MUT"

        self.assertEqual(search_plan["route_context"]["origin"], "SVX")


if __name__ == "__main__":
    unittest.main()
