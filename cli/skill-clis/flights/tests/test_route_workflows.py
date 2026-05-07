from __future__ import annotations

import argparse
import json
import subprocess
import sys
import unittest

from flights_cli.config import DEFAULT_ROUTE_HUBS
from flights_cli.domain.carriers import carrier_from_flight_number
from flights_cli.orchestrators.route_plan import build_route_plan
from flights_cli.services.validation import connection_rule, validate_itinerary
from flights_cli.store import Store

from helpers import CliSubprocessMixin, PROJECT, TEST_ENV


class RouteWorkflowTests(CliSubprocessMixin, unittest.TestCase):
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

    def test_route_plan_uses_ru_priority_strategy_when_no_hubs_are_passed(self) -> None:
        args = argparse.Namespace(
            origin="SVX",
            destination="MUC",
            depart_date="2026-08-12",
            return_date=None,
            hub=None,
            routing_strategy="auto",
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

        self.assertEqual(result["routing_strategy"], "ru-priority")
        self.assertEqual(result["hubs"], ["IST", "DXB"])
        self.assertEqual(result["hub_source"], "strategy")
        self.assertEqual(result["metrics"]["segment_request_count"], 7)
        self.assertEqual(
            [(segment["origin"], segment["destination"], segment["leg"]) for segment in result["segments"]],
            [
                ("SVX", "MUC", "direct_outbound"),
                ("SVX", "IST", "origin_to_hub"),
                ("SVX", "SVO", "origin_to_gateway"),
                ("SVO", "IST", "gateway_to_hub"),
                ("IST", "MUC", "hub_to_destination"),
                ("SVX", "DXB", "origin_to_hub"),
                ("DXB", "MUC", "hub_to_destination"),
            ],
        )
        self.assertTrue(all("--direct-only" in segment["command"] for segment in result["segments"]))
        self.assertEqual(result["route_families"][2]["required_carriers"], ["SU"])
        self.assertIn("SVO", result["metrics"]["unique_airports_considered"])
        self.assertNotIn("route_graph", result)

    def test_route_plan_uses_asia_profile_for_beijing(self) -> None:
        args = argparse.Namespace(
            origin="SVX",
            destination="BJS",
            depart_date="2026-09-15",
            return_date="2026-09-20",
            hub=None,
            routing_strategy="auto",
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

        self.assertEqual(result["routing_profile"], "asia-oceania")
        self.assertEqual(result["destination_airports"], ["PEK", "PKX"])
        self.assertEqual(result["hubs"], ["SVO", "IST", "DXB"])
        self.assertEqual(result["metrics"]["segment_request_count"], 26)
        self.assertIn("svo_asia", {family["id"] for family in result["route_families"]})
        segments = {
            (segment["direction"], segment["origin"], segment["destination"], segment["leg"], segment.get("route_family"))
            for segment in result["segments"]
        }
        self.assertIn(("outbound", "SVX", "PEK", "direct_outbound", "direct_control"), segments)
        self.assertIn(("outbound", "SVX", "SVO", "origin_to_hub", "svo_asia"), segments)
        self.assertIn(("outbound", "SVO", "PEK", "hub_to_destination", "svo_asia"), segments)
        self.assertIn(("return", "PEK", "SVX", "direct_return", "direct_control"), segments)
        self.assertIn(("return", "SVO", "SVX", "hub_to_origin", "svo_asia"), segments)

    def test_route_plan_hub_list_strategy_uses_default_hubs(self) -> None:
        args = argparse.Namespace(
            origin="SVX",
            destination="LON",
            depart_date="2026-07-19",
            return_date="2026-07-23",
            hub=None,
            routing_strategy="hub-list",
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

        self.assertEqual(result["hubs"], list(DEFAULT_ROUTE_HUBS))
        self.assertEqual(result["hub_source"], "default")
        self.assertEqual(result["metrics"]["segment_request_count"], len(DEFAULT_ROUTE_HUBS) * 10)

    def test_carrier_from_flight_number_handles_alphanumeric_iata_codes(self) -> None:
        self.assertEqual(carrier_from_flight_number("5N294"), "5N")
        self.assertEqual(carrier_from_flight_number("U6264"), "U6")
        self.assertEqual(carrier_from_flight_number("N41015"), "N4")
        self.assertEqual(carrier_from_flight_number("SU630"), "SU")

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

    def test_route_assemble_agent_mode_adds_compact_report_with_segments(self) -> None:
        def offer(
            offer_id: str,
            origin: str,
            destination: str,
            departure_at: str,
            arrival_at: str,
            price: int,
            flight_number: str,
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
                        "carrier": flight_number[:2],
                    }
                ],
            }

        segment_results = [
            {
                "direction": "outbound",
                "leg": "origin_to_hub",
                "query": {"origin": "SVX", "destination": "IST", "date": "2026-07-19", "currency": "RUB"},
                "offers": [
                    offer("svx-ist", "SVX", "IST", "2026-07-19T10:30:00+05:00", "2026-07-19T13:55:00+03:00", 24000, "SU630")
                ],
            },
            {
                "direction": "outbound",
                "leg": "hub_to_destination",
                "query": {"origin": "IST", "destination": "DEL", "date": "2026-07-19", "currency": "RUB"},
                "offers": [
                    offer("ist-del", "IST", "DEL", "2026-07-19T20:00:00+03:00", "2026-07-20T04:30:00+05:30", 30000, "TK716")
                ],
            },
        ]

        assembled = self._assemble({"segment_results": segment_results}, "--agent-mode")
        report = assembled["data"]["agent_report"]

        self.assertEqual(assembled["data"]["candidates"], [])
        self.assertEqual(report["schema_version"], "agent_report.v1")
        self.assertEqual(report["recommended_options"][0]["segments"][0]["flight_number"], "SU630")
        self.assertIn("Best CLI-ranked option", report["answer_lines"][0])
        self.assertIn("does not construct GDS", report["source_boundaries"][0])

    def test_agent_report_surfaces_hidden_all_su_svo_priority_option(self) -> None:
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
                "query": {"origin": "SVX", "destination": "IST", "date": "2026-06-14", "currency": "RUB"},
                "offers": [
                    offer("svx-ist", "SVX", "IST", "2026-06-14T07:00:00+05:00", "2026-06-14T09:00:00+03:00", 14000, "SU630", "SU"),
                    offer("svx-svo", "SVX", "SVO", "2026-06-14T16:30:00+05:00", "2026-06-14T17:15:00+03:00", 19662, "SU1403", "SU"),
                ],
            },
            {
                "direction": "outbound",
                "leg": "hub_to_destination",
                "query": {"origin": "SVO", "destination": "DEL", "date": "2026-06-14", "currency": "RUB"},
                "offers": [
                    offer("ist-del", "IST", "DEL", "2026-06-14T13:00:00+03:00", "2026-06-14T20:30:00+05:30", 22000, "6E18", "6E"),
                    offer("svo-del", "SVO", "DEL", "2026-06-14T21:20:00+03:00", "2026-06-15T06:00:00+05:30", 24660, "SU232", "SU"),
                ],
            },
        ]

        assembled = self._assemble(
            {"segment_results": segment_results},
            "--agent-mode",
            "--max-candidates",
            "1",
            "--include-ranked-candidates",
            "1",
        )
        report = assembled["data"]["agent_report"]

        self.assertEqual(len(assembled["data"]["ranked"]), 1)
        self.assertEqual(assembled["data"]["ranked"][0]["id"], "assembled-1:SVX-DEL")
        self.assertEqual(report["priority_options"][0]["category"], "all_su_svo")
        self.assertGreater(report["priority_options"][0]["rank"], 1)
        self.assertEqual(
            [segment["flight_number"] for segment in report["priority_options"][0]["segments"]],
            ["SU1403", "SU232"],
        )
        self.assertEqual(report["through_fare_checks"][0]["carrier"], "SU")
        self.assertIn("Priority control", " ".join(report["answer_lines"]))

    def test_agent_brief_json_returns_only_report(self) -> None:
        payload = {
            "segment_results": [
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
                            "departure_at": "2026-07-19T10:30:00+05:00",
                            "arrival_at": "2026-07-19T13:55:00+03:00",
                            "price": 24000,
                            "currency": "RUB",
                            "segments": [
                                {
                                    "origin": "SVX",
                                    "destination": "IST",
                                    "departure_at": "2026-07-19T10:30:00+05:00",
                                    "arrival_at": "2026-07-19T13:55:00+03:00",
                                    "flight_number": "SU630",
                                    "carrier": "SU",
                                }
                            ],
                        }
                    ],
                },
                {
                    "direction": "outbound",
                    "leg": "hub_to_destination",
                    "query": {"origin": "IST", "destination": "DEL", "date": "2026-07-19", "currency": "RUB"},
                    "offers": [
                        {
                            "id": "ist-del",
                            "origin": "IST",
                            "destination": "DEL",
                            "departure_airport": "IST",
                            "arrival_airport": "DEL",
                            "departure_at": "2026-07-19T20:00:00+03:00",
                            "arrival_at": "2026-07-20T04:30:00+05:30",
                            "price": 30000,
                            "currency": "RUB",
                            "segments": [
                                {
                                    "origin": "IST",
                                    "destination": "DEL",
                                    "departure_at": "2026-07-19T20:00:00+03:00",
                                    "arrival_at": "2026-07-20T04:30:00+05:30",
                                    "flight_number": "TK716",
                                    "carrier": "TK",
                                }
                            ],
                        }
                    ],
                },
            ]
        }

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
                "--agent-brief",
                "--input",
                "-",
            ],
            cwd=PROJECT,
            env=TEST_ENV,
            input=json.dumps(payload),
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        result = json.loads(proc.stdout)

        self.assertTrue(result["ok"])
        self.assertEqual(set(result["data"]), {"agent_report"})
        self.assertIn("answer_lines", result["data"]["agent_report"])

    def test_route_assemble_combines_hub_outbound_with_direct_return_and_dedupes(self) -> None:
        def offer(
            offer_id: str,
            origin: str,
            destination: str,
            departure_at: str,
            arrival_at: str,
            price: int,
            flight_number: str,
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
                        "carrier": flight_number[:2],
                    }
                ],
            }

        direct_return = offer(
            "muc-svx",
            "MUC",
            "SVX",
            "2026-08-19T14:00:00+02:00",
            "2026-08-19T22:30:00+05:00",
            20000,
            "U61234",
        )
        segment_results = [
            {
                "direction": "outbound",
                "leg": "origin_to_hub",
                "query": {"origin": "SVX", "destination": "IST", "date": "2026-08-12", "currency": "RUB"},
                "offers": [
                    offer("svx-ist", "SVX", "IST", "2026-08-12T06:00:00+05:00", "2026-08-12T09:00:00+03:00", 10000, "SU630")
                ],
            },
            {
                "direction": "outbound",
                "leg": "hub_to_destination",
                "query": {"origin": "IST", "destination": "MUC", "date": "2026-08-12", "currency": "RUB"},
                "offers": [
                    offer("ist-muc", "IST", "MUC", "2026-08-12T14:00:00+03:00", "2026-08-12T16:00:00+02:00", 12000, "TK1635")
                ],
            },
            {
                "direction": "return",
                "leg": "direct_return",
                "query": {"origin": "MUC", "destination": "SVX", "date": "2026-08-19", "currency": "RUB"},
                "offers": [direct_return],
            },
            {
                "direction": "return",
                "leg": "direct_return",
                "query": {"origin": "MUC", "destination": "SVX", "date": "2026-08-19", "currency": "RUB"},
                "offers": [dict(direct_return)],
            },
        ]

        assembled = self._assemble({"segment_results": segment_results}, "--include-ranked-candidates", "1")

        self.assertEqual(assembled["data"]["assembly"]["outbound_pair_count"], 1)
        self.assertEqual(assembled["data"]["assembly"]["return_direct_count"], 2)
        self.assertEqual(assembled["data"]["assembly"]["raw_candidate_count"], 2)
        self.assertEqual(assembled["data"]["assembly"]["candidate_duplicate_count"], 1)
        self.assertEqual(assembled["data"]["assembly"]["candidate_count"], 1)
        journeys = assembled["data"]["ranked_candidates"][0]["candidate"]["journeys"]
        self.assertEqual([len(journey["segments"]) for journey in journeys], [2, 1])

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

    def test_route_assemble_caps_after_ranking_and_includes_ranked_details(self) -> None:
        def offer(
            offer_id: str,
            origin: str,
            destination: str,
            departure_at: str,
            arrival_at: str,
            price: int,
            flight_number: str,
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
                        "carrier": flight_number[:2],
                    }
                ],
            }

        segment_results = [
            {
                "direction": "outbound",
                "leg": "origin_to_hub",
                "query": {"origin": "SVX", "destination": "IST", "date": "2026-07-19", "currency": "RUB"},
                "offers": [
                    offer("cheap_first", "SVX", "IST", "2026-07-19T10:30:00+05:00", "2026-07-19T13:55:00+03:00", 100, "SU630"),
                    offer("valid_first", "SVX", "IST", "2026-07-19T06:00:00+05:00", "2026-07-19T07:00:00+03:00", 1000, "U6773"),
                ],
            },
            {
                "direction": "outbound",
                "leg": "hub_to_destination",
                "query": {"origin": "IST", "destination": "LHR", "date": "2026-07-19", "currency": "RUB"},
                "offers": [
                    offer("invalid_second", "IST", "LHR", "2026-07-19T08:00:00+03:00", "2026-07-19T10:00:00+01:00", 100, "TK1979"),
                    offer("valid_second", "IST", "LHR", "2026-07-19T16:30:00+03:00", "2026-07-19T18:30:00+01:00", 1000, "TK1987"),
                ],
            },
        ]

        assembled = self._assemble(
            {"segment_results": segment_results},
            "--max-candidates",
            "1",
            "--include-candidates",
            "0",
            "--include-ranked-candidates",
            "1",
        )
        self.assertEqual(assembled["data"]["count"], 1)
        self.assertEqual(assembled["data"]["assembly"]["candidate_count"], 4)
        self.assertGreater(assembled["data"]["assembly"]["ranked_total_count"], 1)
        self.assertTrue(assembled["data"]["ranked"][0]["ok"])
        ranked_candidate = assembled["data"]["ranked_candidates"][0]["candidate"]
        self.assertNotIn(
            "TK1979",
            [segment["flight_number"] for journey in ranked_candidate["journeys"] for segment in journey["segments"]],
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
                "fetched": {"data": payload},
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


if __name__ == "__main__":
    unittest.main()
