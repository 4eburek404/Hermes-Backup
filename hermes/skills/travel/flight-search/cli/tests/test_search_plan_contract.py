from __future__ import annotations

import unittest
from copy import deepcopy
from datetime import timedelta

from flights_cli.contracts.validation import validate_contract_payload
from flights_cli.errors import CliError
from flights_cli.pipeline.search_plan import (
    GATEWAY_TRIGGER_DISABLED,
    SEARCH_PLAN_SCHEMA_VERSION,
    SearchPlan,
)
from flights_cli.store import Store
from helpers import build_search_plan, future_departure_date, live_assembly_args


def _primary(plan: dict[str, object]) -> list[dict[str, object]]:
    return list(plan["phases"]["primary"])  # type: ignore[index]


def _route_legs(plan: dict[str, object]) -> list[dict[str, object]]:
    return list(plan["phases"]["route_legs"])  # type: ignore[index]


def _query(attempt: dict[str, object]) -> dict[str, object]:
    return dict(attempt["query"])  # type: ignore[arg-type]


class SearchPlanContractTests(unittest.TestCase):
    def test_v6_round_trip_is_typed_and_contract_valid(self) -> None:
        depart = future_departure_date()
        payload = build_search_plan(
            live_assembly_args(
                origin="SVX",
                destination="AMS",
                depart_date=depart.isoformat(),
                return_date=(depart + timedelta(days=7)).isoformat(),
                no_live_cache=True,
            ),
            Store(),
        )

        self.assertEqual(payload["schema_version"], SEARCH_PLAN_SCHEMA_VERSION)
        self.assertEqual(SearchPlan.from_dict(payload).to_dict(), payload)
        validate_contract_payload("search_plan", payload)
        attempts = _primary(payload)
        self.assertTrue(attempts)
        self.assertTrue(
            all(
                set(attempt)
                == {
                    "probe_id",
                    "phase",
                    "trigger",
                    "provider",
                    "probe_type",
                    "direction",
                    "query",
                }
                for attempt in attempts
            )
        )
        self.assertTrue(
            all(
                set(template)
                == {
                    "hypothesis_id",
                    "direction",
                    "required_airports",
                    "source",
                    "leg_policies",
                    "trigger",
                }
                for template in _route_legs(payload)
            )
        )
        self.assertEqual(
            {attempt["direction"] for attempt in _primary(payload)},
            {"outbound", "return"},
        )
        self.assertTrue(
            all("execution_state" not in _query(attempt) for attempt in attempts)
        )
        self.assertEqual(
            payload["output_policy"]["max_round_trip_pairs"],  # type: ignore[index]
            12,
        )

    def test_v6_rejects_flat_attempts_without_nested_query(self) -> None:
        depart = future_departure_date()
        payload = build_search_plan(
            live_assembly_args(
                origin="SVX",
                destination="AMS",
                depart_date=depart.isoformat(),
                return_date=None,
                provider_policy="tutu",
                no_live_cache=True,
            ),
            Store(),
        )
        flat = deepcopy(payload)
        attempt = flat["phases"]["primary"][0]
        attempt.update(attempt.pop("query"))

        with self.assertRaises(ValueError):
            SearchPlan.from_dict(flat)

    def test_v6_rejects_runtime_state_inside_planned_attempt(self) -> None:
        depart = future_departure_date()
        payload = build_search_plan(
            live_assembly_args(
                origin="SVX",
                destination="AMS",
                depart_date=depart.isoformat(),
                return_date=None,
                provider_policy="tutu",
                no_live_cache=True,
            ),
            Store(),
        )
        with_runtime_state = deepcopy(payload)
        with_runtime_state["phases"]["primary"][0]["query"]["execution_state"] = (
            "not_executed"
        )

        with self.assertRaises(ValueError):
            SearchPlan.from_dict(with_runtime_state)
        with self.assertRaises(CliError):
            validate_contract_payload("search_plan", with_runtime_state)

    def test_direct_only_is_an_absolute_gateway_prohibition(self) -> None:
        depart = future_departure_date()
        plan = build_search_plan(
            live_assembly_args(
                origin="SVX",
                destination="AMS",
                depart_date=depart.isoformat(),
                return_date=None,
                preferred_connections=0,
                max_connections=0,
                no_live_cache=True,
            ),
            Store(),
        )

        self.assertTrue(plan["route"]["direct_only"])  # type: ignore[index]
        self.assertTrue(_primary(plan))
        self.assertTrue(
            all(_query(attempt)["direct_only"] for attempt in _primary(plan))
        )
        self.assertEqual(_route_legs(plan), [])
        self.assertEqual(
            plan["gateway_policy"]["trigger"],  # type: ignore[index]
            GATEWAY_TRIGGER_DISABLED,
        )
        self.assertFalse(
            plan["gateway_policy"]["discovery"]["enabled"]  # type: ignore[index]
        )

    def test_request_policies_are_resolved_into_plan(self) -> None:
        depart = future_departure_date()
        plan = build_search_plan(
            live_assembly_args(
                origin="MOW",
                destination="LON",
                origin_airports=["SVO"],
                destination_airports=["LHR", "LGW"],
                only_carrier="KL",
                depart_date=depart.isoformat(),
                return_date=None,
                provider_policy="tutu",
                no_live_cache=True,
            ),
            Store(),
        )

        for attempt in _primary(plan):
            query = _query(attempt)
            self.assertEqual(query["origin_airports"], ["SVO"])
            self.assertEqual(query["destination_airports"], ["LGW", "LHR"])
            self.assertEqual(query["only_carriers"], ["KL"])
        self.assertEqual(
            plan["execution_policy"]["only_carriers"],
            ["KL"],  # type: ignore[index]
        )

    def test_return_direct_inventory_swaps_airport_scope(self) -> None:
        depart = future_departure_date()
        plan = build_search_plan(
            live_assembly_args(
                origin="MOW",
                destination="LON",
                origin_airports=["SVO"],
                destination_airports=["LHR"],
                depart_date=depart.isoformat(),
                return_date=(depart + timedelta(days=7)).isoformat(),
                preferred_connections=0,
                max_connections=0,
                provider_policy="tutu",
                no_live_cache=True,
            ),
            Store(),
        )

        outbound = next(
            attempt for attempt in _primary(plan) if attempt["direction"] == "outbound"
        )
        inbound = next(
            attempt for attempt in _primary(plan) if attempt["direction"] == "return"
        )
        self.assertEqual(_query(outbound)["origin_airports"], ["SVO"])
        self.assertEqual(_query(outbound)["destination_airports"], ["LHR"])
        self.assertEqual(_query(inbound)["origin_airports"], ["LHR"])
        self.assertEqual(_query(inbound)["destination_airports"], ["SVO"])


if __name__ == "__main__":
    unittest.main()
