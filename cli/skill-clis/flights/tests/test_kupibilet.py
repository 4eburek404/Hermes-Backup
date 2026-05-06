from __future__ import annotations

import gzip
import unittest

from flights_cli.cli import build_parser
from flights_cli.errors import CliError
from flights_cli.orchestrators.kb_assemble import build_kupibilet_route_segment_plan
from flights_cli.providers.kupibilet import (
    build_kupibilet_payload,
    decode_http_body,
    kupibilet_result_to_segment_result,
    parse_kupibilet_frontend_search,
)
from flights_cli.store import Store

from helpers import CliSubprocessMixin


class KupibiletTests(CliSubprocessMixin, unittest.TestCase):
    def test_kupibilet_payload_uses_live_frontend_search_shape(self) -> None:
        payload = build_kupibilet_payload("SVX", "MOW", "2026-07-19", "RUB")

        self.assertEqual(payload["trips"], [{"departure": "SVX", "arrival": "MOW", "date": "2026-07-19"}])
        self.assertEqual(payload["travelers"], {"adult": 1, "child": 0, "infant": 0})
        self.assertEqual(payload["cabin"], "economy")
        self.assertEqual(payload["sort_by"], "price")
        self.assertFalse(payload["short_response"])

    def test_decode_http_body_handles_gzip_for_kupibilet(self) -> None:
        raw = b'{"variants":[]}'
        self.assertEqual(decode_http_body(gzip.compress(raw), "gzip"), raw)
        self.assertEqual(decode_http_body(raw, None), raw)

    def test_parse_kupibilet_dedupes_marketed_su_direct_flights(self) -> None:
        raw = {
            "variants": [
                {"id": "cheap-su1419", "price": {"amount": "10844", "currency": "RUB"}, "segments": [{"flights": ["f1"]}]},
                {"id": "expensive-su1419", "price": {"amount": "13935", "currency": "RUB"}, "segments": [{"flights": ["f1"]}]},
                {"id": "rossiya-marketed-su", "price": {"amount": "10844", "currency": "RUB"}, "segments": [{"flights": ["f2"]}]},
                {"id": "ural", "price": {"amount": "7000", "currency": "RUB"}, "segments": [{"flights": ["f3"]}]},
                {"id": "connection-su", "price": {"amount": "9000", "currency": "RUB"}, "segments": [{"flights": ["f1", "f4"]}]},
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
        self.assertEqual([offer["flight_numbers"][0] for offer in result["offers"]], ["SU1419", "SU6208"])
        self.assertEqual(result["offers"][0]["price"], 10844)
        self.assertEqual(result["offers"][1]["flights"][0]["operating_carrier"], "FV")

    def test_parse_kupibilet_ignores_bad_duration_values(self) -> None:
        raw = {
            "variants": [
                {"id": "bad-duration", "price": {"amount": "10844", "currency": "RUB"}, "segments": [{"flights": ["f1"]}]},
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

    def test_kb_search_parser_exposes_live_kupibilet_command(self) -> None:
        args = build_parser().parse_args(
            [
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

        self.assertEqual(args.command_name, "kb-search")
        self.assertEqual(args.only_carrier, ["SU"])
        self.assertTrue(args.direct_only)
        self.assertEqual(args.limit, 20)

    def test_route_kb_assemble_parser_and_default_day_offsets(self) -> None:
        args = build_parser().parse_args(
            [
                "route",
                "kb-assemble",
                "SVX",
                "CDG",
                "--depart-date",
                "2026-08-15",
                "--return-date",
                "2026-08-19",
                "--hub",
                "IST",
                "--hub",
                "AYT",
            ]
        )

        self.assertEqual(args.command_name, "route kb-assemble")
        self.assertEqual(args.segment_limit, 30)
        self.assertEqual(args.limit_per_pair, 10)
        plan = build_kupibilet_route_segment_plan(args, Store())
        self.assertEqual(plan["hubs"], ["IST", "AYT"])
        self.assertEqual(plan["second_leg_day_offsets"], {"outbound": [0, 1], "return": [0, 1, 2]})
        self.assertEqual(plan["metrics"]["segment_search_count"], 14)

    def test_route_kb_assemble_requires_explicit_or_auto_hubs(self) -> None:
        args = build_parser().parse_args(
            [
                "route",
                "kb-assemble",
                "SVX",
                "CDG",
                "--depart-date",
                "2026-08-15",
                "--return-date",
                "2026-08-19",
            ]
        )

        with self.assertRaises(CliError):
            build_kupibilet_route_segment_plan(args, Store())

    def test_kupibilet_direct_segments_feed_route_assemble(self) -> None:
        def kb_result(origin: str, destination: str, depart_date: str, price: int, flight_number: str, dep: str, arr: str) -> dict:
            carrier = "".join(ch for ch in flight_number if ch.isalpha())[:2]
            return {
                "origin": origin,
                "destination": destination,
                "depart_date": depart_date,
                "currency": "RUB",
                "source": "Kupibilet frontend_search (live aggregate)",
                "source_url": "https://api-rs-lb.kupibilet.ru/frontend_search",
                "raw_variant_count": 1,
                "unique_flight_count": 1,
                "offers": [
                    {
                        "id": f"{flight_number}-{depart_date}",
                        "price": price,
                        "currency": "RUB",
                        "number_of_changes": 0,
                        "duration": 180,
                        "flights": [
                            {
                                "flight_number": flight_number,
                                "marketing_carrier": carrier,
                                "operating_carrier": carrier,
                                "origin": origin,
                                "destination": destination,
                                "departure_at": dep,
                                "arrival_at": arr,
                                "aircraft": "320",
                            }
                        ],
                    }
                ],
            }

        segment_results = [
            kupibilet_result_to_segment_result(
                kb_result("SVX", "AYT", "2026-08-15", 20126, "DP955", "2026-08-15T06:05:00+05:00", "2026-08-15T09:30:00+03:00"),
                direction="outbound",
                leg="origin_to_hub",
            ),
            kupibilet_result_to_segment_result(
                kb_result("AYT", "CDG", "2026-08-15", 35013, "XQ510", "2026-08-15T13:35:00+03:00", "2026-08-15T16:55:00+02:00"),
                direction="outbound",
                leg="hub_to_destination",
            ),
            kupibilet_result_to_segment_result(
                kb_result("CDG", "AYT", "2026-08-19", 13240, "XQ511", "2026-08-19T17:45:00+02:00", "2026-08-19T22:15:00+03:00"),
                direction="return",
                leg="destination_to_hub",
            ),
            kupibilet_result_to_segment_result(
                kb_result("AYT", "SVX", "2026-08-20", 22325, "DP956", "2026-08-20T10:05:00+03:00", "2026-08-20T16:50:00+05:00"),
                direction="return",
                leg="hub_to_origin",
            ),
        ]

        self.assertEqual(segment_results[0]["offers"][0]["source"], "Kupibilet frontend_search direct-only")
        assembled = self._assemble({"segment_results": segment_results}, "--include-candidates", "10")
        self.assertEqual(assembled["data"]["assembly"]["candidate_count"], 1)
        self.assertEqual(assembled["data"]["ranked"][0]["price"], 90704)


if __name__ == "__main__":
    unittest.main()
