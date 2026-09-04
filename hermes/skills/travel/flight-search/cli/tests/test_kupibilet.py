from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from flights_cli.adapters.providers.kupibilet_adapter import (
    KupibiletProviderAdapter,
    kupibilet_aggregate_search_summary,
)
from flights_cli.providers.kupibilet import (
    build_kupibilet_payload,
    cached_kupibilet_search,
    kupibilet_flight_number,
    parse_kupibilet_frontend_search,
)
from flights_cli.providers.live_cache import (
    live_cache_key,
    read_live_cache,
    write_live_cache,
)

from helpers import CliSubprocessMixin, future_departure_date


def airport_scope_raw(rows: list[tuple[str, str, str, int]]) -> dict:
    variants = []
    flights = {}
    for index, (offer_id, origin, destination, price) in enumerate(rows):
        flight_id = f"flight-{index}"
        variants.append(
            {
                "id": offer_id,
                "price": {"amount": str(price), "currency": "RUB"},
                "segments": [{"flights": [flight_id]}],
            }
        )
        flights[flight_id] = {
            "marketing_carrier": "ZZ",
            "operating_carrier": "ZZ",
            "transport_number": str(index + 1),
            "departure": origin,
            "arrival": destination,
            "departure_datetime": f"2026-08-12T{index:02d}:00:00+00:00",
            "arrival_datetime": f"2026-08-12T{index + 1:02d}:00:00+00:00",
            "duration": 60,
            "transport_kind": "airplane",
        }
    return {"variants": variants, "flights": flights}


class KupibiletTests(CliSubprocessMixin, unittest.TestCase):
    def test_adapter_does_not_repeat_parser_stop_filtering(self) -> None:
        summary = kupibilet_aggregate_search_summary(
            direction="outbound",
            origin="SVX",
            destination="AMS",
            depart_date="2026-08-12",
            carriers=[],
            direct_only=False,
            result={
                "source": "test",
                "raw_offer_count": 2,
                "suppressed_three_plus_count": 1,
                "suppressed_airport_change_count": 0,
                "offers": [
                    {
                        "id": "parser-output",
                        "price": 10_000,
                        "currency": "RUB",
                        "number_of_changes": 3,
                        "segments": [],
                    }
                ],
            },
        )

        self.assertEqual(summary["offer_count"], 1)
        self.assertEqual(summary["raw_offer_count"], 2)
        self.assertEqual(summary["suppressed_three_plus_count"], 1)
        self.assertEqual(summary["top_offers"][0]["id"], "parser-output")

    def test_kupibilet_payload_uses_live_frontend_search_shape(self) -> None:
        payload = build_kupibilet_payload("SVX", "MOW", "2026-07-19", "RUB")

        self.assertEqual(
            payload["trips"],
            [{"departure": "SVX", "arrival": "MOW", "date": "2026-07-19"}],
        )
        self.assertEqual(payload["travelers"], {"adult": 1, "child": 0, "infant": 0})
        self.assertEqual(payload["cabin"], "economy")
        self.assertEqual(payload["sort_by"], "price")
        self.assertFalse(payload["short_response"])

    def test_parse_kupibilet_filters_airport_scope_before_limit(self) -> None:
        raw = airport_scope_raw(
            [
                ("wrong-cheap", "AAA", "BBC", 1000),
                ("allowed", "AAA", "BBB", 5000),
                ("missing-airport", "AAA", "", 500),
            ]
        )

        result = parse_kupibilet_frontend_search(
            raw,
            origin="AAA",
            destination="CTY",
            depart_date="2026-08-12",
            currency="RUB",
            origin_airports=[" aaa ", "AAA"],
            destination_airports=["BBB"],
            limit=1,
        )

        self.assertEqual([offer["id"] for offer in result["offers"]], ["allowed"])
        self.assertEqual(result["filters"]["origin_airports"], ["AAA"])
        self.assertEqual(result["filters"]["destination_airports"], ["BBB"])
        self.assertEqual(result["skipped"]["destination_out_of_scope"], 1)
        self.assertEqual(result["skipped"]["missing_airport"], 1)

    def test_parse_kupibilet_supports_independent_multi_airport_scopes(self) -> None:
        raw = airport_scope_raw(
            [
                ("first", "AAA", "BBB", 1000),
                ("second", "AAB", "BBC", 2000),
                ("wrong-origin", "AAC", "BBB", 3000),
                ("wrong-destination", "AAA", "BBD", 4000),
            ]
        )
        common = {
            "origin": "ORG",
            "destination": "DST",
            "depart_date": "2026-08-12",
            "currency": "RUB",
        }

        both = parse_kupibilet_frontend_search(
            raw,
            **common,
            origin_airports=["AAA", "AAB"],
            destination_airports=["BBB", "BBC"],
        )
        origin_only = parse_kupibilet_frontend_search(
            raw,
            **common,
            origin_airports=["AAA", "AAB"],
        )
        destination_only = parse_kupibilet_frontend_search(
            raw,
            **common,
            destination_airports=["BBB", "BBC"],
        )
        unrestricted = parse_kupibilet_frontend_search(
            raw,
            **common,
            origin_airports=[],
            destination_airports=[],
        )
        all_out_of_scope = parse_kupibilet_frontend_search(
            raw,
            **common,
            destination_airports=["ZZZ"],
        )

        self.assertEqual({offer["id"] for offer in both["offers"]}, {"first", "second"})
        self.assertEqual(
            {offer["id"] for offer in origin_only["offers"]},
            {"first", "second", "wrong-destination"},
        )
        self.assertEqual(
            {offer["id"] for offer in destination_only["offers"]},
            {"first", "second", "wrong-origin"},
        )
        self.assertEqual(len(unrestricted["offers"]), 4)
        self.assertEqual(all_out_of_scope["offers"], [])
        self.assertEqual(all_out_of_scope["skipped"]["destination_out_of_scope"], 4)

    def test_parser_rejects_missing_and_reversed_segment_times(self) -> None:
        raw = airport_scope_raw(
            [
                ("missing-departure", "AAA", "BBB", 1000),
                ("missing-arrival", "AAA", "BBB", 2000),
                ("reversed", "AAA", "BBB", 3000),
                ("valid", "AAA", "BBB", 4000),
            ]
        )
        raw["flights"]["flight-0"]["departure_datetime"] = ""
        raw["flights"]["flight-1"]["arrival_datetime"] = ""
        raw["flights"]["flight-2"]["departure_datetime"] = "2026-08-12T10:00:00+00:00"
        raw["flights"]["flight-2"]["arrival_datetime"] = "2026-08-12T09:00:00+00:00"

        result = parse_kupibilet_frontend_search(
            raw,
            origin="AAA",
            destination="BBB",
            depart_date="2026-08-12",
            currency="RUB",
        )

        self.assertEqual([offer["id"] for offer in result["offers"]], ["valid"])
        self.assertEqual(result["skipped"]["missing_segment_time"], 2)
        self.assertEqual(result["skipped"]["segment_arrival_before_departure"], 1)
        self.assertEqual(result["raw_offer_count"], 1)

    def test_kupibilet_adapter_forwards_airport_scopes_for_both_probe_types(
        self,
    ) -> None:
        depart = future_departure_date()
        calls: list[dict[str, object]] = []

        def fake_fetch(
            origin: str, destination: str, depart_date: object, **kwargs: object
        ) -> dict:
            calls.append(dict(kwargs))
            return {
                "origin": origin,
                "destination": destination,
                "depart_date": str(depart_date),
                "currency": "RUB",
                "source": "test",
                "raw_variant_count": 0,
                "unique_flight_count": 0,
                "skipped": {"destination_out_of_scope": 1},
                "filters": {
                    "origin_airports": kwargs["origin_airports"],
                    "destination_airports": kwargs["destination_airports"],
                },
                "offers": [],
            }

        adapter = KupibiletProviderAdapter(fetcher=fake_fetch)
        query = {
            "probe_id": "scope-probe",
            "direction": "outbound",
            "leg": "direct_outbound",
            "origin": "ORG",
            "destination": "DST",
            "origin_airports": [" aab ", "AAA", "aaa"],
            "destination_airports": ["bbb", ""],
            "date": depart.isoformat(),
            "currency": "RUB",
            "only_carriers": [],
            "direct_only": True,
            "limit": 10,
            "timeout": 10,
            "cache_ttl_seconds": 0,
            "use_cache": False,
        }

        segment = adapter.search_segment(query)
        aggregate = adapter.search_aggregate(query)

        self.assertEqual(len(calls), 2)
        self.assertTrue(all(call["direct_only"] is True for call in calls))
        self.assertTrue(
            all(call["origin_airports"] == ["AAA", "AAB"] for call in calls)
        )
        self.assertTrue(all(call["destination_airports"] == ["BBB"] for call in calls))
        self.assertEqual(segment.query["origin_airports"], ["AAA", "AAB"])
        self.assertEqual(segment.query["destination_airports"], ["BBB"])
        self.assertEqual(aggregate.query["origin_airports"], ["AAA", "AAB"])
        self.assertEqual(aggregate.query["destination_airports"], ["BBB"])
        self.assertTrue(aggregate.query["direct_only"])
        self.assertEqual(aggregate.execution_state, "searched")
        self.assertEqual(aggregate.result_summary["status"], "ok")
        self.assertTrue(aggregate.result_summary["filters"]["direct_only"])
        self.assertEqual(aggregate.result_summary["offer_count"], 0)
        self.assertEqual(
            aggregate.result_summary["skipped"], {"destination_out_of_scope": 1}
        )

    def test_cached_kupibilet_search_normalizes_scopes_in_cache_key(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_fetch(
            origin: str, destination: str, depart_date: object, **kwargs: object
        ) -> dict:
            calls.append(dict(kwargs))
            return {"offers": []}

        common = {
            "currency": "RUB",
            "only_carriers": [],
            "direct_only": False,
            "limit": 20,
            "timeout": 10,
            "use_cache": False,
            "fetcher": fake_fetch,
        }
        first = cached_kupibilet_search(
            "ORG",
            "DST",
            date(2026, 8, 12),
            **common,
            origin_airports=["AAB", "AAA", "AAA"],
            destination_airports=["BBB"],
        )
        equivalent = cached_kupibilet_search(
            "ORG",
            "DST",
            date(2026, 8, 12),
            **common,
            origin_airports=["AAA", "AAB"],
            destination_airports=["BBB"],
        )
        different = cached_kupibilet_search(
            "ORG",
            "DST",
            date(2026, 8, 12),
            **common,
            origin_airports=["AAA"],
            destination_airports=["BBC"],
        )

        self.assertEqual(calls[0]["origin_airports"], ["AAA", "AAB"])
        self.assertEqual(first["cache"]["key"], equivalent["cache"]["key"])
        self.assertNotEqual(first["cache"]["key"], different["cache"]["key"])

    def test_parse_kupibilet_dedupes_marketed_su_direct_flights(self) -> None:
        raw = {
            "variants": [
                {
                    "id": "cheap-su1419",
                    "price": {"amount": "10844", "currency": "RUB"},
                    "segments": [{"flights": ["f1"]}],
                },
                {
                    "id": "expensive-su1419",
                    "price": {"amount": "13935", "currency": "RUB"},
                    "segments": [{"flights": ["f1"]}],
                },
                {
                    "id": "rossiya-marketed-su",
                    "price": {"amount": "10844", "currency": "RUB"},
                    "segments": [{"flights": ["f2"]}],
                },
                {
                    "id": "ural",
                    "price": {"amount": "7000", "currency": "RUB"},
                    "segments": [{"flights": ["f3"]}],
                },
                {
                    "id": "connection-su",
                    "price": {"amount": "9000", "currency": "RUB"},
                    "segments": [{"flights": ["f1", "f4"]}],
                },
            ],
            "flights": {
                "f1": {
                    "marketing_carrier": "SU",
                    "operating_carrier": "SU",
                    "number": 1419,
                    "transport_number": "1419",
                    "departure": "SVX",
                    "departure_datetime": "2026-07-19T00:40:00+05:00",
                    "arrival": "SVO",
                    "arrival_datetime": "2026-07-19T01:10:00+03:00",
                    "equipment": "32A",
                    "duration": 150,
                    "transport_kind": "airplane",
                },
                "f2": {
                    "marketing_carrier": "SU",
                    "operating_carrier": "FV",
                    "number": 6208,
                    "transport_number": "6208",
                    "departure": "SVX",
                    "departure_datetime": "2026-07-19T05:10:00+05:00",
                    "arrival": "SVO",
                    "arrival_datetime": "2026-07-19T05:45:00+03:00",
                    "equipment": "SU9",
                    "duration": 155,
                    "transport_kind": "airplane",
                },
                "f3": {
                    "marketing_carrier": "U6",
                    "operating_carrier": "U6",
                    "number": 264,
                    "transport_number": "264",
                    "departure": "SVX",
                    "departure_datetime": "2026-07-19T06:00:00+05:00",
                    "arrival": "DME",
                    "arrival_datetime": "2026-07-19T06:30:00+03:00",
                    "equipment": "320",
                    "duration": 150,
                    "transport_kind": "airplane",
                },
                "f4": {
                    "marketing_carrier": "SU",
                    "operating_carrier": "SU",
                    "number": 1400,
                    "transport_number": "1400",
                    "departure": "SVO",
                    "departure_datetime": "2026-07-19T03:00:00+03:00",
                    "arrival": "LED",
                    "arrival_datetime": "2026-07-19T04:30:00+03:00",
                    "equipment": "320",
                    "duration": 90,
                    "transport_kind": "airplane",
                },
            },
        }

        result = parse_kupibilet_frontend_search(
            raw,
            origin="SVX",
            destination="MOW",
            depart_date="2026-07-19",
            currency="RUB",
            only_carriers=["SU"],
            direct_only=True,
            limit=20,
        )

        self.assertEqual(result["raw_variant_count"], 5)
        self.assertEqual(result["offer_count"], 2)
        self.assertEqual(result["unique_flight_count"], 2)
        self.assertEqual(
            [offer["flight_numbers"][0] for offer in result["offers"]],
            ["SU1419", "SU6208"],
        )
        self.assertEqual(result["offers"][0]["price"], 10844)
        self.assertEqual(result["offers"][1]["segments"][0]["operating_carrier"], "FV")

    def test_parse_kupibilet_ignores_bad_duration_values(self) -> None:
        raw = {
            "variants": [
                {
                    "id": "bad-duration",
                    "price": {"amount": "10844", "currency": "RUB"},
                    "segments": [{"flights": ["f1"]}],
                },
            ],
            "flights": {
                "f1": {
                    "marketing_carrier": "SU",
                    "operating_carrier": "SU",
                    "transport_number": "1419",
                    "departure": "SVX",
                    "departure_datetime": "2026-07-19T00:40:00+05:00",
                    "arrival": "SVO",
                    "arrival_datetime": "2026-07-19T01:10:00+03:00",
                    "duration": "not-a-number",
                    "transport_kind": "airplane",
                },
            },
        }

        result = parse_kupibilet_frontend_search(
            raw,
            origin="SVX",
            destination="MOW",
            depart_date="2026-07-19",
            currency="RUB",
        )

        self.assertEqual(result["offer_count"], 1)
        self.assertIsNone(result["offers"][0]["duration"])

    def test_parse_kupibilet_orders_provider_cap_by_business_duration_before_price(
        self,
    ) -> None:
        raw = {
            "variants": [
                {
                    "id": "slow-cheap",
                    "price": {"amount": "8000", "currency": "RUB"},
                    "segments": [{"flights": ["slow"]}],
                },
                {
                    "id": "fast-expensive",
                    "price": {"amount": "12000", "currency": "RUB"},
                    "segments": [{"flights": ["fast"]}],
                },
            ],
            "flights": {
                "slow": {
                    "marketing_carrier": "SU",
                    "transport_number": "100",
                    "departure": "SVX",
                    "arrival": "SVO",
                    "departure_datetime": "2026-07-19T05:00:00+05:00",
                    "arrival_datetime": "2026-07-19T06:30:00+03:00",
                    "duration": 210,
                    "transport_kind": "airplane",
                },
                "fast": {
                    "marketing_carrier": "SU",
                    "transport_number": "200",
                    "departure": "SVX",
                    "arrival": "SVO",
                    "departure_datetime": "2026-07-19T07:00:00+05:00",
                    "arrival_datetime": "2026-07-19T07:35:00+03:00",
                    "duration": 155,
                    "transport_kind": "airplane",
                },
            },
        }

        result = parse_kupibilet_frontend_search(
            raw,
            origin="SVX",
            destination="MOW",
            depart_date="2026-07-19",
            currency="RUB",
            limit=1,
        )

        self.assertEqual(
            [offer["id"] for offer in result["offers"]], ["fast-expensive"]
        )

    def test_parse_kupibilet_defers_stop_cap_but_filters_airport_change_before_limit(
        self,
    ) -> None:
        raw = {
            "variants": [
                {
                    "id": "three-stop",
                    "price": {"amount": "1000", "currency": "RUB"},
                    "segments": [{"flights": ["a1", "a2", "a3", "a4"]}],
                },
                {
                    "id": "airport-change",
                    "price": {"amount": "2000", "currency": "RUB"},
                    "segments": [{"flights": ["b1", "b2"]}],
                },
                {
                    "id": "good-one-stop",
                    "price": {"amount": "5000", "currency": "RUB"},
                    "segments": [{"flights": ["c1", "c2"]}],
                },
            ],
            "flights": {
                "a1": {
                    "marketing_carrier": "SU",
                    "transport_number": "1",
                    "departure": "SVX",
                    "arrival": "SVO",
                    "departure_datetime": "2026-07-19T01:00:00+05:00",
                    "arrival_datetime": "2026-07-19T02:00:00+03:00",
                    "duration": 120,
                    "transport_kind": "airplane",
                },
                "a2": {
                    "marketing_carrier": "SU",
                    "transport_number": "2",
                    "departure": "SVO",
                    "arrival": "IST",
                    "departure_datetime": "2026-07-19T04:00:00+03:00",
                    "arrival_datetime": "2026-07-19T08:00:00+03:00",
                    "duration": 240,
                    "transport_kind": "airplane",
                },
                "a3": {
                    "marketing_carrier": "SU",
                    "transport_number": "3",
                    "departure": "IST",
                    "arrival": "CDG",
                    "departure_datetime": "2026-07-19T10:00:00+03:00",
                    "arrival_datetime": "2026-07-19T13:00:00+02:00",
                    "duration": 180,
                    "transport_kind": "airplane",
                },
                "a4": {
                    "marketing_carrier": "SU",
                    "transport_number": "4",
                    "departure": "CDG",
                    "arrival": "FRA",
                    "departure_datetime": "2026-07-19T15:00:00+02:00",
                    "arrival_datetime": "2026-07-19T16:00:00+02:00",
                    "duration": 60,
                    "transport_kind": "airplane",
                },
                "b1": {
                    "marketing_carrier": "TK",
                    "transport_number": "1",
                    "departure": "SVX",
                    "arrival": "IST",
                    "departure_datetime": "2026-07-19T01:00:00+05:00",
                    "arrival_datetime": "2026-07-19T04:00:00+03:00",
                    "duration": 180,
                    "transport_kind": "airplane",
                },
                "b2": {
                    "marketing_carrier": "TK",
                    "transport_number": "2",
                    "departure": "SAW",
                    "arrival": "FRA",
                    "departure_datetime": "2026-07-19T07:00:00+03:00",
                    "arrival_datetime": "2026-07-19T09:00:00+02:00",
                    "duration": 180,
                    "transport_kind": "airplane",
                },
                "c1": {
                    "marketing_carrier": "TK",
                    "transport_number": "3",
                    "departure": "SVX",
                    "arrival": "IST",
                    "departure_datetime": "2026-07-19T01:00:00+05:00",
                    "arrival_datetime": "2026-07-19T04:00:00+03:00",
                    "duration": 180,
                    "transport_kind": "airplane",
                },
                "c2": {
                    "marketing_carrier": "TK",
                    "transport_number": "4",
                    "departure": "IST",
                    "arrival": "FRA",
                    "departure_datetime": "2026-07-19T07:00:00+03:00",
                    "arrival_datetime": "2026-07-19T09:00:00+02:00",
                    "duration": 180,
                    "transport_kind": "airplane",
                },
            },
        }

        result = parse_kupibilet_frontend_search(
            raw,
            origin="SVX",
            destination="FRA",
            depart_date="2026-07-19",
            currency="RUB",
            limit=1,
        )

        self.assertEqual(result["raw_offer_count"], 3)
        self.assertEqual(result["suppressed_airport_change_count"], 1)
        self.assertEqual(result["unique_flight_count"], 2)
        self.assertEqual(result["offer_count"], 1)
        self.assertEqual(result["offers"][0]["id"], "good-one-stop")

    def test_live_search_cache_round_trips_and_can_be_bypassed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_dir = Path(tmp_dir)
            key = live_cache_key(
                "kupibilet_frontend_search",
                {
                    "origin": "SVX",
                    "destination": "IST",
                    "depart_date": "2026-07-19",
                    "currency": "RUB",
                    "only_carriers": ["SU"],
                    "direct_only": True,
                    "limit": 20,
                },
            )
            stored = write_live_cache(
                key,
                {"offers": [{"id": "svx-ist"}], "cache": {"stale": True}},
                cache_dir=cache_dir,
            )
            self.assertFalse(stored["cache"]["hit"])

            cached = read_live_cache(key, ttl_seconds=60, cache_dir=cache_dir)

            self.assertIsNotNone(cached)
            self.assertTrue(cached["cache"]["hit"])
            self.assertEqual(cached["offers"][0]["id"], "svx-ist")
            self.assertIsNone(read_live_cache(key, ttl_seconds=0, cache_dir=cache_dir))

    def test_cached_kupibilet_search_bypasses_fetcher_on_cache_hit(self) -> None:
        calls: list[tuple[str, str]] = []

        def fake_fetch(
            origin: str, destination: str, depart_date: object, **_: object
        ) -> dict:
            calls.append((origin, destination))
            depart = (
                depart_date.isoformat()
                if hasattr(depart_date, "isoformat")
                else str(depart_date)
            )
            return {
                "origin": origin,
                "destination": destination,
                "depart_date": depart,
                "currency": "RUB",
                "source": "test",
                "source_url": "test",
                "raw_variant_count": 0,
                "unique_flight_count": 0,
                "http_status": 200,
                "offers": [],
            }

        with patch(
            "flights_cli.providers.kupibilet.read_live_cache",
            return_value={"offers": [], "cache": {"hit": True}},
        ):
            result = cached_kupibilet_search(
                "SVX",
                "IST",
                date(2026, 7, 19),
                currency="RUB",
                only_carriers=["SU"],
                direct_only=True,
                limit=20,
                timeout=10,
                fetcher=fake_fetch,
            )

        self.assertTrue(result["cache"]["hit"])
        self.assertEqual(calls, [])


class KupibiletFlightNumberTests(unittest.TestCase):
    def test_number_with_embedded_carrier_is_not_doubled(self) -> None:
        # Regression: raw number already carries the carrier prefix ("SU6418").
        # Must yield "SU6418", not "SUSU6418".
        self.assertEqual(
            kupibilet_flight_number(
                {"marketing_carrier": "SU", "transport_number": "SU6418"}
            ),
            "SU6418",
        )

    def test_bare_numeric_number_is_prefixed_once(self) -> None:
        self.assertEqual(
            kupibilet_flight_number(
                {"marketing_carrier": "SU", "transport_number": "6418"}
            ),
            "SU6418",
        )

    def test_two_char_alnum_carrier_with_embedded_prefix(self) -> None:
        # S7 carrier, number "S72534" -> "S72534" (the "2" after S7 is a digit).
        self.assertEqual(
            kupibilet_flight_number(
                {"marketing_carrier": "S7", "transport_number": "S72534"}
            ),
            "S72534",
        )

    def test_operating_carrier_fallback_and_lowercase_number(self) -> None:
        self.assertEqual(
            kupibilet_flight_number({"operating_carrier": "su", "number": "su6418"}),
            "SU6418",
        )

    def test_number_without_carrier_is_left_intact(self) -> None:
        self.assertEqual(
            kupibilet_flight_number({"transport_number": "SU6418"}),
            "SU6418",
        )

    def test_empty_flight_yields_empty_string(self) -> None:
        self.assertEqual(kupibilet_flight_number({}), "")


if __name__ == "__main__":
    unittest.main()
