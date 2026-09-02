from __future__ import annotations

from datetime import timedelta
import unittest
from unittest.mock import patch

from flights_cli.orchestrators.search_plan_builder import (
    build_planning_state,
    build_route_context,
)
from flights_cli.store import Store
from tests.helpers import (
    build_search_plan,
    future_departure_date,
    live_assembly_args,
)


class FlowDecisionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = Store()

    def flow_for(self, **overrides: object):
        return build_planning_state(live_assembly_args(**overrides), self.store)

    def plan_for(self, **overrides: object) -> dict:
        request = live_assembly_args(**overrides)
        return build_search_plan(request, self.store)

    def test_global_non_ru_auto_uses_plain_hub_list_routing(self) -> None:
        flow = self.flow_for(
            origin="BER", destination="MAD", provider_policy="auto", return_date=None
        )
        route = build_route_context(flow.request, self.store, flow=flow)

        self.assertEqual(flow.flow_decision.market_class, "global_non_ru")
        self.assertEqual(flow.flow_decision.routing_strategy, "hub-list")
        self.assertEqual(route["routing_strategy"], "hub-list")
        self.assertFalse({"SVO", "DME", "VKO"} & set(route.get("hubs") or []))

    def test_ru_domestic_auto_gets_domestic_ru_route_mode(self) -> None:
        flow = self.flow_for(origin="SVX", destination="KUF", return_date=None)

        self.assertEqual(flow.flow_decision.market_class, "ru_domestic")
        self.assertEqual(flow.flow_decision.routing_strategy, "domestic-ru")
        self.assertEqual(flow.flow_decision.route_mode, "domestic_ru")

    def test_ru_touching_auto_uses_ru_priority_with_probe_reason(self) -> None:
        flow = self.flow_for(origin="SVX", destination="IST", return_date=None)
        plan = self.plan_for(origin="SVX", destination="IST", return_date=None)

        self.assertEqual(flow.flow_decision.market_class, "ru_touching_international")
        self.assertEqual(flow.flow_decision.routing_strategy, "ru-priority")
        self.assertIn(
            "ru_touching_market_uses_ru_priority_probes",
            flow.flow_decision.limitations,
        )
        self.assertIn(
            "ru_touching_market_uses_ru_priority_probes", plan["planning_reasons"]
        )

    def test_round_trip_plan_is_two_provider_directions_without_route_legs(self) -> None:
        depart = future_departure_date()
        plan = self.plan_for(
            origin="SVX",
            destination="CDG",
            depart_date=depart.isoformat(),
            return_date=(depart + timedelta(days=10)).isoformat(),
        )

        self.assertEqual(plan["schema_version"], "flight_search_plan.v6")
        self.assertEqual(
            set(plan),
            {
                "schema_version",
                "route",
                "phases",
                "gateway_policy",
                "execution_policy",
                "decision_policy",
                "output_policy",
                "planning_reasons",
            },
        )
        # Шлюзового плеча больше нет: круговой маршрут — это два
        # провайдерских запроса, а не зеркальные маршрутные шаблоны.
        self.assertEqual(plan["phases"]["route_legs"], [])
        self.assertEqual(plan["gateway_policy"]["trigger"], "disabled")
        self.assertEqual(
            {attempt["direction"] for attempt in plan["phases"]["primary"]},
            {"outbound", "return"},
        )

    def test_direct_inventory_is_expressed_by_route_and_provider_queries(self) -> None:
        request = live_assembly_args(
            origin="SVX",
            destination="KUF",
            max_connections=0,
            tier2_max_connections=0,
            return_date=None,
        )
        flow = build_planning_state(request, self.store)
        plan = build_search_plan(request, self.store)

        self.assertEqual(flow.flow_decision.route_mode, "direct_inventory")
        self.assertTrue(plan["route"]["direct_only"])
        self.assertTrue(plan["phases"]["primary"])
        self.assertTrue(
            all(
                attempt["query"]["direct_only"] for attempt in plan["phases"]["primary"]
            )
        )
        self.assertTrue(
            all(
                query["probe_type"] == "full_route_aggregate"
                for query in plan["phases"]["primary"]
            )
        )

    def test_exact_carrier_and_airport_scopes_require_live_probes(self) -> None:
        carrier_flow = self.flow_for(
            origin="BER", destination="MAD", only_carrier=["LH"], return_date=None
        )
        airport_flow = self.flow_for(
            origin="BER",
            destination="MAD",
            origin_airport=["BER"],
            destination_airport=["MAD"],
            return_date=None,
        )

        self.assertIn(
            "exact_scope_requires_live_probes", carrier_flow.flow_decision.limitations
        )
        self.assertIn(
            "exact_scope_requires_live_probes", airport_flow.flow_decision.limitations
        )

    def test_direct_only_and_exact_scopes_disable_live_cache(self) -> None:
        direct_plan = self.plan_for(
            max_connections=0,
            tier2_max_connections=0,
            return_date=None,
        )
        exact_plan = self.plan_for(origin_airport=["SVX"], return_date=None)

        for plan in (direct_plan, exact_plan):
            self.assertFalse(plan["execution_policy"]["live_cache_enabled"])
            self.assertEqual(plan["execution_policy"]["live_cache_ttl_seconds"], 0)

    def test_near_departure_uses_injected_today_and_disables_cache(self) -> None:
        depart = future_departure_date()
        injected_today = depart - timedelta(days=2)
        request = live_assembly_args(
            origin="BER",
            destination="MAD",
            depart_date=depart.isoformat(),
            live_cache_ttl_seconds=1800,
            return_date=None,
        )
        flow = build_planning_state(
            request,
            self.store,
            today_provider=lambda: injected_today,
        )
        with patch(
            "flights_cli.orchestrators.search_plan_builder.build_planning_state",
            return_value=flow,
        ):
            plan = build_search_plan(request, self.store)

        self.assertEqual(flow.today, injected_today)
        self.assertFalse(plan["execution_policy"]["live_cache_enabled"])
        self.assertEqual(plan["execution_policy"]["live_cache_ttl_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
