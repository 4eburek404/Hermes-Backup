from __future__ import annotations

import unittest

from flights_cli.cli import build_parser
from flights_cli.providers.u6 import parse_u6_calendar


class U6CalendarTests(unittest.TestCase):
    def test_parse_u6_calendar_normal_data(self) -> None:
        raw = {
            "dates": [
                {"date": "2026-07-01", "price": {"code": "RUB", "price": 25000}},
                {"date": "2026-07-19", "price": {"code": "RUB", "price": 20948}},
                {"date": "2026-07-25", "price": {"code": "RUB", "price": 34000}},
                {"date": "2026-07-30", "price": {"code": "RUB", "price": 15000}},
            ],
            "finalDate": "2026-09-30",
        }
        result = parse_u6_calendar(raw, "SVX", "IST")
        self.assertTrue(result["ok"])
        self.assertFalse(result["empty"])
        self.assertEqual(result["priced_dates"], 4)
        self.assertEqual(result["stats"]["min"], 15000)
        self.assertEqual(result["stats"]["max"], 34000)
        self.assertEqual(result["stats"]["avg"], 23737)
        # default sort by price ascending
        self.assertEqual(result["results"][0]["price"], 15000)
        self.assertEqual(result["results"][-1]["price"], 34000)
        self.assertIn("cross_check_commands", result)

    def test_parse_u6_calendar_skips_malformed_entries(self) -> None:
        raw = {
            "dates": [
                None,
                {"date": "2026-07-01", "price": None},
                {"date": "2026-07-02", "price": {"code": "RUB", "price": "12000"}},
                {"date": "2026-07-03", "price": {"code": "RUB", "price": "not-a-price"}},
                {"date": "2026-07-04", "price": {"code": 5, "price": 13000}},
            ],
            "finalDate": "2026-09-30",
        }

        result = parse_u6_calendar(raw, "SVX", "IST", sort_by="date")

        self.assertTrue(result["ok"])
        self.assertEqual(result["total_dates"], 5)
        self.assertEqual(result["priced_dates"], 2)
        self.assertEqual(result["unpriced_dates"], 3)
        self.assertEqual([entry["price"] for entry in result["results"]], [12000, 13000])
        self.assertEqual(result["results"][1]["currency"], "RUB")

    def test_parse_u6_calendar_selected_date_filter(self) -> None:
        raw = {
            "dates": [
                {"date": "2026-07-19", "price": {"code": "RUB", "price": 20948}},
                {"date": "2026-07-20", "price": {"code": "RUB", "price": 22000}},
            ],
            "finalDate": "2026-09-30",
        }
        result = parse_u6_calendar(raw, "SVX", "IST", selected_date="2026-07-19")
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["date"], "2026-07-19")
        self.assertEqual(result["priced_dates"], 1)

    def test_parse_u6_calendar_empty_response_not_an_error(self) -> None:
        """Empty response is not a hard error - it's a signal."""
        result = parse_u6_calendar(None, "SVX", "XYZ")
        self.assertFalse(result["ok"])
        self.assertTrue(result["empty"])
        self.assertEqual(result["empty_reason"], "empty_body")
        self.assertEqual(len(result["results"]), 0)
        self.assertIn("cross_check_commands", result)

    def test_parse_u6_calendar_no_dates_key(self) -> None:
        result = parse_u6_calendar({"something": "else"}, "SVX", "IST")
        self.assertFalse(result["ok"])
        self.assertTrue(result["empty"])
        self.assertEqual(result["empty_reason"], "no_dates_key")

    def test_parse_u6_calendar_price_filters(self) -> None:
        raw = {
            "dates": [
                {"date": "2026-07-01", "price": {"code": "RUB", "price": 10000}},
                {"date": "2026-07-02", "price": {"code": "RUB", "price": 20000}},
                {"date": "2026-07-03", "price": {"code": "RUB", "price": 30000}},
            ],
        }
        result = parse_u6_calendar(raw, "SVX", "IST", min_price=15000, max_price=25000)
        self.assertEqual(result["priced_dates"], 1)
        self.assertEqual(result["results"][0]["price"], 20000)

    def test_parse_u6_calendar_sort_by_date(self) -> None:
        raw = {
            "dates": [
                {"date": "2026-07-03", "price": {"code": "RUB", "price": 30000}},
                {"date": "2026-07-01", "price": {"code": "RUB", "price": 20000}},
            ],
        }
        result = parse_u6_calendar(raw, "SVX", "IST", sort_by="date")
        self.assertEqual(result["results"][0]["date"], "2026-07-01")
        self.assertEqual(result["results"][1]["date"], "2026-07-03")

    def test_parse_u6_calendar_limit(self) -> None:
        raw = {
            "dates": [
                {"date": f"2026-07-{i:02d}", "price": {"code": "RUB", "price": i * 1000}}
                for i in range(1, 11)
            ],
        }
        result = parse_u6_calendar(raw, "SVX", "IST", limit=3)
        self.assertEqual(len(result["results"]), 3)
        self.assertEqual(result["priced_dates"], 10)  # full count

    def test_u6_prices_parser_accepts_new_args(self) -> None:
        args = build_parser().parse_args(
            [
                "u6-prices",
                "SVX",
                "IST",
                "--from-date",
                "2026-07-19",
                "--date",
                "2026-07-19",
                "--sort",
                "price",
                "--limit",
                "5",
                "--min-price",
                "10000",
                "--max-price",
                "50000",
            ]
        )
        self.assertEqual(args.command_name, "u6-prices")
        self.assertEqual(args.origin, "SVX")
        self.assertEqual(args.selected_date, "2026-07-19")
        self.assertEqual(args.sort, "price")
        self.assertEqual(args.limit, 5)
        self.assertEqual(args.min_price, 10000)
        self.assertEqual(args.max_price, 50000)


if __name__ == "__main__":
    unittest.main()
