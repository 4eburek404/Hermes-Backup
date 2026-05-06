from __future__ import annotations

import argparse
import ast
import contextlib
import gzip
import io
import json
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from flights_cli import __version__
from flights_cli.cli import build_parser, normalize_global_json
from flights_cli.domain.carriers import carrier_from_flight_number
from flights_cli.env import load_env_file
from flights_cli.orchestrators.kb_assemble import build_kupibilet_route_segment_plan
from flights_cli.orchestrators.route_plan import build_route_plan
from flights_cli.providers.kupibilet import (
    build_kupibilet_payload,
    decode_http_body,
    kupibilet_result_to_segment_result,
    parse_kupibilet_frontend_search,
)
from flights_cli.providers.u6 import parse_u6_calendar
from flights_cli.services.validation import connection_rule, validate_itinerary
from flights_cli.store import Store


PROJECT = Path(__file__).resolve().parents[1]


class FlightsCliOfflineTests(unittest.TestCase):
    def test_pyproject_version_matches_runtime_version(self) -> None:
        data = tomllib.loads((PROJECT / "pyproject.toml").read_text())
        self.assertEqual(data["project"]["version"], __version__)
        self.assertIn("aeroflot_research*", data["tool"]["setuptools"]["packages"]["find"]["exclude"])

    def test_research_artifacts_are_not_kept_in_runtime_tree(self) -> None:
        self.assertFalse((PROJECT / "aeroflot_research").exists())

    def test_module_dependency_boundaries(self) -> None:
        root = PROJECT / "flights_cli"
        modules = {".".join(path.relative_to(PROJECT).with_suffix("").parts): path for path in root.rglob("*.py")}
        edges: dict[str, set[str]] = {module: set() for module in modules}

        def resolve_target(target: str) -> str | None:
            parts = target.split(".")
            for end in range(len(parts), 0, -1):
                candidate = ".".join(parts[:end])
                if candidate in modules:
                    return candidate
            return None

        for module, path in modules.items():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                target_name = None
                if isinstance(node, ast.ImportFrom) and node.module:
                    if node.level:
                        base = module.split(".")[:-node.level]
                        target_name = ".".join(base + [node.module])
                    else:
                        target_name = node.module
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        target = resolve_target(alias.name)
                        if target and target != module:
                            edges[module].add(target)
                    continue

                if target_name and target_name.startswith("flights_cli"):
                    target = resolve_target(target_name)
                    if target and target != module:
                        edges[module].add(target)

        visiting: list[str] = []
        visited: set[str] = set()
        cycles: list[list[str]] = []

        def visit(module: str) -> None:
            visited.add(module)
            visiting.append(module)
            for target in edges[module]:
                if target not in visited:
                    visit(target)
                elif target in visiting:
                    cycles.append(visiting[visiting.index(target):] + [target])
            visiting.pop()

        for module in modules:
            if module not in visited:
                visit(module)

        forbidden_provider_edges = [
            (source, target)
            for source, targets in edges.items()
            for target in targets
            if source.startswith("flights_cli.providers.") and target.startswith(("flights_cli.cli", "flights_cli.commands."))
        ]
        forbidden_output_edges = [
            (source, target)
            for source, targets in edges.items()
            for target in targets
            if source == "flights_cli.output" and target.startswith(("flights_cli.providers.", "flights_cli.orchestrators.", "flights_cli.commands."))
        ]

        self.assertEqual(cycles, [])
        self.assertEqual(forbidden_provider_edges, [])
        self.assertEqual(forbidden_output_edges, [])

    def test_connection_rule_rejects_ist_saw_short_transfer(self) -> None:
        rule = connection_rule("IST", "SAW", "separate", 180, 300, actual_minutes=55)
        self.assertEqual(rule["severity"], "error")
        self.assertEqual(rule["status"], "too_short")
        self.assertTrue(rule["same_multi_airport_system"])

    def test_validate_itinerary_accepts_same_airport_long_connection(self) -> None:
        data = {
            "ticketing": "separate",
            "segments": [
                {
                    "origin": "SVX",
                    "destination": "IST",
                    "departure_at": "2026-07-19T10:30:00",
                    "arrival_at": "2026-07-19T13:55:00",
                },
                {
                    "origin": "IST",
                    "destination": "LHR",
                    "departure_at": "2026-07-19T20:25:00",
                    "arrival_at": "2026-07-19T22:25:00",
                },
            ],
        }
        args = argparse.Namespace(ticketing="separate", min_same_airport_min=180, min_cross_airport_min=300, profile="safe")
        result = validate_itinerary(data, args)
        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["violation_count"], 0)
        self.assertEqual(result["risk"]["grade"], "excellent")

    def test_route_plan_svx_lon_expands_london_and_counts_segments(self) -> None:
        args = argparse.Namespace(
            origin="SVX",
            destination="LON",
            depart_date="2026-07-19",
            return_date="2026-07-23",
            hub=["IST", "SAW", "AYT"],
            origin_airport=None,
            destination_airport=None,
            currency="RUB",
            direct_only=False,
            ticketing="separate",
            min_same_airport_min=120,
            min_cross_airport_min=300,
            max_airports_per_city=6,
        )
        result = build_route_plan(args, Store())
        self.assertEqual(result["origin_airports"], ["SVX"])
        self.assertEqual(result["destination_airports"], ["LHR", "LGW", "STN", "LTN"])
        self.assertEqual(result["metrics"]["segment_request_count"], 30)
        self.assertEqual(result["itinerary_families"][0]["outbound_airport_compatibility"][0]["required_min"], 120)
        self.assertIn("LON often returns empty in Travelpayouts; use specific London airports.", result["warnings"])

    def test_route_commands_default_same_airport_minimum_is_120(self) -> None:
        parser = build_parser()
        cases = [
            ["route", "plan", "SVX", "LON", "--depart-date", "2026-07-20"],
            ["route", "validate"],
            ["route", "rank"],
            ["route", "assemble"],
        ]
        for argv in cases:
            with self.subTest(argv=argv):
                args = parser.parse_args(argv)
                self.assertEqual(args.min_same_airport_min, 120)
                self.assertEqual(args.min_cross_airport_min, 300)
        assemble_args = parser.parse_args(["route", "assemble"])
        self.assertEqual(assemble_args.limit_per_pair, 10)

    def test_carrier_from_flight_number_handles_alphanumeric_iata_codes(self) -> None:
        self.assertEqual(carrier_from_flight_number("5N294"), "5N")
        self.assertEqual(carrier_from_flight_number("U6264"), "U6")
        self.assertEqual(carrier_from_flight_number("N41015"), "N4")
        self.assertEqual(carrier_from_flight_number("SU630"), "SU")

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

    def test_su_flights_legacy_command_is_removed(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as ctx:
            build_parser().parse_args(["su-flights", "SVX", "SVO", "--depart-date", "2026-07-19"])

        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("invalid choice", stderr.getvalue())

    def test_route_rank_profiles_change_order(self) -> None:
        payload = {
            "itineraries": [
                {
                    "id": "safe_ist",
                    "price": 92817,
                    "segments": [
                        {
                            "origin": "SVX",
                            "destination": "IST",
                            "departure_at": "2026-07-19T10:30:00",
                            "arrival_at": "2026-07-19T13:55:00",
                            "carrier": "SU",
                        },
                        {
                            "origin": "IST",
                            "destination": "LHR",
                            "departure_at": "2026-07-19T20:25:00",
                            "arrival_at": "2026-07-19T22:25:00",
                            "carrier": "TK",
                        },
                    ],
                },
                {
                    "id": "cheap_ayt",
                    "price": 74034,
                    "segments": [
                        {
                            "origin": "SVX",
                            "destination": "AYT",
                            "departure_at": "2026-07-19T01:45:00",
                            "arrival_at": "2026-07-19T04:50:00",
                            "carrier": "SU",
                        },
                        {
                            "origin": "AYT",
                            "destination": "LGW",
                            "departure_at": "2026-07-19T07:55:00",
                            "arrival_at": "2026-07-19T10:35:00",
                            "carrier": "XQ",
                        },
                    ],
                },
            ]
        }

        safe = self._rank(payload, "safe")
        cheap = self._rank(payload, "cheap")
        self.assertEqual(safe["data"]["ranked"][0]["id"], "safe_ist")
        self.assertEqual(cheap["data"]["ranked"][0]["id"], "cheap_ayt")
        self.assertGreater(safe["data"]["ranked"][1]["risk"]["score"], safe["data"]["ranked"][0]["risk"]["score"])

    def test_route_rank_carrier_selection_flags(self) -> None:
        payload = {
            "itineraries": [
                {
                    "id": "tk_choice",
                    "price": 20000,
                    "journeys": [
                        {
                            "direction": "outbound",
                            "segments": [
                                {
                                    "origin": "IST",
                                    "destination": "LHR",
                                    "departure_at": "2026-07-19T10:00:00+03:00",
                                    "arrival_at": "2026-07-19T12:00:00+01:00",
                                    "carrier": "TK",
                                }
                            ],
                        }
                    ],
                },
                {
                    "id": "dp_choice",
                    "price": 10000,
                    "journeys": [
                        {
                            "direction": "outbound",
                            "segments": [
                                {
                                    "origin": "IST",
                                    "destination": "LHR",
                                    "departure_at": "2026-07-19T11:00:00+03:00",
                                    "arrival_at": "2026-07-19T13:00:00+01:00",
                                    "carrier": "DP",
                                }
                            ],
                        }
                    ],
                },
            ]
        }

        only_tk = self._rank(payload, "balanced", "--only-carrier", "TK")
        self.assertEqual(only_tk["data"]["count"], 1)
        self.assertEqual(only_tk["data"]["ranked"][0]["id"], "tk_choice")
        self.assertEqual(only_tk["data"]["carrier_policy"]["filtered_count"], 1)
        self.assertEqual(only_tk["data"]["carrier_policy"]["filtered"][0]["id"], "dp_choice")

        prefer_tk = self._rank(payload, "balanced", "--prefer-carrier", "TK")
        self.assertEqual(prefer_tk["data"]["ranked"][0]["id"], "tk_choice")
        self.assertIn("preferred_carrier_match", {r["code"] for r in prefer_tk["data"]["ranked"][0]["risk"]["top_reasons"]})
        self.assertIn("missing_preferred_carrier", {r["code"] for r in prefer_tk["data"]["ranked"][1]["risk"]["top_reasons"]})

        avoid_dp = self._rank(payload, "balanced", "--avoid-carrier", "DP")
        self.assertEqual(avoid_dp["data"]["ranked"][0]["id"], "tk_choice")
        self.assertIn("avoided_carrier", {r["code"] for r in avoid_dp["data"]["ranked"][1]["risk"]["top_reasons"]})

    def test_results_parse_and_route_assemble(self) -> None:
        segment_results = [
            self._parse_raw(
                {
                    "data": {
                        "prices_one_way": [
                            {
                                "departure_at": "2026-07-19T10:30:00",
                                "value": 24766,
                                "number_of_changes": 0,
                                "main_airline": "SU",
                                "duration": 205,
                                "segments": [
                                    {
                                        "departure_at": "2026-07-19T10:30:00",
                                        "arrival_at": "2026-07-19T13:55:00",
                                        "flight_legs": [
                                            {
                                                "origin": "SVX",
                                                "destination": "IST",
                                                "flight_number": "SU630",
                                                "operating_carrier": "SU",
                                                "departure_at": "2026-07-19T10:30:00",
                                                "arrival_at": "2026-07-19T13:55:00",
                                            }
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                },
                "origin_to_hub",
                "SVX",
                "IST",
            )["data"]["segment_result"],
            self._parse_raw(
                {
                    "data": {
                        "prices_one_way": [
                            {
                                "departure_at": "2026-07-19T20:25:00",
                                "value": 11037,
                                "number_of_changes": 0,
                                "main_airline": "TK",
                                "duration": 240,
                                "segments": [
                                    {
                                        "departure_at": "2026-07-19T20:25:00",
                                        "arrival_at": "2026-07-19T22:25:00",
                                        "flight_legs": [
                                            {
                                                "origin": "IST",
                                                "destination": "LHR",
                                                "flight_number": "TK1987",
                                                "operating_carrier": "TK",
                                                "departure_at": "2026-07-19T20:25:00",
                                                "arrival_at": "2026-07-19T22:25:00",
                                            }
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                },
                "hub_to_destination",
                "IST",
                "LHR",
            )["data"]["segment_result"],
        ]
        assembled = self._assemble({"segment_results": segment_results})
        self.assertEqual(assembled["data"]["assembly"]["candidate_count"], 1)
        self.assertEqual(assembled["data"]["ranked"][0]["price"], 35803)
        self.assertEqual(assembled["data"]["ranked"][0]["risk"]["grade"], "excellent")

    def test_route_assemble_default_depth_preserves_frontier_relevant_option(self) -> None:
        """Single-axis sorted segment lists must not hide the 6th-by-price frontier option."""

        def offer(
            offer_id: str,
            origin: str,
            destination: str,
            departure_at: str,
            arrival_at: str,
            price: int,
            flight_number: str,
            carrier: str,
        ) -> dict:
            return {
                "id": offer_id,
                "origin": origin,
                "destination": destination,
                "departure_airport": origin,
                "arrival_airport": destination,
                "departure_at": departure_at,
                "arrival_at": arrival_at,
                "price": price,
                "currency": "RUB",
                "segments": [
                    {
                        "origin": origin,
                        "destination": destination,
                        "departure_at": departure_at,
                        "arrival_at": arrival_at,
                        "flight_number": flight_number,
                        "carrier": carrier,
                    }
                ],
            }

        segment_results = [
            {
                "direction": "outbound",
                "leg": "origin_to_hub",
                "query": {"origin": "SVX", "destination": "IST", "date": "2026-07-19", "currency": "RUB"},
                "offers": [
                    offer("su630", "SVX", "IST", "2026-07-19T10:30:00+05:00", "2026-07-19T13:55:00+03:00", 26032, "SU630", "SU"),
                    offer("u6773", "SVX", "IST", "2026-07-19T07:20:00+05:00", "2026-07-19T10:50:00+03:00", 48265, "U6773", "U6"),
                ],
            },
            {
                "direction": "outbound",
                "leg": "hub_to_destination",
                "query": {"origin": "IST", "destination": "LHR", "date": "2026-07-19", "currency": "RUB"},
                "offers": [
                    offer("tk1987", "IST", "LHR", "2026-07-19T20:25:00+03:00", "2026-07-19T22:25:00+01:00", 10379, "TK1987", "TK"),
                    offer("tk1979", "IST", "LHR", "2026-07-19T07:50:00+03:00", "2026-07-19T09:50:00+01:00", 13368, "TK1979", "TK"),
                    offer("tk1989", "IST", "LHR", "2026-07-19T09:40:00+03:00", "2026-07-19T11:40:00+01:00", 15012, "TK1989", "TK"),
                    offer("tk1971", "IST", "LHR", "2026-07-19T14:50:00+03:00", "2026-07-19T16:40:00+01:00", 15012, "TK1971", "TK"),
                    offer("tk1983", "IST", "LHR", "2026-07-19T19:05:00+03:00", "2026-07-19T21:05:00+01:00", 15387, "TK1983", "TK"),
                    offer("tk1985", "IST", "LHR", "2026-07-19T13:15:00+03:00", "2026-07-19T15:10:00+01:00", 16881, "TK1985", "TK"),
                ],
            },
        ]

        assembled = self._assemble({"segment_results": segment_results}, "--include-candidates", "100")
        self.assertEqual(assembled["data"]["assembly"]["limit_per_pair"], 10)
        self.assertTrue(
            any(
                [
                    segment.get("flight_number")
                    for journey in candidate.get("journeys", [])
                    for segment in journey.get("segments", [])
                ]
                == ["U6773", "TK1985"]
                for candidate in assembled["data"]["candidates"]
            )
        )

    def test_results_parse_preserves_transfer_metadata_for_risk(self) -> None:
        parsed = self._parse_raw(
            {
                "data": {
                    "prices_one_way": [
                        {
                            "departure_at": "2026-07-19T19:50:00+05:00",
                            "value": 25258,
                            "number_of_changes": 1,
                            "main_airline": "DP",
                            "duration": 1100,
                            "segments": [
                                {
                                    "departure_at": "2026-07-19T19:50:00+05:00",
                                    "arrival_at": "2026-07-20T12:10:00+03:00",
                                    "flight_legs": [
                                        {
                                            "origin": "SVX",
                                            "destination": "VKO",
                                            "flight_number": "DP408",
                                            "operating_carrier": "DP",
                                            "departure_at": "2026-07-19T19:50:00+05:00",
                                            "arrival_at": "2026-07-19T20:20:00+03:00",
                                        },
                                        {
                                            "origin": "VKO",
                                            "destination": "IST",
                                            "flight_number": "DP993",
                                            "operating_carrier": "DP",
                                            "departure_at": "2026-07-20T06:50:00+03:00",
                                            "arrival_at": "2026-07-20T12:10:00+03:00",
                                        },
                                    ],
                                    "transfers": [
                                        {
                                            "at": "VKO",
                                            "to": "VKO",
                                            "country_code": "RU",
                                            "duration_seconds": 37800,
                                            "night_transfer": True,
                                            "visa_required": False,
                                        }
                                    ],
                                }
                            ],
                        }
                    ]
                }
            },
            "origin_to_hub",
            "SVX",
            "IST",
        )
        offer = parsed["data"]["segment_result"]["offers"][0]
        self.assertEqual(offer["transfers"][0]["at"], "VKO")
        self.assertTrue(offer["segments"][0]["transfer_after"]["night_transfer"])

        args = argparse.Namespace(ticketing="separate", min_same_airport_min=180, min_cross_airport_min=300, profile="safe")
        validation = validate_itinerary({"price": offer["price"], "segments": offer["segments"]}, args)
        codes = {component["code"] for component in validation["risk"]["components"]}
        self.assertIn("api_night_transfer", codes)
        self.assertIn("long_internal_transfer", codes)

    def test_round_trip_parse_selects_return_segment(self) -> None:
        payload = {
            "data": {
                "prices_round_trip": [
                    {
                        "departure_at": "2026-07-19T10:30:00+05:00",
                        "return_at": "2026-07-23T14:05:00+03:00",
                        "value": 41000,
                        "number_of_changes": 0,
                        "main_airline": "SU",
                        "duration": 650,
                        "segments": [
                            {
                                "departure_at": "2026-07-19T10:30:00+05:00",
                                "arrival_at": "2026-07-19T13:55:00+03:00",
                                "flight_legs": [
                                    {
                                        "origin": "SVX",
                                        "destination": "IST",
                                        "flight_number": "SU630",
                                        "operating_carrier": "SU",
                                        "departure_at": "2026-07-19T10:30:00+05:00",
                                        "arrival_at": "2026-07-19T13:55:00+03:00",
                                    }
                                ],
                            },
                            {
                                "departure_at": "2026-07-23T14:05:00+03:00",
                                "arrival_at": "2026-07-23T21:05:00+05:00",
                                "flight_legs": [
                                    {
                                        "origin": "IST",
                                        "destination": "SVX",
                                        "flight_number": "SU631",
                                        "operating_carrier": "SU",
                                        "departure_at": "2026-07-23T14:05:00+03:00",
                                        "arrival_at": "2026-07-23T21:05:00+05:00",
                                    }
                                ],
                            },
                        ],
                    }
                ]
            }
        }
        outbound = self._parse_raw(payload, "origin_to_hub", "SVX", "IST", direction="outbound", date="2026-07-19")
        returned = self._parse_raw(payload, "hub_to_origin", "IST", "SVX", direction="return", date="2026-07-23")

        self.assertEqual(outbound["data"]["segment_result"]["offers"][0]["origin"], "SVX")
        self.assertEqual(outbound["data"]["segment_result"]["offers"][0]["destination"], "IST")
        self.assertEqual(returned["data"]["segment_result"]["offers"][0]["origin"], "IST")
        self.assertEqual(returned["data"]["segment_result"]["offers"][0]["destination"], "SVX")
        self.assertEqual(returned["data"]["segment_result"]["offers"][0]["selected_trip_segment_index"], 1)

        envelope = {
            "ok": True,
            "data": {
                "request": {
                    "variables": {
                        "origin": "SVX",
                        "destination": "IST",
                        "depart_dates": ["2026-07-19"],
                        "return_dates": ["2026-07-23"],
                        "currency": "RUB",
                    }
                },
                "live": {"data": payload},
            },
        }
        inferred = self._parse_raw(envelope, "hub_to_origin", None, None, direction="return", date="2026-07-23")
        self.assertEqual(inferred["data"]["segment_result"]["query"]["origin"], "IST")
        self.assertEqual(inferred["data"]["segment_result"]["query"]["destination"], "SVX")

    def test_route_assemble_reports_rejected_airport_pairs(self) -> None:
        segment_results = [
            {
                "direction": "outbound",
                "leg": "origin_to_hub",
                "query": {"origin": "SVX", "destination": "IST", "date": "2026-07-19", "currency": "RUB"},
                "offers": [
                    {
                        "id": "svx-saw-hidden",
                        "origin": "SVX",
                        "destination": "SAW",
                        "departure_airport": "SVX",
                        "arrival_airport": "SAW",
                        "departure_at": "2026-07-19T19:50:00+05:00",
                        "arrival_at": "2026-07-20T06:00:00+03:00",
                        "price": 30677,
                        "currency": "RUB",
                        "segments": [
                            {
                                "origin": "SVX",
                                "destination": "SAW",
                                "departure_at": "2026-07-19T19:50:00+05:00",
                                "arrival_at": "2026-07-20T06:00:00+03:00",
                                "carrier": "VF",
                            }
                        ],
                    }
                ],
            },
            {
                "direction": "outbound",
                "leg": "hub_to_destination",
                "query": {"origin": "IST", "destination": "LHR", "date": "2026-07-19", "currency": "RUB"},
                "offers": [
                    {
                        "id": "ist-lhr",
                        "origin": "IST",
                        "destination": "LHR",
                        "departure_airport": "IST",
                        "arrival_airport": "LHR",
                        "departure_at": "2026-07-20T12:00:00+03:00",
                        "arrival_at": "2026-07-20T14:00:00+01:00",
                        "price": 12000,
                        "currency": "RUB",
                        "segments": [
                            {
                                "origin": "IST",
                                "destination": "LHR",
                                "departure_at": "2026-07-20T12:00:00+03:00",
                                "arrival_at": "2026-07-20T14:00:00+01:00",
                                "carrier": "TK",
                            }
                        ],
                    }
                ],
            },
        ]
        assembled = self._assemble({"segment_results": segment_results})
        self.assertEqual(assembled["data"]["assembly"]["candidate_count"], 0)
        self.assertEqual(assembled["data"]["assembly"]["rejected_pair_count"], 1)
        self.assertGreaterEqual(assembled["data"]["rejected_pairs"][0]["actual_min"], assembled["data"]["rejected_pairs"][0]["required_min"])
        self.assertEqual(assembled["data"]["rejected_pairs"][0]["reason"], "ground_transfer_required")
        self.assertEqual(assembled["data"]["rejected_pairs"][0]["airport_pair_status"], "ground_transfer_required")
        self.assertEqual(assembled["data"]["rejected_pairs"][0]["airport_group"], "Istanbul")
        self.assertTrue(assembled["data"]["rejected_pairs"][0]["same_multi_airport_system"])

    def test_route_assemble_keeps_too_short_same_airport_pair_as_invalid_candidate(self) -> None:
        segment_results = [
            {
                "direction": "outbound",
                "leg": "origin_to_hub",
                "query": {"origin": "SVX", "destination": "IST", "date": "2026-07-19", "currency": "RUB"},
                "offers": [
                    {
                        "id": "svx-ist",
                        "origin": "SVX",
                        "destination": "IST",
                        "departure_airport": "SVX",
                        "arrival_airport": "IST",
                        "departure_at": "2026-07-19T10:00:00",
                        "arrival_at": "2026-07-19T12:00:00",
                        "price": 10000,
                        "currency": "RUB",
                        "segments": [
                            {
                                "origin": "SVX",
                                "destination": "IST",
                                "departure_at": "2026-07-19T10:00:00",
                                "arrival_at": "2026-07-19T12:00:00",
                                "carrier": "SU",
                            }
                        ],
                    }
                ],
            },
            {
                "direction": "outbound",
                "leg": "hub_to_destination",
                "query": {"origin": "IST", "destination": "LHR", "date": "2026-07-19", "currency": "RUB"},
                "offers": [
                    {
                        "id": "ist-lhr",
                        "origin": "IST",
                        "destination": "LHR",
                        "departure_airport": "IST",
                        "arrival_airport": "LHR",
                        "departure_at": "2026-07-19T12:30:00",
                        "arrival_at": "2026-07-19T14:30:00",
                        "price": 12000,
                        "currency": "RUB",
                        "segments": [
                            {
                                "origin": "IST",
                                "destination": "LHR",
                                "departure_at": "2026-07-19T12:30:00",
                                "arrival_at": "2026-07-19T14:30:00",
                                "carrier": "TK",
                            }
                        ],
                    }
                ],
            },
        ]

        assembled = self._assemble({"segment_results": segment_results})

        self.assertEqual(assembled["data"]["assembly"]["candidate_count"], 1)
        self.assertEqual(assembled["data"]["assembly"]["rejected_pair_count"], 0)
        self.assertFalse(assembled["data"]["ranked"][0]["ok"])
        self.assertEqual(assembled["data"]["ranked"][0]["connections"][0]["status"], "too_short")

    def test_load_env_file_reads_hermes_dotenv_without_overriding(self) -> None:
        old_token = os.environ.pop("TRAVELPAYOUTS_TOKEN", None)
        old_marker = os.environ.pop("TRAVELPAYOUTS_MARKER", None)
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                env_path = Path(tmp_dir) / ".env"
                env_path.write_text("TRAVELPAYOUTS_TOKEN=file-token\nTRAVELPAYOUTS_MARKER=file-marker\n", encoding="utf-8")
                loaded = load_env_file(env_path)
                self.assertEqual(os.environ["TRAVELPAYOUTS_TOKEN"], "file-token")
                self.assertEqual(os.environ["TRAVELPAYOUTS_MARKER"], "file-marker")
                self.assertEqual(loaded, {"TRAVELPAYOUTS_TOKEN", "TRAVELPAYOUTS_MARKER"})

                os.environ["TRAVELPAYOUTS_TOKEN"] = "external-token"
                loaded_again = load_env_file(env_path)
                self.assertEqual(os.environ["TRAVELPAYOUTS_TOKEN"], "external-token")
                self.assertEqual(loaded_again, set())
        finally:
            if old_token is not None:
                os.environ["TRAVELPAYOUTS_TOKEN"] = old_token
            else:
                os.environ.pop("TRAVELPAYOUTS_TOKEN", None)
            if old_marker is not None:
                os.environ["TRAVELPAYOUTS_MARKER"] = old_marker
            else:
                os.environ.pop("TRAVELPAYOUTS_MARKER", None)

    def test_json_doctor_envelope(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "flights_cli", "--json", "doctor"],
            cwd=PROJECT,
            env={"PYTHONPATH": str(PROJECT)},
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "doctor")
        self.assertIn("cache_counts", payload["data"])
        self.assertEqual(payload["data"]["safety"]["travelpayouts_live_requires"], "request search --live")
        self.assertEqual(payload["data"]["safety"]["live_provider_commands"], ["kb-search", "u6-prices", "route kb-assemble"])
        self.assertNotIn("live_calls_require_flag", payload["data"]["safety"])

        human_proc = subprocess.run(
            [sys.executable, "-m", "flights_cli", "doctor"],
            cwd=PROJECT,
            env={"PYTHONPATH": str(PROJECT)},
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertIn("Travelpayouts live: request search --live", human_proc.stdout)
        self.assertIn("provider live commands: kb-search, u6-prices, route kb-assemble", human_proc.stdout)

    def test_json_route_plan_envelope_and_repeatable_hubs(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "flights_cli",
                "--json",
                "route",
                "plan",
                "SVX",
                "LON",
                "--depart-date",
                "2026-07-20",
                "--hub",
                "IST",
                "--hub",
                "DXB",
            ],
            cwd=PROJECT,
            env={"PYTHONPATH": str(PROJECT)},
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "route plan")
        data = payload["data"]
        self.assertEqual(data["hubs"], ["IST", "DXB"])
        self.assertEqual(data["destination_airports"], ["LHR", "LGW", "STN", "LTN"])
        self.assertEqual(data["metrics"]["segment_request_count"], 10)
        self.assertIn("warnings", data)
        self.assertNotIn("cache_age_minutes", data)

    def test_normalize_global_json_accepts_trailing_json(self) -> None:
        argv = ["flights", "route", "plan", "SVX", "LON", "--json"]
        self.assertEqual(normalize_global_json(argv), ["flights", "--json", "route", "plan", "SVX", "LON"])

    # ── U6 price calendar parsing tests ────────────────────────────────

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
        """Empty response is not a hard error — it's a signal."""
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

    def _rank(self, payload: dict, profile: str, *extra_args: str) -> dict:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "flights_cli",
                "--json",
                "route",
                "rank",
                "--profile",
                profile,
                "--input",
                "-",
                *extra_args,
            ],
            cwd=PROJECT,
            env={"PYTHONPATH": str(PROJECT)},
            input=json.dumps(payload),
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return json.loads(proc.stdout)

    def _parse_raw(
        self,
        payload: dict,
        leg: str,
        origin: str | None,
        destination: str | None,
        *,
        direction: str = "outbound",
        date: str = "2026-07-19",
    ) -> dict:
        cmd = [
            sys.executable,
            "-m",
            "flights_cli",
            "--json",
            "results",
            "parse",
            "--direction",
            direction,
            "--leg",
            leg,
            "--date",
            date,
            "--currency",
            "RUB",
            "--input",
            "-",
        ]
        if origin is not None:
            cmd.extend(["--origin", origin])
        if destination is not None:
            cmd.extend(["--destination", destination])
        proc = subprocess.run(
            cmd,
            cwd=PROJECT,
            env={"PYTHONPATH": str(PROJECT)},
            input=json.dumps(payload),
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return json.loads(proc.stdout)

    def _assemble(self, payload: dict, *extra_args: str) -> dict:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "flights_cli",
                "--json",
                "route",
                "assemble",
                "--profile",
                "safe",
                "--input",
                "-",
                *extra_args,
            ],
            cwd=PROJECT,
            env={"PYTHONPATH": str(PROJECT)},
            input=json.dumps(payload),
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return json.loads(proc.stdout)


if __name__ == "__main__":
    unittest.main()
