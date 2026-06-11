from __future__ import annotations

import unittest
from unittest.mock import patch

from flights_cli.errors import CliError
from flights_cli.execution.probe_dispatcher import SegmentProbeOutcome
from flights_cli.orchestrators.live_assemble import build_live_route_segment_plan, run_live_route_assembly
from flights_cli.pipeline.search_pipeline import build_live_route_search_flow
from flights_cli.store import Store
from helpers import live_assembly_args


def window_args(**overrides: object):
    values: dict[str, object] = {
        "origin": "SVX",
        "destination": "LED",
        "depart_date": "2026-08-16",
        "date_window_end": "2026-08-18",
        "origin_airports": ["SVX"],
        "destination_airports": ["LED"],
        "max_connections": 0,
        "fallback_max_connections": 0,
        "no_live_cache": True,
        "no_direct_route_intel": True,
        "coverage_mode": "targeted",
        "agent_brief": True,
    }
    values.update(overrides)
    return live_assembly_args(**values)


def _offer(date_text: str) -> dict[str, object]:
    return {
        "origin": "SVX",
        "destination": "LED",
        "departure_at": f"{date_text}T08:10:00+05:00",
        "arrival_at": f"{date_text}T09:30:00+03:00",
        "carrier": "SU",
        "flight_number": "SU1407",
        "price": 12345,
        "currency": "RUB",
    }


def _dispatch_by_date(spec, **_kwargs):
    date_text = str(spec.get("date"))
    base = {
        "direction": spec.get("direction"),
        "leg": spec.get("leg"),
        "origin": spec.get("origin"),
        "destination": spec.get("destination"),
        "date": date_text,
        "provider": "kupibilet",
        "probe_id": f"probe-{date_text}",
        "cache_status": "live",
    }
    if date_text == "2026-08-16":
        summary = {**base, "status": "ok", "offer_count": 1}
        segment_result = {
            "direction": spec.get("direction"),
            "leg": spec.get("leg"),
            "origin": spec.get("origin"),
            "destination": spec.get("destination"),
            "date": date_text,
            "offers": [_offer(date_text)],
        }
        return [SegmentProbeOutcome(summary=summary, segment_result=segment_result)]
    if date_text == "2026-08-17":
        summary = {**base, "status": "ok", "offer_count": 0}
        segment_result = {
            "direction": spec.get("direction"),
            "leg": spec.get("leg"),
            "origin": spec.get("origin"),
            "destination": spec.get("destination"),
            "date": date_text,
            "offers": [],
        }
        return [SegmentProbeOutcome(summary=summary, segment_result=segment_result)]
    summary = {**base, "status": "error", "offer_count": 0, "error": "upstream timeout"}
    failure = {"layer": "provider", "origin": spec.get("origin"), "destination": spec.get("destination"), "date": date_text, "error": "upstream timeout"}
    return [SegmentProbeOutcome(summary=summary, segment_result=None, failure=failure)]


class DateWindowPlanTests(unittest.TestCase):
    def test_window_expands_into_per_date_direct_segments_and_controls(self) -> None:
        args = window_args()
        plan = build_live_route_segment_plan(args, Store())

        segment_dates = sorted({str(spec.get("date")) for spec in plan["segments"]})
        self.assertEqual(segment_dates, ["2026-08-16", "2026-08-17", "2026-08-18"])
        self.assertTrue(all(spec.get("leg") == "direct_outbound" for spec in plan["segments"]))
        self.assertTrue(all(spec.get("route_family") == "direct_inventory" for spec in plan["segments"]))
        self.assertEqual(plan["metrics"]["segment_search_count"], 3)
        self.assertEqual(plan["dates"].get("window_end"), "2026-08-18")

        control_dates = sorted(
            {
                str(control.get("date"))
                for control in plan["coverage_controls"]
                if control.get("type") == "exact_airport_direct" and control.get("direction") == "outbound"
            }
        )
        self.assertEqual(control_dates, ["2026-08-16", "2026-08-17", "2026-08-18"])

    def test_window_requires_direct_only_route_options(self) -> None:
        with self.assertRaises(CliError):
            build_live_route_segment_plan(window_args(max_connections=None, fallback_max_connections=None), Store())

    def test_window_rejects_return_date(self) -> None:
        with self.assertRaises(CliError):
            build_live_route_segment_plan(window_args(return_date="2026-08-20"), Store())

    def test_window_end_must_not_precede_depart_date(self) -> None:
        with self.assertRaises(CliError):
            build_live_route_segment_plan(window_args(date_window_end="2026-08-15"), Store())

    def test_window_is_bounded(self) -> None:
        with self.assertRaises(CliError):
            build_live_route_segment_plan(window_args(date_window_end="2026-09-30"), Store())

    def test_required_controls_include_date_window_direct(self) -> None:
        flow = build_live_route_search_flow(window_args())
        self.assertIn("date_window_direct", flow.evidence_plan.required_controls)
        self.assertEqual(flow.flow_decision.intent_class, "direct_inventory")


class DateWindowInventoryProjectionTests(unittest.TestCase):
    def test_runner_projects_per_date_inventory_into_report_evidence(self) -> None:
        args = window_args()
        with patch("flights_cli.orchestrators.live_assemble.dispatch_segment_probe", side_effect=_dispatch_by_date):
            result = run_live_route_assembly(args, Store())

        inventory = result["live_search"].get("date_window_inventory")
        self.assertIsInstance(inventory, dict)
        entries = {entry["date"]: entry for entry in inventory["dates"]}
        self.assertEqual(sorted(entries), ["2026-08-16", "2026-08-17", "2026-08-18"])
        self.assertEqual(entries["2026-08-16"]["status"], "direct_offers")
        self.assertEqual(entries["2026-08-16"]["offer_count"], 1)
        first_offer = entries["2026-08-16"]["offers"][0]
        self.assertEqual(first_offer["carrier"], "SU")
        self.assertEqual(first_offer["flight_number"], "SU1407")
        self.assertEqual(first_offer["price"], 12345)
        self.assertEqual(entries["2026-08-17"]["status"], "no_direct_offers")
        self.assertEqual(entries["2026-08-18"]["status"], "probe_failed")
        self.assertEqual(inventory.get("boundary"), "provider_live_only")

        report = result.get("agent_report")
        self.assertIsInstance(report, dict)
        self.assertIn("date_window_inventory", report["evidence"])
        report_dates = [entry["date"] for entry in report["evidence"]["date_window_inventory"]["dates"]]
        self.assertEqual(sorted(report_dates), ["2026-08-16", "2026-08-17", "2026-08-18"])


if __name__ == "__main__":
    unittest.main()
