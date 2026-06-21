"""Unit tests for LiveAssemblyRunner skip-predicate methods and helper functions.

These tests exercise the pure-logic predicate methods with minimal fake state —
no network, no Store, no argparse.  Each test constructs a LiveAssemblyRunner
with just enough init state to call the method under test.
"""
from __future__ import annotations

import argparse
import unittest
from typing import Any

from flights_cli.domain.vocabulary import Direction, Leg, RoutingStrategy
from flights_cli.orchestrators.live_assembly_runner import (
    LiveAssemblyRunner,
    city_code_primary_keys_for_deferred_airport,
    deferred_airport_priority_sides,
    direct_route_intel_context,
    endpoint_group_code,
    hub_viability_summary,
    plan_has_svx_direct_control,
    preferred_keys_for_deferred_airport,
    provider_city_code_side,
)
from flights_cli.store import Store


# ---------------------------------------------------------------------------
# Helpers to build minimal runner / args / spec
# ---------------------------------------------------------------------------

def _args(**overrides: Any) -> argparse.Namespace:
    """Build a minimal Namespace with defaults that skip-predicates read."""
    defaults = dict(
        origin="SVX",
        destination="BKK",
        depart_date="2026-08-01",
        return_date="2026-08-15",
        currency="RUB",
        profile="balanced",
        ticketing="separate",
        include_segment_results=20,
        limit_per_pair=5,
        max_segment_searches=200,
        min_same_airport_min=60,
        min_cross_airport_min=180,
        max_airports_per_city=4,
        provider_policy="kupibilet",
        only_carrier=None,
        prefer_carrier=None,
        no_direct_route_intel=False,
        direct_route_index_ttl_seconds=0,
        timeout=20,
        hub=[],
        date_window_end=None,
        outbound_second_leg_day_offset=None,
        return_second_leg_day_offset=None,
        origin_airport=None,
        destination_airport=None,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _runner(
    *,
    offer_counts: dict | None = None,
    plan: dict | None = None,
    direct_route_index: dict | None = None,
    priority_route_viability: dict | None = None,
    synthetic_moscow_control_done: set | None = None,
) -> LiveAssemblyRunner:
    """Build a LiveAssemblyRunner with just enough state for skip-predicate tests.

    We bypass ``__init__`` by setting attributes directly so we don't need a
    real Store or flow.
    """
    runner = object.__new__(LiveAssemblyRunner)
    runner.args = _args()
    runner.store = Store()
    runner._plan_builder = lambda *a, **kw: {}  # unused in predicates
    runner.flow = None  # type: ignore[assignment]
    runner.plan = plan or {
        "routing_strategy": RoutingStrategy.RU_PRIORITY,
        "segments": [],
        "hubs": ["IST"],
        "dates": {"depart": "2026-08-01", "return": "2026-08-15"},
    }
    runner.max_searches = 200
    runner.only_carriers = []
    runner.cache_ttl_seconds = 0
    runner.use_live_cache = False
    runner.provider_policy = "kupibilet"
    runner.direct_route_index = direct_route_index
    runner.direct_route_intel = {}
    runner.segment_results: list[dict[str, Any]] = []
    runner.searches: list[dict[str, Any]] = []
    runner.failures: list[dict[str, Any]] = []
    runner.offer_counts = offer_counts or {}
    runner.synthetic_moscow_control_done = synthetic_moscow_control_done or set()
    runner.priority_route_viability = priority_route_viability or {}
    runner.request_deduper = None  # type: ignore[assignment]
    runner.probe_ledger = None  # type: ignore[assignment]
    return runner


# ---------------------------------------------------------------------------
# provider_city_code_side
# ---------------------------------------------------------------------------

class TestProviderCityCodeSide(unittest.TestCase):
    def test_returns_true_when_code_matches_city(self) -> None:
        spec = {"provider_city_code": "MOW", "origin": "MOW", "destination": "IST"}
        self.assertTrue(provider_city_code_side(spec, "origin"))

    def test_returns_true_when_code_in_deferred_airports(self) -> None:
        spec = {"provider_city_code": "MOW", "origin": "SVO", "destination": "IST"}
        # SVO is in KUPIBILET_CITY_CODE_FIRST_AIRPORTS["MOW"]
        self.assertTrue(provider_city_code_side(spec, "origin"))

    def test_returns_false_when_no_city_code(self) -> None:
        spec = {"origin": "SVO", "destination": "IST"}
        self.assertFalse(provider_city_code_side(spec, "origin"))

    def test_returns_false_when_code_not_matching(self) -> None:
        spec = {"provider_city_code": "MOW", "origin": "LED", "destination": "IST"}
        self.assertFalse(provider_city_code_side(spec, "origin"))


# ---------------------------------------------------------------------------
# endpoint_group_code
# ---------------------------------------------------------------------------

class TestEndpointGroupCode(unittest.TestCase):
    def test_returns_city_code_when_provider_side(self) -> None:
        spec = {"provider_city_code": "MOW", "origin": "SVO", "destination": "IST"}
        self.assertEqual(endpoint_group_code(spec, "origin"), "MOW")

    def test_returns_airport_code_when_not_provider_side(self) -> None:
        spec = {"provider_city_code": "MOW", "origin": "SVO", "destination": "IST"}
        self.assertEqual(endpoint_group_code(spec, "destination"), "IST")


# ---------------------------------------------------------------------------
# city_code_primary_keys_for_deferred_airport
# ---------------------------------------------------------------------------

class TestCityCodePrimaryKeysForDeferredAirport(unittest.TestCase):
    def test_returns_empty_when_not_deferred(self) -> None:
        spec = {"direction": "outbound", "leg": "origin_to_hub", "origin": "SVO", "destination": "IST"}
        self.assertEqual(city_code_primary_keys_for_deferred_airport(spec), [])

    def test_returns_keys_for_deferred_origin(self) -> None:
        spec = {
            "deferred_for_city_code_request": True,
            "provider_city_code": "MOW",
            "direction": "outbound",
            "leg": "origin_to_hub",
            "origin": "SVO",
            "destination": "IST",
        }
        keys = city_code_primary_keys_for_deferred_airport(spec)
        self.assertEqual(keys, [("outbound", "origin_to_hub", "MOW", "IST")])

    def test_returns_keys_for_deferred_destination(self) -> None:
        spec = {
            "deferred_for_city_code_request": True,
            "provider_city_code": "MOW",
            "direction": "return",
            "leg": "hub_to_origin",
            "origin": "IST",
            "destination": "SVO",
        }
        keys = city_code_primary_keys_for_deferred_airport(spec)
        self.assertEqual(keys, [("return", "hub_to_origin", "IST", "MOW")])


# ---------------------------------------------------------------------------
# deferred_airport_priority_sides
# ---------------------------------------------------------------------------

class TestDeferredAirportPrioritySides(unittest.TestCase):
    def test_returns_empty_when_no_priority_metadata(self) -> None:
        spec = {"origin": "SVO", "destination": "IST"}
        self.assertEqual(deferred_airport_priority_sides(spec), [])

    def test_returns_deferred_side_with_tier_above_1(self) -> None:
        spec = {
            "origin": "SVO",
            "origin_airport_priority": {"tier": 2, "role": "deferred", "city_code": "MOW"},
            "destination": "IST",
        }
        sides = deferred_airport_priority_sides(spec)
        self.assertEqual(len(sides), 1)
        self.assertEqual(sides[0][0], "origin")
        self.assertEqual(sides[0][1]["tier"], 2)

    def test_includes_deferred_role_even_at_tier_1(self) -> None:
        spec = {
            "origin": "SVO",
            "origin_airport_priority": {"tier": 1, "role": "deferred", "city_code": "MOW"},
        }
        sides = deferred_airport_priority_sides(spec)
        self.assertEqual(len(sides), 1)
        self.assertEqual(sides[0][0], "origin")

    def test_skips_tier_0_non_deferred(self) -> None:
        spec = {
            "origin": "SVO",
            "origin_airport_priority": {"tier": 0, "role": "primary", "city_code": "MOW"},
        }
        self.assertEqual(deferred_airport_priority_sides(spec), [])


# ---------------------------------------------------------------------------
# plan_has_svx_direct_control
# ---------------------------------------------------------------------------

class TestPlanHasSvxDirectControl(unittest.TestCase):
    def test_returns_true_when_svx_outbound(self) -> None:
        plan = {"segments": [{"leg": Leg.DIRECT_OUTBOUND, "origin": "SVX", "destination": "BKK"}]}
        self.assertTrue(plan_has_svx_direct_control(plan))

    def test_returns_true_when_svx_return(self) -> None:
        plan = {"segments": [{"leg": Leg.DIRECT_RETURN, "origin": "BKK", "destination": "SVX"}]}
        self.assertTrue(plan_has_svx_direct_control(plan))

    def test_returns_false_when_no_svx(self) -> None:
        plan = {"segments": [{"leg": Leg.DIRECT_OUTBOUND, "origin": "MOW", "destination": "BKK"}]}
        self.assertFalse(plan_has_svx_direct_control(plan))

    def test_returns_false_when_empty_segments(self) -> None:
        self.assertFalse(plan_has_svx_direct_control({"segments": []}))
        self.assertFalse(plan_has_svx_direct_control({}))


# ---------------------------------------------------------------------------
# _skipped_by_direct_route_intel
# ---------------------------------------------------------------------------

class TestSkippedByDirectRouteIntel(unittest.TestCase):
    def test_returns_none_when_no_direct_route_index(self) -> None:
        runner = _runner(direct_route_index=None)
        spec = {"leg": Leg.DIRECT_OUTBOUND, "origin": "SVX", "destination": "BKK"}
        self.assertIsNone(runner._skipped_by_direct_route_intel(spec))

    def test_returns_none_when_not_direct_leg(self) -> None:
        runner = _runner(direct_route_index={"routes": {}})
        spec = {"leg": Leg.ORIGIN_TO_HUB, "origin": "SVX", "destination": "IST"}
        self.assertIsNone(runner._skipped_by_direct_route_intel(spec))

    def test_skips_when_airport_not_in_route_set(self) -> None:
        runner = _runner(direct_route_index={
            "routes": {"outbound": ["BKK", "IST"], "return": ["SVX"]},
            "source": "svx-route-index",
            "fetched_at": "2026-01-01",
        })
        spec = {"leg": Leg.DIRECT_OUTBOUND, "origin": "SVX", "destination": "HKT"}
        result = runner._skipped_by_direct_route_intel(spec)
        self.assertIsNotNone(result)
        self.assertEqual(result["reason"], "direct_route_schedule_negative")
        self.assertEqual(result["skipped_because"]["checked_airport"], "HKT")

    def test_does_not_skip_when_airport_in_route_set(self) -> None:
        runner = _runner(direct_route_index={
            "routes": {"outbound": ["BKK", "IST"], "return": ["SVX"]},
        })
        spec = {"leg": Leg.DIRECT_OUTBOUND, "origin": "SVX", "destination": "BKK"}
        self.assertIsNone(runner._skipped_by_direct_route_intel(spec))

    def test_returns_none_when_neither_endpoint_is_svx(self) -> None:
        runner = _runner(direct_route_index={"routes": {"outbound": ["BKK"]}})
        spec = {"leg": Leg.DIRECT_OUTBOUND, "origin": "MOW", "destination": "BKK"}
        self.assertIsNone(runner._skipped_by_direct_route_intel(spec))


# ---------------------------------------------------------------------------
# _skipped_by_condition
# ---------------------------------------------------------------------------

class TestSkippedByCondition(unittest.TestCase):
    def test_returns_none_when_no_conditions_and_no_priority(self) -> None:
        runner = _runner()
        spec = {"direction": "outbound", "leg": "origin_to_hub"}
        self.assertIsNone(runner._skipped_by_condition(spec))

    def test_skips_by_skip_if_offer_exists(self) -> None:
        runner = _runner(offer_counts={("outbound", "direct_outbound", "SVX", "BKK"): 3})
        spec = {
            "direction": "outbound",
            "leg": "direct_outbound",
            "origin": "SVX",
            "destination": "BKK",
            "skip_if_offer_exists": {
                "direction": "outbound",
                "leg": "direct_outbound",
                "origin": "SVX",
                "destination": "BKK",
            },
        }
        result = runner._skipped_by_condition(spec)
        self.assertIsNotNone(result)
        self.assertEqual(result["reason"], "direct_probe_has_offers")
        self.assertEqual(result["skipped_because"]["offer_count"], 3)

    def test_does_not_skip_when_offer_count_zero(self) -> None:
        runner = _runner(offer_counts={("outbound", "direct_outbound", "SVX", "BKK"): 0})
        spec = {
            "direction": "outbound",
            "skip_if_offer_exists": {
                "direction": "outbound",
                "leg": "direct_outbound",
                "origin": "SVX",
                "destination": "BKK",
            },
        }
        self.assertIsNone(runner._skipped_by_condition(spec))

    def test_skips_by_priority_route_viable(self) -> None:
        runner = _runner(priority_route_viability={"outbound": True})
        spec = {"direction": "outbound", "skip_if_priority_route_viable": "outbound"}
        result = runner._skipped_by_condition(spec)
        self.assertIsNotNone(result)
        self.assertEqual(result["reason"], "priority_route_viable")

    def test_does_not_skip_priority_when_not_viable(self) -> None:
        runner = _runner(priority_route_viability={"outbound": False})
        spec = {"direction": "outbound", "skip_if_priority_route_viable": "outbound"}
        self.assertIsNone(runner._skipped_by_condition(spec))


# ---------------------------------------------------------------------------
# _skipped_by_offer_keys
# ---------------------------------------------------------------------------

class TestSkippedByOfferKeys(unittest.TestCase):
    def test_returns_none_when_no_matches(self) -> None:
        runner = _runner(offer_counts={("outbound", "direct_outbound", "SVX", "BKK"): 0})
        result = runner._skipped_by_offer_keys(
            {"direction": "outbound"},
            keys=[("outbound", "direct_outbound", "SVX", "BKK")],
            reason="test_reason",
            note="test_note",
        )
        self.assertIsNone(result)

    def test_returns_skip_dict_when_matches(self) -> None:
        runner = _runner(offer_counts={("outbound", "direct_outbound", "SVX", "BKK"): 5})
        result = runner._skipped_by_offer_keys(
            {"direction": "outbound", "leg": "direct_outbound"},
            keys=[("outbound", "direct_outbound", "SVX", "BKK")],
            reason="test_reason",
            note="test_note",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "test_reason")
        self.assertEqual(result["skipped_because"]["matched_offer_counts"][0]["offer_count"], 5)


# ---------------------------------------------------------------------------
# _skipped_by_city_code_primary
# ---------------------------------------------------------------------------

class TestSkippedByCityCodePrimary(unittest.TestCase):
    def test_returns_skip_when_city_code_primary_has_offers(self) -> None:
        runner = _runner(offer_counts={("outbound", "origin_to_hub", "MOW", "IST"): 2})
        spec = {
            "deferred_for_city_code_request": True,
            "provider_city_code": "MOW",
            "direction": "outbound",
            "leg": "origin_to_hub",
            "origin": "SVO",
            "destination": "IST",
        }
        result = runner._skipped_by_city_code_primary(spec)
        self.assertIsNotNone(result)
        self.assertEqual(result["reason"], "city_code_request_has_offers")


# ---------------------------------------------------------------------------
# _priority_route_viable
# ---------------------------------------------------------------------------

class TestPriorityRouteViable(unittest.TestCase):
    def test_returns_false_when_not_ru_priority(self) -> None:
        runner = _runner(plan={"routing_strategy": RoutingStrategy.HUB_LIST, "segments": [], "hubs": [], "dates": {}})
        self.assertFalse(runner._priority_route_viable("outbound"))

    def test_returns_cached_viability(self) -> None:
        runner = _runner(priority_route_viability={"outbound": True})
        self.assertTrue(runner._priority_route_viable("outbound"))

    def test_returns_false_for_unknown_direction(self) -> None:
        runner = _runner()
        self.assertFalse(runner._priority_route_viable("sideways"))


# ---------------------------------------------------------------------------
# _ensure_moscow_gateway_control_synthesized
# ---------------------------------------------------------------------------

class TestEnsureMoscowGatewayControlSynthesized(unittest.TestCase):
    def test_does_nothing_when_already_done(self) -> None:
        runner = _runner(synthetic_moscow_control_done={"outbound", "return"})
        # Should not raise or modify anything
        runner._ensure_moscow_gateway_control_synthesized("outbound")
        self.assertEqual(runner.synthetic_moscow_control_done, {"outbound", "return"})

    def test_adds_direction_to_done_set(self) -> None:
        runner = _runner(synthetic_moscow_control_done=set())
        # We can't easily test the full synthesis without mocking
        # synthesize_moscow_gateway_control_results, but we can verify the set update
        runner.synthetic_moscow_control_done = set()
        runner.segment_results = []
        runner.searches = []
        runner.offer_counts = {}
        # Patch synthesize to return empty results
        import flights_cli.orchestrators.live_assembly_runner as runner_mod
        original = runner_mod.synthesize_moscow_gateway_control_results
        try:
            runner_mod.synthesize_moscow_gateway_control_results = lambda *a, **kw: ([], [])
            runner._ensure_moscow_gateway_control_synthesized("outbound")
            self.assertIn("outbound", runner.synthetic_moscow_control_done)
        finally:
            runner_mod.synthesize_moscow_gateway_control_results = original


# ---------------------------------------------------------------------------
# _skipped_by_preferred_airport_tier
# ---------------------------------------------------------------------------

class TestSkippedByPreferredAirportTier(unittest.TestCase):
    def test_returns_none_when_no_preferred_offers(self) -> None:
        runner = _runner(offer_counts={})
        spec = {
            "direction": "outbound",
            "leg": "origin_to_hub",
            "origin": "SVO",
            "destination": "IST",
            "origin_airport_priority": {"tier": 1, "city_code": "MOW"},
        }
        # preferred_keys_for_deferred_airport returns [] if no matching plan segments
        result = runner._skipped_by_preferred_airport_tier(spec)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# hub_viability_summary (standalone helper)
# ---------------------------------------------------------------------------

class TestHubViabilitySummary(unittest.TestCase):
    def test_marks_hub_viable_when_all_required_legs_have_offers(self) -> None:
        plan = {
            "hubs": ["IST"],
            "dates": {"depart": "2026-08-01", "return": "2026-08-15"},
        }
        searches = [
            {"leg": Leg.ORIGIN_TO_HUB, "destination": "IST", "offer_count": 1, "date": "2026-08-01"},
            {"leg": Leg.HUB_TO_DESTINATION, "origin": "IST", "offer_count": 2, "date": "2026-08-01"},
            {"leg": Leg.DESTINATION_TO_HUB, "destination": "IST", "offer_count": 1, "date": "2026-08-15"},
            {"leg": Leg.HUB_TO_ORIGIN, "origin": "IST", "offer_count": 3, "date": "2026-08-15"},
        ]
        result = hub_viability_summary(plan, searches)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["viable"])
        self.assertEqual(result[0]["total_offer_count"], 7)
        self.assertEqual(result[0]["missing_legs"], [])

    def test_marks_hub_not_viable_when_missing_legs(self) -> None:
        plan = {
            "hubs": ["IST"],
            "dates": {"depart": "2026-08-01", "return": "2026-08-15"},
        }
        searches = [
            {"leg": Leg.ORIGIN_TO_HUB, "destination": "IST", "offer_count": 1, "date": "2026-08-01"},
        ]
        result = hub_viability_summary(plan, searches)
        self.assertFalse(result[0]["viable"])
        self.assertIn(Leg.HUB_TO_DESTINATION, result[0]["missing_legs"])


if __name__ == "__main__":
    unittest.main()