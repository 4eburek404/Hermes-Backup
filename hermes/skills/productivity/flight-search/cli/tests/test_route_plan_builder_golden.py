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
    EXPECTED_HASH = "7c45ebb80ceb6789d754cdcd1f6166a635fcff186f977a4b2800e32675c9aed9"

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
    EXPECTED_HASH = "cffe91845b8963b26de4cd3a4aec7950c2e4bc17f870dc93de83ee8cfdddbdf0"

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
    EXPECTED_HASH = "ba02afe09b56307c5595fcabbe0640bac1907b424e339507538eb76eb45d3b95"

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
    EXPECTED_HASH = "2205676827d703044efbc6c710fecfc0641e7fb48aaf2e641059e83237955ce0"

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
    EXPECTED_HASH = "78937b9997b11d10dfca53d2df395ed1e7cb0010de52428bf8ff438a84a525df"

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
    EXPECTED_HASH = "37c2a65bc6358e2a5a4c57c9850103a0fb2173d63c7b24bbddb1ebba3091d300"

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
    EXPECTED_HASH = "44108f7c9fa8c2c7f86369536301440af2b3fb6aef0094943a256795e9866ff6"

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
    EXPECTED_HASH = "bd1ea23d3b069c4b4c33e3f8aa57f26bd554eef5c75b19df517caad9bcc4f8fd"

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
