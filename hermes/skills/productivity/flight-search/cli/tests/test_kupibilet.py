from __future__ import annotations

import gzip
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from flights_cli.cli import build_parser
from flights_cli.config import DEFAULT_ROUTE_HUBS
from flights_cli.orchestrators.kb_assemble import (
    build_kupibilet_route_segment_plan,
    run_kupibilet_route_assembly,
    synthesize_moscow_gateway_control_results,
)
from flights_cli.providers.kupibilet import (
    build_kupibilet_payload,
    build_kupibilet_roundtrip_payload,
    cached_kupibilet_search,
    decode_http_body,
    kupibilet_result_to_segment_result,
    parse_kupibilet_frontend_search,
    parse_kupibilet_roundtrip_search,
)
from flights_cli.providers.live_cache import live_cache_key, read_live_cache, write_live_cache
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

    def test_kupibilet_roundtrip_payload_uses_two_trip_frontend_search_shape(self) -> None:
        payload = build_kupibilet_roundtrip_payload("SVX", "BJS", "2026-08-01", "2026-08-08", "RUB")

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
                    "segments": [{"flights": ["out873", "out874"]}, {"flights": ["ret776"]}],
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
        self.assertEqual([offer["id"] for offer in result["offers"]], ["u6-basic", "u6-with-bag"])
        self.assertEqual(result["offers"][0]["price"], 73835)
        self.assertEqual(result["offers"][0]["baggage"], {"weight": 0, "count": 0})
        self.assertEqual(result["offers"][1]["baggage"], {"weight": 10, "count": 1})
        self.assertEqual(result["offers"][0]["flight_numbers_by_journey"], [["U6873"], ["U6776"]])
        self.assertEqual([journey["direction"] for journey in result["offers"][0]["journeys"]], ["outbound", "return"])
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

    def test_parse_kupibilet_filters_three_stop_and_airport_change_before_limit(self) -> None:
        raw = {
            "variants": [
                {"id": "three-stop", "price": {"amount": "1000", "currency": "RUB"}, "segments": [{"flights": ["a1", "a2", "a3", "a4"]}]},
                {"id": "airport-change", "price": {"amount": "2000", "currency": "RUB"}, "segments": [{"flights": ["b1", "b2"]}]},
                {"id": "good-one-stop", "price": {"amount": "5000", "currency": "RUB"}, "segments": [{"flights": ["c1", "c2"]}]},
            ],
            "flights": {
                "a1": {"marketing_carrier": "SU", "transport_number": "1", "departure": "SVX", "arrival": "SVO", "departure_datetime": "2026-07-19T01:00:00+05:00", "arrival_datetime": "2026-07-19T02:00:00+03:00", "duration": 120, "transport_kind": "airplane"},
                "a2": {"marketing_carrier": "SU", "transport_number": "2", "departure": "SVO", "arrival": "IST", "departure_datetime": "2026-07-19T04:00:00+03:00", "arrival_datetime": "2026-07-19T08:00:00+03:00", "duration": 240, "transport_kind": "airplane"},
                "a3": {"marketing_carrier": "SU", "transport_number": "3", "departure": "IST", "arrival": "CDG", "departure_datetime": "2026-07-19T10:00:00+03:00", "arrival_datetime": "2026-07-19T13:00:00+02:00", "duration": 180, "transport_kind": "airplane"},
                "a4": {"marketing_carrier": "SU", "transport_number": "4", "departure": "CDG", "arrival": "FRA", "departure_datetime": "2026-07-19T15:00:00+02:00", "arrival_datetime": "2026-07-19T16:00:00+02:00", "duration": 60, "transport_kind": "airplane"},
                "b1": {"marketing_carrier": "TK", "transport_number": "1", "departure": "SVX", "arrival": "IST", "departure_datetime": "2026-07-19T01:00:00+05:00", "arrival_datetime": "2026-07-19T04:00:00+03:00", "duration": 180, "transport_kind": "airplane"},
                "b2": {"marketing_carrier": "TK", "transport_number": "2", "departure": "SAW", "arrival": "FRA", "departure_datetime": "2026-07-19T07:00:00+03:00", "arrival_datetime": "2026-07-19T09:00:00+02:00", "duration": 180, "transport_kind": "airplane"},
                "c1": {"marketing_carrier": "TK", "transport_number": "3", "departure": "SVX", "arrival": "IST", "departure_datetime": "2026-07-19T01:00:00+05:00", "arrival_datetime": "2026-07-19T04:00:00+03:00", "duration": 180, "transport_kind": "airplane"},
                "c2": {"marketing_carrier": "TK", "transport_number": "4", "departure": "IST", "arrival": "FRA", "departure_datetime": "2026-07-19T07:00:00+03:00", "arrival_datetime": "2026-07-19T09:00:00+02:00", "duration": 180, "transport_kind": "airplane"},
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
        self.assertEqual(args.cache_ttl_seconds, 30 * 60)
        self.assertFalse(args.no_cache)

    def test_kb_roundtrip_parser_exposes_kupibilet_two_trip_command(self) -> None:
        args = build_parser().parse_args(
            [
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

        self.assertEqual(args.command_name, "kb-roundtrip")
        self.assertEqual(args.only_carrier, ["U6"])
        self.assertTrue(args.direct_only)
        self.assertEqual(args.depart_date, "2026-08-01")
        self.assertEqual(args.return_date, "2026-08-08")
        self.assertEqual(args.limit, 10)

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
        self.assertEqual(args.live_cache_ttl_seconds, 30 * 60)
        self.assertFalse(args.no_live_cache)
        self.assertEqual(args.direct_route_index_ttl_seconds, 604800)
        self.assertFalse(args.no_direct_route_intel)
        plan = build_kupibilet_route_segment_plan(args, Store())
        self.assertEqual(plan["hubs"], ["IST", "AYT"])
        self.assertEqual(plan["second_leg_day_offsets"], {"outbound": [0, 1], "return": [0, 1, 2]})
        self.assertEqual(plan["metrics"]["segment_search_count"], 14)

    def test_route_kb_assemble_uses_ru_priority_strategy_when_none_are_passed(self) -> None:
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

        plan = build_kupibilet_route_segment_plan(args, Store())

        self.assertEqual(plan["routing_strategy"], "ru-priority")
        self.assertEqual(plan["hubs"], ["IST", "DXB"])
        self.assertEqual(plan["hub_source"], "strategy")
        self.assertEqual(plan["metrics"]["segment_search_count"], 24)

    def test_route_kb_assemble_uses_asia_profile_for_beijing(self) -> None:
        args = build_parser().parse_args(
            [
                "route",
                "kb-assemble",
                "SVX",
                "BJS",
                "--depart-date",
                "2026-09-15",
                "--return-date",
                "2026-09-20",
            ]
        )

        plan = build_kupibilet_route_segment_plan(args, Store())

        self.assertEqual(plan["routing_profile"], "asia-oceania")
        self.assertEqual(plan["destination_airports"], ["PEK", "PKX"])
        self.assertEqual(plan["hubs"], ["SVO", "IST", "DXB"])
        self.assertEqual(plan["metrics"]["segment_search_count"], 42)
        segments = {
            (segment["direction"], segment["origin"], segment["destination"], segment["date"], segment["leg"], segment.get("route_family"))
            for segment in plan["segments"]
        }
        self.assertIn(("outbound", "SVX", "PEK", "2026-09-15", "direct_outbound", "direct_control"), segments)
        self.assertIn(("outbound", "SVO", "PEK", "2026-09-16", "hub_to_destination", "svo_asia"), segments)
        self.assertIn(("return", "PEK", "SVX", "2026-09-20", "direct_return", "direct_control"), segments)
        self.assertIn(("return", "SVO", "SVX", "2026-09-22", "hub_to_origin", "svo_asia"), segments)

    def test_route_kb_assemble_hub_list_strategy_uses_default_hubs(self) -> None:
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
                "--routing-strategy",
                "hub-list",
            ]
        )

        plan = build_kupibilet_route_segment_plan(args, Store())

        self.assertEqual(plan["hubs"], list(DEFAULT_ROUTE_HUBS))
        self.assertEqual(plan["hub_source"], "default")
        self.assertEqual(plan["metrics"]["segment_search_count"], 91)

    def test_ru_priority_synthesizes_svo_fallback_when_ist_direct_is_empty(self) -> None:
        plan = {
            "routing_strategy": "ru-priority",
            "origin_airports": ["SVX"],
            "dates": {"depart": "2026-08-12", "return": None},
            "currency": "RUB",
        }
        segment_results = [
            {
                "direction": "outbound",
                "leg": "origin_to_gateway",
                "query": {"origin": "SVX", "destination": "SVO", "date": "2026-08-12"},
                "offers": [
                    {
                        "id": "svx-svo",
                        "origin": "SVX",
                        "destination": "SVO",
                        "departure_airport": "SVX",
                        "arrival_airport": "SVO",
                        "departure_at": "2026-08-12T06:00:00+05:00",
                        "arrival_at": "2026-08-12T06:40:00+03:00",
                        "price": 10000,
                        "currency": "RUB",
                        "segments": [
                            {
                                "origin": "SVX",
                                "destination": "SVO",
                                "departure_at": "2026-08-12T06:00:00+05:00",
                                "arrival_at": "2026-08-12T06:40:00+03:00",
                                "carrier": "SU",
                            }
                        ],
                    }
                ],
            },
            {
                "direction": "outbound",
                "leg": "gateway_to_hub",
                "query": {"origin": "SVO", "destination": "IST", "date": "2026-08-12"},
                "offers": [
                    {
                        "id": "svo-ist",
                        "origin": "SVO",
                        "destination": "IST",
                        "departure_airport": "SVO",
                        "arrival_airport": "IST",
                        "departure_at": "2026-08-12T09:30:00+03:00",
                        "arrival_at": "2026-08-12T13:30:00+03:00",
                        "price": 20000,
                        "currency": "RUB",
                        "segments": [
                            {
                                "origin": "SVO",
                                "destination": "IST",
                                "departure_at": "2026-08-12T09:30:00+03:00",
                                "arrival_at": "2026-08-12T13:30:00+03:00",
                                "carrier": "SU",
                            }
                        ],
                    }
                ],
            },
        ]

        synthetic_results, synthetic_searches = synthesize_moscow_gateway_control_results(plan, segment_results)

        self.assertEqual(len(synthetic_results), 1)
        self.assertEqual(synthetic_results[0]["leg"], "origin_to_hub")
        self.assertEqual(synthetic_results[0]["query"]["origin"], "SVX")
        self.assertEqual(synthetic_results[0]["query"]["destination"], "IST")
        self.assertEqual(synthetic_results[0]["offers"][0]["price"], 30000)
        self.assertEqual([segment["origin"] for segment in synthetic_results[0]["offers"][0]["segments"]], ["SVX", "SVO"])
        self.assertEqual(synthetic_searches[0]["status"], "synthetic")

    def test_ru_priority_synthesizes_moscow_control_even_when_ist_direct_has_offers(self) -> None:
        plan = {
            "routing_strategy": "ru-priority",
            "origin_airports": ["SVX"],
            "dates": {"depart": "2026-08-12", "return": None},
            "currency": "RUB",
        }

        def offer(offer_id: str, origin: str, destination: str, price: int) -> dict:
            return {
                "id": offer_id,
                "origin": origin,
                "destination": destination,
                "departure_airport": origin,
                "arrival_airport": destination,
                "departure_at": "2026-08-12T06:00:00+05:00",
                "arrival_at": "2026-08-12T09:00:00+03:00",
                "price": price,
                "currency": "RUB",
                "segments": [{"origin": origin, "destination": destination, "carrier": "SU"}],
            }

        segment_results = [
            {
                "direction": "outbound",
                "leg": "origin_to_hub",
                "query": {"origin": "SVX", "destination": "IST", "date": "2026-08-12"},
                "offers": [offer("direct-svx-ist", "SVX", "IST", 25000)],
            },
            {
                "direction": "outbound",
                "leg": "origin_to_gateway",
                "query": {"origin": "SVX", "destination": "SVO", "date": "2026-08-12"},
                "offers": [offer("svx-svo", "SVX", "SVO", 10000)],
            },
            {
                "direction": "outbound",
                "leg": "gateway_to_hub",
                "query": {"origin": "SVO", "destination": "IST", "date": "2026-08-12"},
                "offers": [offer("svo-ist", "SVO", "IST", 20000)],
            },
        ]

        synthetic_results, synthetic_searches = synthesize_moscow_gateway_control_results(plan, segment_results)

        self.assertEqual(len(synthetic_results), 1)
        self.assertEqual(synthetic_results[0]["leg"], "origin_to_hub")
        self.assertEqual(synthetic_results[0]["offers"][0]["source"], "Kupibilet synthesized Moscow gateway control")
        self.assertEqual(synthetic_searches[0]["route_family"], "moscow_gateway_control")

    def test_ru_priority_skips_dxb_when_ist_pair_is_usable(self) -> None:
        args = build_parser().parse_args(
            [
                "route",
                "kb-assemble",
                "SVX",
                "MUC",
                "--depart-date",
                "2026-08-12",
                "--include-segment-results",
                "10",
                "--no-live-cache",
                "--no-direct-route-intel",
            ]
        )
        calls: list[tuple[str, str]] = []

        def kb_result(origin: str, destination: str, depart_date: object, dep: str | None = None, arr: str | None = None) -> dict:
            depart = depart_date.isoformat() if hasattr(depart_date, "isoformat") else str(depart_date)
            offers = []
            if dep and arr:
                offers.append(
                    {
                        "id": f"{origin}-{destination}-{depart}",
                        "price": 10000,
                        "currency": "RUB",
                        "number_of_changes": 0,
                        "duration": 180,
                        "flights": [
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

        def fake_fetch(origin: str, destination: str, depart_date: object, **_: object) -> dict:
            calls.append((origin, destination))
            depart = depart_date.isoformat() if hasattr(depart_date, "isoformat") else str(depart_date)
            if (origin, destination) == ("SVX", "IST"):
                return kb_result(origin, destination, depart_date, f"{depart}T06:00:00+05:00", f"{depart}T09:00:00+03:00")
            if (origin, destination) == ("IST", "MUC"):
                return kb_result(origin, destination, depart_date, f"{depart}T14:00:00+03:00", f"{depart}T16:00:00+02:00")
            return kb_result(origin, destination, depart_date)

        with patch("flights_cli.orchestrators.kb_assemble.fetch_kupibilet_search", side_effect=fake_fetch):
            result = run_kupibilet_route_assembly(args, Store())

        self.assertNotIn(("SVX", "DXB"), calls)
        self.assertNotIn(("DXB", "MUC"), calls)
        self.assertGreater(result["assembly"]["candidate_count"], 0)
        skipped_dxb = [
            search
            for search in result["live_search"]["segment_searches"]
            if search.get("reason") == "priority_route_viable"
        ]
        self.assertGreaterEqual(len(skipped_dxb), 2)
        self.assertTrue(all(search["route_family"] == "dxb_direct" for search in skipped_dxb))

    def test_direct_route_intel_skips_absent_svx_direct_control(self) -> None:
        args = build_parser().parse_args(
            [
                "route",
                "kb-assemble",
                "SVX",
                "MUC",
                "--depart-date",
                "2026-08-12",
                "--no-live-cache",
            ]
        )
        calls: list[tuple[str, str]] = []
        route_index = {
            "source": "test official schedule",
            "airport": "SVX",
            "fetched_at": "2026-05-07T00:00:00+00:00",
            "source_urls": {"outbound": "test", "return": "test"},
            "routes": {"outbound": ["IST", "DXB", "PKX"], "return": ["IST"]},
        }

        def kb_result(origin: str, destination: str, depart_date: object, dep: str | None = None, arr: str | None = None) -> dict:
            depart = depart_date.isoformat() if hasattr(depart_date, "isoformat") else str(depart_date)
            offers = []
            if dep and arr:
                offers.append(
                    {
                        "id": f"{origin}-{destination}-{depart}",
                        "price": 10000,
                        "currency": "RUB",
                        "number_of_changes": 0,
                        "duration": 180,
                        "flights": [
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

        def fake_fetch(origin: str, destination: str, depart_date: object, **_: object) -> dict:
            calls.append((origin, destination))
            depart = depart_date.isoformat() if hasattr(depart_date, "isoformat") else str(depart_date)
            if (origin, destination) == ("SVX", "IST"):
                return kb_result(origin, destination, depart_date, f"{depart}T06:00:00+05:00", f"{depart}T09:00:00+03:00")
            if (origin, destination) == ("IST", "MUC"):
                return kb_result(origin, destination, depart_date, f"{depart}T14:00:00+03:00", f"{depart}T16:00:00+02:00")
            return kb_result(origin, destination, depart_date)

        with (
            patch("flights_cli.orchestrators.kb_assemble.load_or_refresh_svx_route_index", return_value=(route_index, {"hit": True, "ttl_seconds": 604800})),
            patch("flights_cli.orchestrators.kb_assemble.fetch_kupibilet_search", side_effect=fake_fetch),
        ):
            result = run_kupibilet_route_assembly(args, Store())

        self.assertNotIn(("SVX", "MUC"), calls)
        self.assertIn(("SVX", "IST"), calls)
        self.assertTrue(result["live_search"]["direct_route_intelligence"]["available"])
        skipped = [
            search
            for search in result["live_search"]["segment_searches"]
            if search.get("reason") == "direct_route_schedule_negative"
        ]
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["destination"], "MUC")

    def test_agent_mode_runs_carrier_aggregate_control_and_reports_through_fare_check(self) -> None:
        from flights_cli.cli import apply_agent_mode_defaults

        args = build_parser().parse_args(
            [
                "route",
                "kb-assemble",
                "SVX",
                "DEL",
                "--depart-date",
                "2026-06-01",
                "--agent-mode",
                "--aggregate-control-carrier",
                "SU",
                "--no-live-cache",
                "--no-direct-route-intel",
            ]
        )
        apply_agent_mode_defaults(args)
        calls: list[tuple[str, str, bool, tuple[str, ...]]] = []

        def fake_fetch(origin: str, destination: str, depart_date: object, *, direct_only: bool, only_carriers: list[str], **_: object) -> dict:
            calls.append((origin, destination, bool(direct_only), tuple(only_carriers)))
            depart = depart_date.isoformat() if hasattr(depart_date, "isoformat") else str(depart_date)
            offers = []
            if origin == "SVX" and destination == "DEL" and not direct_only and only_carriers == ["SU"]:
                offers.append(
                    {
                        "id": "su-through-control",
                        "price": 42000,
                        "currency": "RUB",
                        "number_of_changes": 1,
                        "duration": 520,
                        "flight_numbers": ["SU1419", "SU232"],
                        "flights": [
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

        with patch("flights_cli.orchestrators.kb_assemble.fetch_kupibilet_search", side_effect=fake_fetch):
            result = run_kupibilet_route_assembly(args, Store())

        self.assertIn(("SVX", "DEL", False, ("SU",)), calls)
        carrier_controls = [
            control
            for control in result["live_search"]["aggregate_controls"]
            if control.get("filters", {}).get("only_carriers") == ["SU"]
        ]
        self.assertEqual(carrier_controls[0]["top_offers"][0]["flight_numbers"], ["SU1419", "SU232"])
        report = result["agent_report"]
        self.assertEqual(report["through_fare_checks"][0]["carrier"], "SU")
        self.assertIn("Through-fare check required", " ".join(report["answer_lines"]))

    def test_direct_route_intel_skips_absent_direct_control_to_svx(self) -> None:
        args = build_parser().parse_args(
            [
                "route",
                "kb-assemble",
                "MUC",
                "SVX",
                "--depart-date",
                "2026-08-12",
                "--no-live-cache",
            ]
        )
        calls: list[tuple[str, str]] = []
        route_index = {
            "source": "test official schedule",
            "airport": "SVX",
            "fetched_at": "2026-05-07T00:00:00+00:00",
            "source_urls": {"outbound": "test", "return": "test"},
            "routes": {"outbound": ["IST"], "return": ["IST", "DXB"]},
        }

        def fake_fetch(origin: str, destination: str, depart_date: object, **_: object) -> dict:
            calls.append((origin, destination))
            depart = depart_date.isoformat() if hasattr(depart_date, "isoformat") else str(depart_date)
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

        with (
            patch("flights_cli.orchestrators.kb_assemble.load_or_refresh_svx_route_index", return_value=(route_index, {"hit": True, "ttl_seconds": 604800})),
            patch("flights_cli.orchestrators.kb_assemble.fetch_kupibilet_search", side_effect=fake_fetch),
        ):
            result = run_kupibilet_route_assembly(args, Store())

        self.assertNotIn(("MUC", "SVX"), calls)
        skipped = [
            search
            for search in result["live_search"]["segment_searches"]
            if search.get("reason") == "direct_route_schedule_negative"
        ]
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["origin"], "MUC")

    def test_direct_route_intel_keeps_known_beijing_direct_airport(self) -> None:
        args = build_parser().parse_args(
            [
                "route",
                "kb-assemble",
                "SVX",
                "BJS",
                "--depart-date",
                "2026-09-15",
                "--no-live-cache",
            ]
        )
        calls: list[tuple[str, str]] = []
        route_index = {
            "source": "test official schedule",
            "airport": "SVX",
            "fetched_at": "2026-05-07T00:00:00+00:00",
            "source_urls": {"outbound": "test", "return": "test"},
            "routes": {"outbound": ["IST", "DXB", "PKX", "SVO"], "return": []},
        }

        def fake_fetch(origin: str, destination: str, depart_date: object, **_: object) -> dict:
            calls.append((origin, destination))
            depart = depart_date.isoformat() if hasattr(depart_date, "isoformat") else str(depart_date)
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

        with (
            patch("flights_cli.orchestrators.kb_assemble.load_or_refresh_svx_route_index", return_value=(route_index, {"hit": True, "ttl_seconds": 604800})),
            patch("flights_cli.orchestrators.kb_assemble.fetch_kupibilet_search", side_effect=fake_fetch),
        ):
            result = run_kupibilet_route_assembly(args, Store())

        self.assertNotIn(("SVX", "PEK"), calls)
        self.assertIn(("SVX", "PKX"), calls)
        skipped_airports = {
            search.get("skipped_because", {}).get("checked_airport")
            for search in result["live_search"]["segment_searches"]
            if search.get("reason") == "direct_route_schedule_negative"
        }
        self.assertEqual(skipped_airports, {"PEK"})

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
            stored = write_live_cache(key, {"offers": [{"id": "svx-ist"}], "cache": {"stale": True}}, cache_dir=cache_dir)
            self.assertFalse(stored["cache"]["hit"])

            cached = read_live_cache(key, ttl_seconds=60, cache_dir=cache_dir)

            self.assertIsNotNone(cached)
            self.assertTrue(cached["cache"]["hit"])
            self.assertEqual(cached["offers"][0]["id"], "svx-ist")
            self.assertIsNone(read_live_cache(key, ttl_seconds=0, cache_dir=cache_dir))

    def test_cached_kupibilet_search_bypasses_fetcher_on_cache_hit(self) -> None:
        calls: list[tuple[str, str]] = []

        def fake_fetch(origin: str, destination: str, depart_date: object, **_: object) -> dict:
            calls.append((origin, destination))
            depart = depart_date.isoformat() if hasattr(depart_date, "isoformat") else str(depart_date)
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

        with patch("flights_cli.providers.kupibilet.read_live_cache", return_value={"offers": [], "cache": {"hit": True}}):
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
