from __future__ import annotations

import gzip
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from flights_cli.cli import build_parser
from flights_cli.orchestrators.live_route_assembly import run_live_route_assembly
from flights_cli.providers.kupibilet import (
    build_kupibilet_payload,
    build_kupibilet_roundtrip_payload,
    cached_kupibilet_search,
    decode_http_body,
    kupibilet_flight_number,
    parse_kupibilet_frontend_search,
    parse_kupibilet_roundtrip_search,
)
from flights_cli.providers.live_cache import (
    live_cache_key,
    read_live_cache,
    write_live_cache,
)
from flights_cli.services.agent_report import build_validated_agent_report
from flights_cli.store import Store

from helpers import CliSubprocessMixin, live_assembly_args


class KupibiletTests(CliSubprocessMixin, unittest.TestCase):
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

    def test_kupibilet_roundtrip_payload_uses_two_trip_frontend_search_shape(
        self,
    ) -> None:
        payload = build_kupibilet_roundtrip_payload(
            "SVX", "BJS", "2026-08-01", "2026-08-08", "RUB"
        )

        self.assertEqual(
            payload["trips"],
            [
                {"departure": "SVX", "arrival": "BJS", "date": "2026-08-01"},
                {"departure": "BJS", "arrival": "SVX", "date": "2026-08-08"},
            ],
        )
        self.assertEqual(payload["travelers"], {"adult": 1, "child": 0, "infant": 0})
        self.assertEqual(payload["cabin"], "economy")
        self.assertEqual(payload["sort_by"], "price")
        self.assertFalse(payload["short_response"])

    def test_parse_kupibilet_roundtrip_filters_and_keeps_baggage_variants(self) -> None:
        raw = {
            "variants": [
                {
                    "id": "u6-basic",
                    "price": {"amount": "73835", "currency": "RUB"},
                    "baggage": {"weight": 0, "count": 0},
                    "hand_luggage": {"weight": 5, "count": 1},
                    "seats_left": 4,
                    "segments": [{"flights": ["out873"]}, {"flights": ["ret776"]}],
                },
                {
                    "id": "u6-with-bag",
                    "price": {"amount": "79753", "currency": "RUB"},
                    "baggage": {"weight": 10, "count": 1},
                    "hand_luggage": {"weight": 5, "count": 1},
                    "segments": [{"flights": ["out873"]}, {"flights": ["ret776"]}],
                },
                {
                    "id": "mixed-return",
                    "price": {"amount": "65000", "currency": "RUB"},
                    "segments": [{"flights": ["out873"]}, {"flights": ["ret-su"]}],
                },
                {
                    "id": "u6-connection",
                    "price": {"amount": "62000", "currency": "RUB"},
                    "segments": [
                        {"flights": ["out873", "out874"]},
                        {"flights": ["ret776"]},
                    ],
                },
            ],
            "flights": {
                "out873": {
                    "marketing_carrier": "U6",
                    "operating_carrier": "U6",
                    "number": 873,
                    "transport_number": "873",
                    "departure": "SVX",
                    "departure_datetime": "2026-08-01T15:55:00+05:00",
                    "arrival": "PKX",
                    "arrival_datetime": "2026-08-02T01:00:00+08:00",
                    "equipment": "319",
                    "duration": 365,
                    "transport_kind": "airplane",
                },
                "out874": {
                    "marketing_carrier": "U6",
                    "operating_carrier": "U6",
                    "transport_number": "874",
                    "departure": "PKX",
                    "departure_datetime": "2026-08-02T03:00:00+08:00",
                    "arrival": "HGH",
                    "arrival_datetime": "2026-08-02T05:00:00+08:00",
                    "duration": 120,
                    "transport_kind": "airplane",
                },
                "ret776": {
                    "marketing_carrier": "U6",
                    "operating_carrier": "U6",
                    "number": 776,
                    "transport_number": "776",
                    "departure": "PKX",
                    "departure_datetime": "2026-08-08T10:55:00+08:00",
                    "arrival": "SVX",
                    "arrival_datetime": "2026-08-08T14:30:00+05:00",
                    "equipment": "319",
                    "duration": 395,
                    "transport_kind": "airplane",
                },
                "ret-su": {
                    "marketing_carrier": "SU",
                    "operating_carrier": "SU",
                    "transport_number": "631",
                    "departure": "PKX",
                    "departure_datetime": "2026-08-08T10:55:00+08:00",
                    "arrival": "SVX",
                    "arrival_datetime": "2026-08-08T14:30:00+05:00",
                    "duration": 395,
                    "transport_kind": "airplane",
                },
            },
        }

        result = parse_kupibilet_roundtrip_search(
            raw,
            origin="SVX",
            destination="BJS",
            depart_date="2026-08-01",
            return_date="2026-08-08",
            currency="RUB",
            only_carriers=["U6"],
            direct_only=True,
            limit=20,
        )

        self.assertEqual(result["raw_variant_count"], 4)
        self.assertEqual(result["offer_count"], 2)
        self.assertEqual(
            [offer["id"] for offer in result["offers"]], ["u6-basic", "u6-with-bag"]
        )
        self.assertEqual(result["offers"][0]["price"], 73835)
        self.assertEqual(result["offers"][0]["baggage"], {"weight": 0, "count": 0})
        self.assertEqual(result["offers"][1]["baggage"], {"weight": 10, "count": 1})
        self.assertEqual(
            result["offers"][0]["flight_numbers_by_journey"], [["U6873"], ["U6776"]]
        )
        self.assertEqual(
            [journey["direction"] for journey in result["offers"][0]["journeys"]],
            ["outbound", "return"],
        )
        self.assertEqual(result["offers"][0]["journeys"][0]["origin"], "SVX")
        self.assertEqual(result["offers"][0]["journeys"][0]["destination"], "PKX")
        self.assertEqual(result["offers"][0]["journeys"][1]["origin"], "PKX")
        self.assertEqual(result["offers"][0]["journeys"][1]["destination"], "SVX")
        self.assertEqual(result["skipped"]["carrier"], 1)
        self.assertEqual(result["skipped"]["not_direct"], 1)

    def test_decode_http_body_handles_gzip_for_kupibilet(self) -> None:
        raw = b'{"variants":[]}'
        self.assertEqual(decode_http_body(gzip.compress(raw), "gzip"), raw)
        self.assertEqual(decode_http_body(raw, None), raw)

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

    def test_parse_kupibilet_filters_three_stop_and_airport_change_before_limit(
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
        self.assertEqual(result["suppressed_three_plus_count"], 1)
        self.assertEqual(result["suppressed_airport_change_count"], 1)
        self.assertEqual(result["offer_count"], 1)
        self.assertEqual(result["offers"][0]["id"], "good-one-stop")

    def test_kb_search_parser_exposes_live_kupibilet_command(self) -> None:
        args = build_parser().parse_args(
            [
                "diagnose",
                "kb-search",
                "SVX",
                "MOW",
                "--depart-date",
                "2026-07-19",
                "--only-carrier",
                "SU",
                "--direct-only",
                "--limit",
                "20",
            ]
        )

        self.assertEqual(args.command_name, "diagnose kb-search")
        self.assertEqual(args.only_carrier, ["SU"])
        self.assertTrue(args.direct_only)
        self.assertEqual(args.limit, 20)
        self.assertEqual(args.cache_ttl_seconds, 30 * 60)
        self.assertFalse(args.no_cache)

    def test_kb_roundtrip_parser_exposes_kupibilet_two_trip_command(self) -> None:
        args = build_parser().parse_args(
            [
                "diagnose",
                "kb-roundtrip",
                "SVX",
                "BJS",
                "--depart-date",
                "2026-08-01",
                "--return-date",
                "2026-08-08",
                "--only-carrier",
                "U6",
                "--direct-only",
                "--limit",
                "10",
            ]
        )

        self.assertEqual(args.command_name, "diagnose kb-roundtrip")
        self.assertEqual(args.only_carrier, ["U6"])
        self.assertTrue(args.direct_only)
        self.assertEqual(args.depart_date, "2026-08-01")
        self.assertEqual(args.return_date, "2026-08-08")
        self.assertEqual(args.limit, 10)

    def test_ru_priority_skips_dxb_when_ist_pair_is_usable(self) -> None:
        args = live_assembly_args(
            origin="SVX",
            destination="MUC",
            depart_date="2026-08-12",
            provider_policy="kupibilet",
            include_segment_results=10,
            no_live_cache=True,
        )
        calls: list[tuple[str, str]] = []

        def kb_result(
            origin: str,
            destination: str,
            depart_date: object,
            dep: str | None = None,
            arr: str | None = None,
        ) -> dict:
            depart = (
                depart_date.isoformat()
                if hasattr(depart_date, "isoformat")
                else str(depart_date)
            )
            offers = []
            if dep and arr:
                offers.append(
                    {
                        "id": f"{origin}-{destination}-{depart}",
                        "price": 10000,
                        "currency": "RUB",
                        "number_of_changes": 0,
                        "duration": 180,
                        "segments": [
                            {
                                "flight_number": f"TK{len(calls) + 100}",
                                "marketing_carrier": "TK",
                                "operating_carrier": "TK",
                                "origin": origin,
                                "destination": destination,
                                "departure_at": dep,
                                "arrival_at": arr,
                                "aircraft": "320",
                            }
                        ],
                    }
                )
            return {
                "origin": origin,
                "destination": destination,
                "depart_date": depart,
                "currency": "RUB",
                "source": "test",
                "source_url": "test",
                "raw_variant_count": len(offers),
                "unique_flight_count": len(offers),
                "http_status": 200,
                "offers": offers,
            }

        def fake_fetch(
            origin: str, destination: str, depart_date: object, **kwargs: object
        ) -> dict:
            calls.append((origin, destination, bool(kwargs.get("direct_only", True))))
            depart = (
                depart_date.isoformat()
                if hasattr(depart_date, "isoformat")
                else str(depart_date)
            )
            if (origin, destination) == ("SVX", "IST"):
                return kb_result(
                    origin,
                    destination,
                    depart_date,
                    f"{depart}T06:00:00+05:00",
                    f"{depart}T09:00:00+03:00",
                )
            if (origin, destination) == ("IST", "MUC"):
                return kb_result(
                    origin,
                    destination,
                    depart_date,
                    f"{depart}T14:00:00+03:00",
                    f"{depart}T16:00:00+02:00",
                )
            return kb_result(origin, destination, depart_date)

        with patch(
            "flights_cli.orchestrators.live_assembly_runner.fetch_kupibilet_search",
            side_effect=fake_fetch,
        ):
            result = run_live_route_assembly(args, Store())

        direct_calls = {
            (origin, destination)
            for origin, destination, direct_only in calls
            if direct_only
        }
        self.assertNotIn(("SVX", "DXB"), direct_calls)
        self.assertNotIn(("DXB", "MUC"), direct_calls)
        self.assertGreater(result["assembly"]["candidate_count"], 0)
        priority_skips = [
            search
            for search in result["live_search"]["segment_searches"]
            if search.get("reason") == "priority_route_viable"
        ]
        self.assertEqual(priority_skips, [])
        self.assertFalse(
            any(
                "DXB" in {search.get("origin"), search.get("destination")}
                for search in result["live_search"]["segment_searches"]
            )
        )

    def test_explicit_carrier_aggregate_control_reports_through_fare_check(
        self,
    ) -> None:
        class FixedDate(date):
            @classmethod
            def today(cls) -> date:
                return cls(2026, 5, 1)

        args = live_assembly_args(
            origin="SVX",
            destination="DEL",
            depart_date="2026-06-01",
            provider_policy="kupibilet",
            aggregate_control_limit=10,
            aggregate_control_carriers=["SU"],
            no_live_cache=True,
        )
        calls: list[tuple[str, str, bool, tuple[str, ...]]] = []

        def fake_fetch(
            origin: str,
            destination: str,
            depart_date: object,
            *,
            direct_only: bool,
            only_carriers: list[str],
            **_: object,
        ) -> dict:
            calls.append((origin, destination, bool(direct_only), tuple(only_carriers)))
            depart = (
                depart_date.isoformat()
                if hasattr(depart_date, "isoformat")
                else str(depart_date)
            )
            offers = []
            if (
                origin == "SVX"
                and destination == "DEL"
                and not direct_only
                and only_carriers == ["SU"]
            ):
                offers.append(
                    {
                        "id": "su-through-control",
                        "price": 42000,
                        "currency": "RUB",
                        "number_of_changes": 1,
                        "duration": 520,
                        "flight_numbers": ["SU1419", "SU232"],
                        "segments": [
                            {
                                "flight_number": "SU1419",
                                "marketing_carrier": "SU",
                                "operating_carrier": "SU",
                                "origin": "SVX",
                                "destination": "SVO",
                                "departure_at": "2026-06-01T06:00:00+05:00",
                                "arrival_at": "2026-06-01T06:40:00+03:00",
                            },
                            {
                                "flight_number": "SU232",
                                "marketing_carrier": "SU",
                                "operating_carrier": "SU",
                                "origin": "SVO",
                                "destination": "DEL",
                                "departure_at": "2026-06-01T10:30:00+03:00",
                                "arrival_at": "2026-06-01T18:50:00+05:30",
                            },
                        ],
                    }
                )
            return {
                "origin": origin,
                "destination": destination,
                "depart_date": depart,
                "currency": "RUB",
                "source": "test",
                "source_url": "test",
                "raw_variant_count": len(offers),
                "unique_flight_count": len(offers),
                "http_status": 200,
                "offers": offers,
            }

        with (
            patch("flights_cli.domain.normalize.date", FixedDate),
            patch(
                "flights_cli.pipeline.evidence_plan.SYSTEM_CLOCK.today",
                return_value=date(2026, 5, 1),
            ),
            patch(
                "flights_cli.orchestrators.live_assembly_runner.fetch_kupibilet_search",
                side_effect=fake_fetch,
            ),
        ):
            result = run_live_route_assembly(args, Store())

        self.assertIn(("SVX", "DEL", False, ("SU",)), calls)
        carrier_controls = [
            control
            for control in result["live_search"]["aggregate_controls"]
            if control.get("filters", {}).get("only_carriers") == ["SU"]
        ]
        self.assertEqual(
            carrier_controls[0]["top_offers"][0]["flight_numbers"], ["SU1419", "SU232"]
        )
        ledger = result["live_search"]["probe_ledger"]
        planned_types = {item["type"] for item in ledger["planned_controls"]}
        searched_types = {item["type"] for item in ledger["searched_controls"]}
        self.assertIn("carrier_aggregate", planned_types)
        self.assertIn("carrier_aggregate", searched_types)
        self.assertEqual(ledger["not_executed_controls"], [])
        self.assertEqual(
            ledger["completeness"]["planned_count"],
            ledger["completeness"]["terminal_count"],
        )
        report = build_validated_agent_report(result, Store())
        self.assertEqual(
            report["evidence"]["coverage"]["counts"]["not_executed_controls"], 0
        )
        self.assertEqual(report["evidence"]["through_fare_checks"][0]["carrier"], "SU")

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
