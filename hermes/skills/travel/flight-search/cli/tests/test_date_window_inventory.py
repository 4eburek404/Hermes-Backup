from __future__ import annotations

import contextlib
import io
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from flights_cli.cli import build_parser
from flights_cli.errors import CliError
from flights_cli.orchestrators.search_workflow import SearchWorkflow
from flights_cli.orchestrators.search_plan_builder import (
    build_route_context,
)
from flights_cli.pipeline.result_builder import build_result_projection
from flights_cli.store import Store
from helpers import build_search_plan, future_departure_date, live_assembly_args


def execute_projection(*args: object, **kwargs: object) -> dict:
    request, store = args
    return SearchWorkflow(store).run_artifacts(request).projection_input


def window_args(depart: date, **overrides: object):
    values: dict[str, object] = {
        "origin": "SVX",
        "destination": "LED",
        "depart_date": depart.isoformat(),
        "date_window_end": (depart + timedelta(days=2)).isoformat(),
        "origin_airports": ["SVX"],
        "destination_airports": ["LED"],
        "max_connections": 0,
        "tier2_max_connections": 0,
        "no_live_cache": True,
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


def _primary_results_by_query(queries, *_args, **_kwargs):
    results = []
    emitted_offer_dates: set[str] = set()
    ordered_dates = sorted({str(query.get("date")) for query in queries})
    if not ordered_dates:
        return results
    first_date = ordered_dates[0]
    second_date = ordered_dates[min(1, len(ordered_dates) - 1)]
    for query in queries:
        date_text = str(query.get("date"))
        provider = query.get("provider") or "tutu"
        base = {
            "role": "primary_offer_collection",
            "source_type": "provider_full_route",
            "direction": query.get("direction"),
            "origin": query.get("origin"),
            "destination": query.get("destination"),
            "date": date_text,
            "provider": provider,
            "probe_id": f"probe-{date_text}",
            "cache_status": "live",
            "filters": {"direct_only": True, "only_carriers": []},
            "direct_only": True,
        }
        if date_text == first_date and date_text not in emitted_offer_dates:
            emitted_offer_dates.add(date_text)
            results.append(
                {
                    **base,
                    "status": "ok",
                    "offer_count": 1,
                    "top_offers": [_offer(date_text)],
                }
            )
            continue
        if date_text in {first_date, second_date}:
            results.append({**base, "status": "ok", "offer_count": 0, "top_offers": []})
            continue
        results.append(
            {
                **base,
                "status": "error",
                "execution_state": "failed",
                "offer_count": 0,
                "top_offers": [],
                "error": "upstream timeout",
            }
        )
    return results


class DateWindowPlanTests(unittest.TestCase):
    def test_date_window_end_is_request_only_not_cli_flag(self) -> None:
        for argv in (
            ["search", "--request", "request.json", "--date-window-end", "2026-08-18"],
        ):
            with self.subTest(argv=argv):
                with (
                    contextlib.redirect_stderr(io.StringIO()),
                    self.assertRaises(SystemExit),
                ):
                    build_parser().parse_args(argv)

    def test_window_expands_into_per_date_direct_provider_queries(self) -> None:
        depart = future_departure_date()
        args = window_args(depart)
        plan = build_route_context(args, Store())
        search_plan = build_search_plan(args, Store())

        query_dates = sorted(
            {
                str(attempt["query"].get("date"))
                for attempt in search_plan["phases"]["primary"]
            }
        )
        expected_dates = [
            (depart + timedelta(days=offset)).isoformat() for offset in range(3)
        ]
        self.assertEqual(query_dates, expected_dates)
        self.assertTrue(
            all(
                attempt["query"].get("direct_only")
                for attempt in search_plan["phases"]["primary"]
            )
        )
        self.assertTrue(
            all(
                attempt["query"].get("route_family") == "direct_inventory"
                for attempt in search_plan["phases"]["primary"]
            )
        )
        self.assertEqual(plan["dates"].get("window_end"), expected_dates[-1])

    def test_window_requires_direct_only_route_options(self) -> None:
        depart = future_departure_date()
        with self.assertRaises(CliError):
            build_search_plan(
                window_args(depart, max_connections=None, tier2_max_connections=None),
                Store(),
            )

    def test_window_rejects_return_date(self) -> None:
        depart = future_departure_date()
        with self.assertRaises(CliError):
            build_search_plan(
                window_args(
                    depart, return_date=(depart + timedelta(days=4)).isoformat()
                ),
                Store(),
            )

    def test_window_end_must_not_precede_depart_date(self) -> None:
        depart = future_departure_date()
        with self.assertRaises(CliError):
            build_search_plan(
                window_args(
                    depart, date_window_end=(depart - timedelta(days=1)).isoformat()
                ),
                Store(),
            )

    def test_window_is_bounded(self) -> None:
        depart = future_departure_date()
        with self.assertRaises(CliError):
            build_search_plan(
                window_args(
                    depart, date_window_end=(depart + timedelta(days=45)).isoformat()
                ),
                Store(),
            )


class DateWindowInventoryProjectionTests(unittest.TestCase):
    def test_runner_projects_per_date_inventory_into_report_evidence(self) -> None:
        depart = future_departure_date()
        args = window_args(depart)
        with patch(
            "flights_cli.execution.search_executor.run_primary_offer_queries",
            side_effect=_primary_results_by_query,
        ):
            result = execute_projection(args, Store())

        inventory = result["live_search"].get("date_window_inventory")
        self.assertIsInstance(inventory, dict)
        entries = {entry["date"]: entry for entry in inventory["dates"]}
        expected_dates = [
            (depart + timedelta(days=offset)).isoformat() for offset in range(3)
        ]
        self.assertEqual(sorted(entries), expected_dates)
        self.assertEqual(entries[expected_dates[0]]["status"], "direct_offers")
        self.assertEqual(entries[expected_dates[0]]["offer_count"], 1)
        first_offer = entries[expected_dates[0]]["offers"][0]
        self.assertEqual(first_offer["carrier"], "SU")
        self.assertEqual(first_offer["flight_number"], "SU1407")
        self.assertEqual(first_offer["price"], 12345)
        self.assertEqual(entries[expected_dates[1]]["status"], "no_direct_offers")
        self.assertEqual(entries[expected_dates[2]]["status"], "probe_failed")
        self.assertEqual(inventory.get("boundary"), "provider_live_only")

        report = build_result_projection(result)
        self.assertIsInstance(report, dict)
        self.assertIn("date_window_inventory", report["evidence"])
        report_dates = [
            entry["date"]
            for entry in report["evidence"]["date_window_inventory"]["dates"]
        ]
        self.assertEqual(sorted(report_dates), expected_dates)


if __name__ == "__main__":
    unittest.main()
