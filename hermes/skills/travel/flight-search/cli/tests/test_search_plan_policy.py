from __future__ import annotations

from datetime import timedelta
import unittest
from unittest.mock import patch

from flights_cli.orchestrators.search_plan_builder import build_planning_state
from flights_cli.store import Store
from tests.helpers import (
    build_search_plan,
    future_departure_date,
    live_assembly_args,
)


class SearchPlanPolicyTests(unittest.TestCase):
    """Форма плана и политика исполнения — то, что планировщик решает сам.

    Классификация рынка жила здесь же, пока её выводы на что-то влияли.
    Влиять перестали: `flow_decision` удалён 2 сентября, а вместе с ним
    проверки, сверявшие ярлыки `market_class`, `route_mode` и
    `routing_strategy` с ожидаемыми строками.
    """

    def setUp(self) -> None:
        self.store = Store()

    def plan_for(self, **overrides: object) -> dict:
        request = live_assembly_args(**overrides)
        return build_search_plan(request, self.store)

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
        plan = build_search_plan(request, self.store)

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
