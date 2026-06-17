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

from flights_cli.orchestrators.live_assemble import build_live_route_segment_plan
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
    EXPECTED_HASH = "2b5c44e99d229f2745ee9ff1c1ad0e10bf1262244f27d4f59df8d9728579c0df"

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
    EXPECTED_HASH = "4dd041d7598f4f3033945effaf239590ba9edb096d7486ec1cc80efe4d4a2121"

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
    EXPECTED_HASH = "b1a05c21ef9bf332bb919fd11292874a7ee8ad56746d9134bec2424f777c063a"

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
    EXPECTED_HASH = "d91a35ad6eff6c3a655dace5333270d48ccc9b0290f2cc91b818db214e82c31c"

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
    EXPECTED_HASH = "7cdd158193f57be48c0834c5bf3eb2e52bce3588e54d40bd9d344cac2ff9e5b9"

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
    EXPECTED_HASH = "1edd1795ecb049d489fba1f071aeb8928b56acf84ae2be5a5fe5199db15c158c"

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
    EXPECTED_HASH = "3e56784412bcd1730701cb05c3e3572b51f9185521a970885dfedb5eafd9450f"

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
    EXPECTED_HASH = "4299e49b2266d107c9597ea34fef28f6dee49c35d2b12297f6157e3d18534405"

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