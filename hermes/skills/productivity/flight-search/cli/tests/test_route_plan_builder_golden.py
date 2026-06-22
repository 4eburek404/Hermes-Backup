"""Golden tests for build_live_route_segment_plan — freeze output before refactoring.

Run with: PYTHONPATH=. python -m pytest tests/test_route_plan_builder_golden.py -v

These tests snapshot the plan dict (segments, route_families, coverage_controls, etc.)
for each strategy × direction combination.  Any refactor of the planner must produce
byte-identical output; if these tests break, the refactor changed behaviour.
"""
from __future__ import annotations

import hashlib
import json
import unittest

from flights_cli.orchestrators.live_route_assembly import build_live_route_segment_plan
from flights_cli.store import Store
from helpers import live_assembly_args


def _normalize_for_json(obj):
    """Recursively normalize a plan dict to JSON-safe primitives."""
    if isinstance(obj, dict):
        return {k: _normalize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_for_json(v) for v in obj]
    if isinstance(obj, (set, frozenset, tuple)):
        return [_normalize_for_json(v) for v in sorted(obj, key=repr)]
    if hasattr(obj, "value"):
        # Enum members → their string value
        return obj.value
    if hasattr(obj, "isoformat"):
        # date/datetime → ISO string
        return obj.isoformat()
    return obj


def _plan_snapshot(plan: dict) -> str:
    """Deterministic JSON snapshot: sort keys, normalize enums and dates."""
    normalized = _normalize_for_json(plan)
    return json.dumps(normalized, sort_keys=True)


def _plan_hash(plan: dict) -> str:
    return hashlib.sha256(_plan_snapshot(plan).encode()).hexdigest()


class _GoldenPlanMixin:
    """Subclasses set STRATEGY and DIRECTION overrides."""

    STRATEGY: str
    DIRECTION: str
    EXPECTED_HASH: str | None = None

    def _make_args(self):
        overrides: dict = {
            "routing_strategy": self.STRATEGY,
            "no_direct_route_intel": True,
            "no_live_cache": True,
        }
        if self.DIRECTION == "one-way":
            overrides["return_date"] = None
        return live_assembly_args(**overrides)

    def test_plan_segment_count(self):
        plan = build_live_route_segment_plan(self._make_args(), Store())
        self.assertGreater(len(plan["segments"]), 0)

    def test_plan_snapshot_hash(self):
        plan = build_live_route_segment_plan(self._make_args(), Store())
        h = _plan_hash(plan)
        if self.EXPECTED_HASH is None:
            self.skipTest(f"Set EXPECTED_HASH = \"{h}\"")
        self.assertEqual(
            h,
            self.EXPECTED_HASH,
            f"Snapshot changed! New hash: {h}\nFirst segment: {plan['segments'][0] if plan['segments'] else 'none'}",
        )

    def test_plan_strategy_matches(self):
        plan = build_live_route_segment_plan(self._make_args(), Store())
        self.assertEqual(plan["routing_strategy"], self.STRATEGY)


class TestDirectOnlyRoundTrip(_GoldenPlanMixin, unittest.TestCase):
    STRATEGY = "ru-priority"
    DIRECTION = "round-trip"
    EXPECTED_HASH = "19014d6d0df3cacadd5ae5a8925dfff1ba553564fe10a3b4e761f78e2e7fe814"

    def _make_args(self):
        return live_assembly_args(
            origin="SVX",
            destination="CDG",
            depart_date="2026-08-15",
            return_date="2026-08-19",
            max_connections=0,
            tier2_max_connections=0,
            no_direct_route_intel=True,
            no_live_cache=True,
        )


class TestDirectOnlyOneWay(_GoldenPlanMixin, unittest.TestCase):
    STRATEGY = "ru-priority"
    DIRECTION = "one-way"
    EXPECTED_HASH = "ecdf9d59348fd76ac78829c03701417d6c190cec9a8be80e80bffe800da15c2e"

    def _make_args(self):
        return live_assembly_args(
            origin="SVX",
            destination="CDG",
            depart_date="2026-08-15",
            return_date=None,
            max_connections=0,
            tier2_max_connections=0,
            date_window_end="2026-08-20",
            no_direct_route_intel=True,
            no_live_cache=True,
        )


class TestRuPriorityRoundTrip(_GoldenPlanMixin, unittest.TestCase):
    STRATEGY = "ru-priority"
    DIRECTION = "round-trip"
    EXPECTED_HASH = "c74ae090fa0cdfe4c3e629375e7339d261130d08f77421273e6e3da2b92a2cba"

    def _make_args(self):
        return live_assembly_args(
            routing_strategy=self.STRATEGY,
            origin="SVX",
            destination="CDG",
            depart_date="2026-08-15",
            return_date="2026-08-19",
            no_direct_route_intel=True,
            no_live_cache=True,
        )


class TestRuPriorityOneWay(_GoldenPlanMixin, unittest.TestCase):
    STRATEGY = "ru-priority"
    DIRECTION = "one-way"
    EXPECTED_HASH = "0cfcc571073758d5f4d780de43bd4ea0cceb6839dcfe35a686c2aaba0d0e73d4"

    def _make_args(self):
        return live_assembly_args(
            routing_strategy=self.STRATEGY,
            origin="SVX",
            destination="CDG",
            depart_date="2026-08-15",
            return_date=None,
            no_direct_route_intel=True,
            no_live_cache=True,
        )


class TestDomesticRuRoundTrip(_GoldenPlanMixin, unittest.TestCase):
    STRATEGY = "domestic-ru"
    DIRECTION = "round-trip"
    EXPECTED_HASH = "d2bcdb6fcfec331cf238303886b0e6665b1e94848abb2e8838a2bb6f21a1c74d"

    def _make_args(self):
        return live_assembly_args(
            routing_strategy=self.STRATEGY,
            origin="SVX",
            destination="LED",
            depart_date="2026-08-15",
            return_date="2026-08-19",
            no_direct_route_intel=True,
            no_live_cache=True,
        )


class TestDomesticRuOneWay(_GoldenPlanMixin, unittest.TestCase):
    STRATEGY = "domestic-ru"
    DIRECTION = "one-way"
    EXPECTED_HASH = "28ba2125c38cf25c25b0e5b9704a538d9422c6eca56649037142652f7b61a945"

    def _make_args(self):
        return live_assembly_args(
            routing_strategy=self.STRATEGY,
            origin="SVX",
            destination="LED",
            depart_date="2026-08-15",
            return_date=None,
            no_direct_route_intel=True,
            no_live_cache=True,
        )


class TestHubListRoundTrip(_GoldenPlanMixin, unittest.TestCase):
    STRATEGY = "hub-list"
    DIRECTION = "round-trip"
    EXPECTED_HASH = "eb34cae3ee4561d0dcb3e6cc747c7d24a59e811618edb2147d6607cebb0f5d44"

    def _make_args(self):
        return live_assembly_args(
            routing_strategy=self.STRATEGY,
            origin="NCE",
            destination="HND",
            depart_date="2026-08-15",
            return_date="2026-08-19",
            hub=["IST"],
            no_direct_route_intel=True,
            no_live_cache=True,
        )


class TestHubListOneWay(_GoldenPlanMixin, unittest.TestCase):
    STRATEGY = "hub-list"
    DIRECTION = "one-way"
    EXPECTED_HASH = "49f20384585e98aebaac2de814b7417b1a502d8d88b94c62029b01911e9a34f4"

    def _make_args(self):
        return live_assembly_args(
            routing_strategy=self.STRATEGY,
            origin="NCE",
            destination="HND",
            depart_date="2026-08-15",
            return_date=None,
            hub=["IST"],
            no_direct_route_intel=True,
            no_live_cache=True,
        )
