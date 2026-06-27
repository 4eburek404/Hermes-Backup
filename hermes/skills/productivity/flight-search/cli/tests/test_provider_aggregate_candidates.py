from __future__ import annotations

import unittest

from flights_cli.adapters.providers.kupibilet_adapter import (
    aggregate_offer_summary,
    kupibilet_aggregate_control_summary,
)
from flights_cli.services.agent_report import build_agent_report
from flights_cli.services.agent_report_contract import validate_agent_report


def aggregate_offer() -> dict:
    return {
        "id": "agg-su-del",
        "price": 42000,
        "currency": "RUB",
        "change_count": 1,
        "duration_min": 520,
        "flight_numbers": ["SU1419", "SU232"],
        "carriers": ["SU"],
        "segments": [
            {
                "flight_number": "SU1419",
                "carrier": "SU",
                "marketing_carrier": "SU",
                "operating_carrier": "SU",
                "origin": "SVX",
                "destination": "SVO",
                "departure_at": "2026-06-01T06:00:00+05:00",
                "arrival_at": "2026-06-01T06:40:00+03:00",
            },
            {
                "flight_number": "SU232",
                "carrier": "SU",
                "marketing_carrier": "SU",
                "operating_carrier": "SU",
                "origin": "SVO",
                "destination": "DEL",
                "departure_at": "2026-06-01T10:30:00+03:00",
                "arrival_at": "2026-06-01T18:50:00+05:30",
            },
        ],
        "ticketing_note": "Provider-assembled route offer; verify single-PNR/protection, baggage, and final fare on the booking screen.",
    }


def assembled_round_trip_detail() -> dict:
    return {
        "category": "assembled_round_trip_control",
        "reason": "ordinary assembled round-trip option for the requested trip",
        "detail_status": "full",
        "ranked": {
            "rank": 1,
            "id": "assembled-round-trip:SVX-DEL",
            "ok": True,
            "price": 90000,
            "currency": "RUB",
            "elapsed_min": 1200,
            "carriers": ["SU"],
            "risk": {"score": 1, "grade": "good", "reject": False, "top_reasons": []},
            "validation_summary": {
                "stop_tier": "T0_DIRECT",
                "max_connections_per_journey": 0,
            },
            "connections": [],
        },
        "candidate": {
            "id": "assembled-round-trip:SVX-DEL",
            "journeys": [
                {
                    "direction": "outbound",
                    "segments": [
                        {
                            "flight_number": "SU100",
                            "carrier": "SU",
                            "marketing_carrier": "SU",
                            "operating_carrier": "SU",
                            "origin": "SVX",
                            "destination": "DEL",
                            "departure_at": "2026-07-19T06:00:00+05:00",
                            "arrival_at": "2026-07-19T12:00:00+05:30",
                        }
                    ],
                },
                {
                    "direction": "return",
                    "segments": [
                        {
                            "flight_number": "SU101",
                            "carrier": "SU",
                            "marketing_carrier": "SU",
                            "operating_carrier": "SU",
                            "origin": "DEL",
                            "destination": "SVX",
                            "departure_at": "2026-07-24T09:00:00+05:30",
                            "arrival_at": "2026-07-24T16:00:00+05:00",
                        }
                    ],
                },
            ],
        },
    }


def return_aggregate_offer(*, price: int = 43000, currency: str = "RUB") -> dict:
    return {
        **aggregate_offer(),
        "id": "agg-return",
        "price": price,
        "currency": currency,
        "segments": [
            {
                "flight_number": "SU233",
                "carrier": "SU",
                "marketing_carrier": "SU",
                "operating_carrier": "SU",
                "origin": "DEL",
                "destination": "SVO",
                "departure_at": "2026-07-24T08:00:00+05:30",
                "arrival_at": "2026-07-24T12:30:00+03:00",
            },
            {
                "flight_number": "SU1418",
                "carrier": "SU",
                "marketing_carrier": "SU",
                "operating_carrier": "SU",
                "origin": "SVO",
                "destination": "SVX",
                "departure_at": "2026-07-24T15:30:00+03:00",
                "arrival_at": "2026-07-24T20:00:00+05:00",
            },
        ],
    }


def add_return_aggregate_control(payload: dict, offer: dict | None = None) -> None:
    payload["live_search"]["aggregate_controls"].append(
        {
            "direction": "return",
            "origin": "DEL",
            "destination": "SVX",
            "date": "2026-07-24",
            "status": "ok",
            "provider": "kupibilet",
            "filters": {"direct_only": False},
            "offer_count": 1,
            "raw_variant_count": 1,
            "top_offers": [offer or return_aggregate_offer()],
            "error": None,
        }
    )


def report_payload() -> dict:
    return {
        "profile": "business",
        "assembly": {
            "ranked_output_count": 0,
            "ranked_total_count": 0,
            "candidate_count": 0,
            "candidate_pool_truncated": False,
        },
        "ranked_candidates": [],
        "frontier_candidates": [],
        "rejected_pairs": [],
        "live_search": {
            "provider_policy": "kupibilet",
            "plan": {
                "origin": "SVX",
                "destination": "DEL",
                "origin_airports": ["SVX"],
                "destination_airports": ["DEL"],
                "dates": {"depart": "2026-06-01", "return": None},
                "routing_strategy": "ru-priority",
                "coverage_mode": "targeted",
                "coverage_controls": [
                    {
                        "type": "full_route_aggregate",
                        "direction": "outbound",
                        "origin": "SVX",
                        "destination": "DEL",
                        "date": "2026-06-01",
                    }
                ],
            },
            "hub_viability": [],
            "segment_searches": [],
            "aggregate_controls": [
                {
                    "direction": "outbound",
                    "origin": "SVX",
                    "destination": "DEL",
                    "date": "2026-06-01",
                    "status": "ok",
                    "provider": "kupibilet",
                    "filters": {"direct_only": False, "only_carriers": ["SU"]},
                    "offer_count": 1,
                    "raw_variant_count": 1,
                    "top_offers": [aggregate_offer()],
                    "error": None,
                }
            ],
            "failure_count": 0,
            "failures": [],
        },
    }


class ProviderAggregateCandidateTests(unittest.TestCase):
    def test_provider_aggregate_offer_is_labeled_candidate_not_protected_fare(
        self,
    ) -> None:
        report = build_agent_report(report_payload())
        validate_agent_report(report)

        aggregate = next(
            item
            for item in report["frontier"]["priority_options"]
            if item.get("category") == "provider_aggregate_candidate"
        )
        self.assertEqual(aggregate["id"], "provider-aggregate:outbound:agg-su-del")
        self.assertEqual(aggregate["detail_status"], "full")
        self.assertEqual(aggregate["price"], {"amount": 42000, "currency": "RUB"})
        self.assertEqual(
            [segment["flight_number"] for segment in aggregate["segments"]],
            ["SU1419", "SU232"],
        )
        self.assertEqual(aggregate["journey_scope"], "one_way")
        self.assertEqual(aggregate["direction"], "outbound")
        self.assertTrue(aggregate["covers_requested_trip"])
        self.assertTrue(aggregate["directional_only"])
        self.assertFalse(aggregate["composed_of_directional_offers"])
        self.assertEqual(aggregate["ticketing_model"], "provider_aggregate")

    def test_offer_graph_frontier_includes_provider_aggregate_candidate(self) -> None:
        report = build_agent_report(report_payload())
        validate_agent_report(report)

        graph = report["frontier"]["offer_graph"]
        frontier_by_id = {item["option_id"]: item for item in graph["frontier"]}

        self.assertIn("provider-aggregate:outbound:agg-su-del", frontier_by_id)
        aggregate_frontier = frontier_by_id["provider-aggregate:outbound:agg-su-del"]
        self.assertEqual(aggregate_frontier["source"], "priority_options")
        self.assertEqual(aggregate_frontier["role"], "provider_aggregate_candidate")
        self.assertEqual(
            aggregate_frontier["evidence_status"],
            "provider_aggregate_unverified_ticketing",
        )
        self.assertEqual(graph["collection"]["mode"], "progressive")
        self.assertEqual(
            graph["truth_language"]["inventory_scope"],
            "live_provider_returned_inventory",
        )

    def test_offer_graph_surfaces_not_supported_as_capability_boundary_not_missing_evidence(
        self,
    ) -> None:
        payload = report_payload()
        payload["live_search"]["probe_ledger"] = {
            "coverage_mode": "targeted",
            "negative_evidence_type": "bounded_live_controls_only",
            "planned_controls": [
                {
                    "type": "full_route_aggregate",
                    "direction": "outbound",
                    "origin": "SVX",
                    "destination": "DEL",
                    "date": "2026-06-01",
                    "probe_id": "agg-probe-001",
                }
            ],
            "searched_controls": [],
            "skipped_controls": [],
            "failed_controls": [],
            "not_supported_controls": [
                {
                    "type": "full_route_aggregate",
                    "direction": "outbound",
                    "origin": "SVX",
                    "destination": "DEL",
                    "date": "2026-06-01",
                    "provider": "kupibilet",
                    "reason": "provider_capability_not_supported",
                    "execution_state": "not_supported",
                    "status": "not_supported",
                    "probe_id": "agg-probe-001",
                }
            ],
            "not_executed_controls": [],
            "deduped_controls": [],
            "completeness": {
                "planned_count": 1,
                "terminal_count": 1,
                "all_planned_controls_have_terminal_state": True,
            },
        }

        report = build_agent_report(payload)
        validate_agent_report(report)

        graph = report["frontier"]["offer_graph"]
        self.assertEqual(graph["evidence"]["not_supported_control_count"], 1)
        self.assertEqual(graph["evidence"]["missing_evidence_count"], 0)
        self.assertEqual(graph["missing_evidence"], [])
        self.assertEqual(
            graph["capability_boundaries"][0]["reason"],
            "provider_capability_not_supported",
        )
        self.assertEqual(
            graph["collection"]["stop_reason"], "bounded_terminal_controls"
        )

    def test_provider_aggregate_times_include_layover_from_segment_timestamps(
        self,
    ) -> None:
        payload = report_payload()
        payload["live_search"]["aggregate_controls"][0]["top_offers"] = [
            {
                **aggregate_offer(),
                "id": "with-layover",
                "duration_min": 300,
                "segments": [
                    {
                        "flight_number": "A1",
                        "carrier": "A",
                        "origin": "SVX",
                        "destination": "IST",
                        "departure_at": "2026-07-19T10:00:00",
                        "arrival_at": "2026-07-19T12:00:00",
                    },
                    {
                        "flight_number": "A2",
                        "carrier": "A",
                        "origin": "IST",
                        "destination": "LON",
                        "departure_at": "2026-07-19T18:00:00",
                        "arrival_at": "2026-07-19T21:00:00",
                    },
                ],
            }
        ]

        report = build_agent_report(payload)
        validate_agent_report(report)

        aggregate = next(
            item
            for item in report["frontier"]["priority_options"]
            if item.get("id") == "provider-aggregate:outbound:with-layover"
        )
        self.assertEqual(aggregate["flight_time_min"], 300)
        self.assertEqual(aggregate["layover_total_min"], 360)
        self.assertEqual(aggregate["itinerary_elapsed_min"], 660)
        self.assertIsNone(aggregate["elapsed"])
        self.assertNotIn("duration", aggregate["user_facing_label"].lower())
        self.assertNotIn("elapsed", aggregate["user_facing_label"].lower())

    def test_provider_aggregate_times_handle_overnight_layover(self) -> None:
        payload = report_payload()
        payload["live_search"]["aggregate_controls"][0]["top_offers"] = [
            {
                **aggregate_offer(),
                "id": "overnight-layover",
                "duration_min": 360,
                "segments": [
                    {
                        "flight_number": "A1",
                        "carrier": "A",
                        "origin": "SVX",
                        "destination": "IST",
                        "departure_at": "2026-07-19T22:00:00",
                        "arrival_at": "2026-07-20T01:00:00",
                    },
                    {
                        "flight_number": "A2",
                        "carrier": "A",
                        "origin": "IST",
                        "destination": "LON",
                        "departure_at": "2026-07-20T10:00:00",
                        "arrival_at": "2026-07-20T13:00:00",
                    },
                ],
            }
        ]

        report = build_agent_report(payload)
        validate_agent_report(report)

        aggregate = next(
            item
            for item in report["frontier"]["priority_options"]
            if item.get("id") == "provider-aggregate:outbound:overnight-layover"
        )
        self.assertEqual(aggregate["flight_time_min"], 360)
        self.assertEqual(aggregate["layover_total_min"], 540)
        self.assertEqual(aggregate["itinerary_elapsed_min"], 900)
        self.assertNotIn("duration", aggregate["user_facing_label"].lower())

    def test_provider_aggregate_missing_timestamps_falls_back_to_flight_time_only(
        self,
    ) -> None:
        payload = report_payload()
        payload["live_search"]["aggregate_controls"][0]["top_offers"] = [
            {
                **aggregate_offer(),
                "id": "flight-time-only",
                "duration_min": 545,
                "segments": [
                    {
                        "flight_number": "A1",
                        "carrier": "A",
                        "origin": "SVX",
                        "destination": "IST",
                    },
                    {
                        "flight_number": "A2",
                        "carrier": "A",
                        "origin": "IST",
                        "destination": "LON",
                    },
                ],
            }
        ]

        report = build_agent_report(payload)
        validate_agent_report(report)

        aggregate = next(
            item
            for item in report["frontier"]["priority_options"]
            if item.get("id") == "provider-aggregate:outbound:flight-time-only"
        )
        self.assertEqual(aggregate["flight_time_min"], 545)
        self.assertIsNone(aggregate["itinerary_elapsed_min"])
        self.assertIsNone(aggregate["layover_total_min"])
        for forbidden in (
            "Travel time",
            "duration",
            "elapsed",
            "total time",
            "nonstop",
            "direct",
        ):
            self.assertNotIn(forbidden.lower(), aggregate["user_facing_label"].lower())

    def test_provider_aggregate_single_segment_time_has_zero_layover_without_noise(
        self,
    ) -> None:
        payload = report_payload()
        payload["live_search"]["aggregate_controls"][0]["top_offers"] = [
            {
                **aggregate_offer(),
                "id": "single-segment",
                "duration_min": 240,
                "change_count": 0,
                "segments": [
                    {
                        "flight_number": "A1",
                        "carrier": "A",
                        "origin": "SVX",
                        "destination": "LON",
                        "departure_at": "2026-07-19T10:00:00",
                        "arrival_at": "2026-07-19T14:00:00",
                    },
                ],
            }
        ]

        report = build_agent_report(payload)
        validate_agent_report(report)

        aggregate = next(
            item
            for item in report["frontier"]["priority_options"]
            if item.get("id") == "provider-aggregate:outbound:single-segment"
        )
        self.assertEqual(aggregate["flight_time_min"], 240)
        self.assertEqual(aggregate["layover_total_min"], 0)
        self.assertEqual(aggregate["itinerary_elapsed_min"], 240)

    def test_round_trip_provider_aggregate_controls_are_marked_directional_only(
        self,
    ) -> None:
        payload = report_payload()
        payload["live_search"]["plan"]["dates"] = {
            "depart": "2026-07-19",
            "return": "2026-07-24",
        }
        return_offer = {
            **aggregate_offer(),
            "id": "agg-return",
            "segments": [
                {
                    "flight_number": "SU233",
                    "carrier": "SU",
                    "marketing_carrier": "SU",
                    "operating_carrier": "SU",
                    "origin": "DEL",
                    "destination": "SVO",
                    "departure_at": "2026-07-24T08:00:00+05:30",
                    "arrival_at": "2026-07-24T12:30:00+03:00",
                },
                {
                    "flight_number": "SU1418",
                    "carrier": "SU",
                    "marketing_carrier": "SU",
                    "operating_carrier": "SU",
                    "origin": "SVO",
                    "destination": "SVX",
                    "departure_at": "2026-07-24T15:30:00+03:00",
                    "arrival_at": "2026-07-24T20:00:00+05:00",
                },
            ],
        }
        payload["live_search"]["aggregate_controls"].append(
            {
                "direction": "return",
                "origin": "DEL",
                "destination": "SVX",
                "date": "2026-07-24",
                "status": "ok",
                "provider": "kupibilet",
                "filters": {"direct_only": False},
                "offer_count": 1,
                "raw_variant_count": 1,
                "top_offers": [return_offer],
                "error": None,
            }
        )

        report = build_agent_report(payload)
        validate_agent_report(report)

        aggregates = {
            item["direction"]: item
            for item in report["frontier"]["priority_options"]
            if item.get("category") == "provider_aggregate_candidate"
        }
        outbound = aggregates["outbound"]
        inbound = aggregates["return"]
        self.assertEqual(outbound["journey_scope"], "outbound_only")
        self.assertFalse(outbound["covers_requested_trip"])
        self.assertTrue(outbound["directional_only"])
        self.assertEqual(inbound["journey_scope"], "return_only")
        self.assertFalse(inbound["covers_requested_trip"])
        self.assertTrue(inbound["directional_only"])

    def test_round_trip_directional_aggregate_controls_create_one_two_one_way_pair(
        self,
    ) -> None:
        payload = report_payload()
        payload["ranked_candidates"] = [assembled_round_trip_detail()]
        payload["live_search"]["plan"]["dates"] = {
            "depart": "2026-07-19",
            "return": "2026-07-24",
        }
        payload["live_search"]["aggregate_controls"][0]["top_offers"] = [
            {
                **aggregate_offer(),
                "id": "agg-outbound",
                "price": 21000,
                "currency": "RUB",
            }
        ]
        add_return_aggregate_control(
            payload, return_aggregate_offer(price=43000, currency="RUB")
        )

        report = build_agent_report(payload)
        validate_agent_report(report)

        self.assertEqual(
            report["frontier"]["recommended_options"][0]["id"],
            "assembled-round-trip:SVX-DEL",
        )
        provider_options = [
            item
            for item in report["frontier"]["priority_options"]
            if item.get("category") == "provider_aggregate_candidate"
        ]
        outbound = next(
            item for item in provider_options if item.get("direction") == "outbound"
        )
        inbound = next(
            item for item in provider_options if item.get("direction") == "return"
        )
        pairs = [
            item
            for item in provider_options
            if item.get("journey_scope") == "two_one_way_pair"
        ]
        self.assertEqual(len(pairs), 1)
        pair = pairs[0]

        self.assertEqual(outbound["journey_scope"], "outbound_only")
        self.assertFalse(outbound["covers_requested_trip"])
        self.assertEqual(inbound["journey_scope"], "return_only")
        self.assertFalse(inbound["covers_requested_trip"])
        self.assertEqual(pair["journey_scope"], "two_one_way_pair")
        self.assertTrue(pair["covers_requested_trip"])
        self.assertIsNone(pair["direction"])
        self.assertFalse(pair["directional_only"])
        self.assertTrue(pair["composed_of_directional_offers"])
        self.assertEqual(pair["ticketing_model"], "separate_one_way_offers")
        self.assertEqual(pair["price"], {"amount": 64000, "currency": "RUB"})
        self.assertNotIn("itinerary_elapsed_min", pair)
        self.assertNotIn("flight_time_min", pair)
        self.assertNotIn("layover_total_min", pair)
        self.assertEqual(
            pair["outbound_time"],
            {
                "itinerary_elapsed_min": 740,
                "flight_time_min": 510,
                "layover_total_min": 230,
            },
        )
        self.assertEqual(
            pair["return_time"],
            {
                "itinerary_elapsed_min": 750,
                "flight_time_min": 570,
                "layover_total_min": 180,
            },
        )
        self.assertNotIn("total journey time", pair["user_facing_label"].lower())
        combined = f"{pair['user_facing_label']} {pair['price_text']}".lower()
        self.assertNotIn("total fare", combined)
        self.assertNotIn("round-trip fare", combined)
        self.assertNotIn("final price", combined)

    def test_two_one_way_pair_does_not_sum_different_currencies(self) -> None:
        payload = report_payload()
        payload["live_search"]["plan"]["dates"] = {
            "depart": "2026-07-19",
            "return": "2026-07-24",
        }
        payload["live_search"]["aggregate_controls"][0]["top_offers"] = [
            {
                **aggregate_offer(),
                "id": "agg-outbound",
                "price": 21000,
                "currency": "RUB",
            }
        ]
        add_return_aggregate_control(
            payload, return_aggregate_offer(price=430, currency="EUR")
        )

        report = build_agent_report(payload)
        validate_agent_report(report)

        pair = next(
            item
            for item in report["frontier"]["priority_options"]
            if item.get("journey_scope") == "two_one_way_pair"
        )
        self.assertEqual(pair["price"], {"amount": None, "currency": None})
        combined = f"{pair['user_facing_label']} {pair['price_text']}".lower()
        self.assertNotIn("sum of displayed one-way prices", combined)
        self.assertNotIn("total fare", combined)
        self.assertNotIn("round-trip fare", combined)

    def test_provider_aggregate_frontier_prefers_fewer_stops_over_cheapest_garbage(
        self,
    ) -> None:
        payload = report_payload()
        cheap_garbage = {
            **aggregate_offer(),
            "id": "cheap-garbage",
            "price": 10000,
            "change_count": 3,
            "flight_numbers": ["A1", "B2", "C3", "D4"],
            "segments": [
                {"origin": "SVX", "destination": "A", "flight_number": "A1"},
                {"origin": "A", "destination": "B", "flight_number": "B2"},
                {"origin": "B", "destination": "C", "flight_number": "C3"},
                {"origin": "C", "destination": "DEL", "flight_number": "D4"},
            ],
        }
        frontier = {
            **aggregate_offer(),
            "id": "frontier",
            "price": 42000,
            "change_count": 1,
        }
        payload["live_search"]["aggregate_controls"][0]["top_offers"] = [
            cheap_garbage,
            frontier,
        ]

        report = build_agent_report(payload)

        self.assertEqual(
            report["evidence"]["aggregate_controls"][0]["top_offers"][0]["id"],
            "frontier",
        )
        self.assertEqual(
            report["frontier"]["priority_options"][0]["id"],
            "provider-aggregate:outbound:frontier",
        )

    def test_provider_aggregate_frontier_prefers_shorter_duration_before_price(
        self,
    ) -> None:
        payload = report_payload()
        slow_cheap = {
            **aggregate_offer(),
            "id": "slow-cheap",
            "price": 26000,
            "change_count": 1,
            "duration": 1040,
        }
        short_expensive = {
            **aggregate_offer(),
            "id": "short-expensive",
            "price": 42000,
            "change_count": 1,
            "duration": 520,
        }
        payload["live_search"]["aggregate_controls"][0]["top_offers"] = [
            slow_cheap,
            short_expensive,
        ]

        report = build_agent_report(payload)

        self.assertEqual(
            report["evidence"]["aggregate_controls"][0]["top_offers"][0]["id"],
            "short-expensive",
        )
        self.assertEqual(
            report["frontier"]["priority_options"][0]["id"],
            "provider-aggregate:outbound:short-expensive",
        )

    def test_provider_aggregate_execution_cuts_three_stop_before_model_payload(
        self,
    ) -> None:
        one_stop = {
            "id": "one-stop",
            "price": 42000,
            "currency": "RUB",
            "number_of_changes": 1,
            "duration": 520,
            "segments": [
                {"origin": "SVX", "destination": "SVO", "flight_number": "SU1419"},
                {"origin": "SVO", "destination": "DEL", "flight_number": "SU232"},
            ],
        }
        three_stop = {
            "id": "three-stop",
            "price": 10000,
            "currency": "RUB",
            "number_of_changes": 3,
            "duration": 1220,
            "segments": [
                {"origin": "SVX", "destination": "A", "flight_number": "A1"},
                {"origin": "A", "destination": "B", "flight_number": "B2"},
                {"origin": "B", "destination": "C", "flight_number": "C3"},
                {"origin": "C", "destination": "DEL", "flight_number": "D4"},
            ],
        }
        airport_change = {
            "id": "airport-change",
            "price": 12000,
            "currency": "RUB",
            "number_of_changes": 1,
            "duration": 420,
            "segments": [
                {"origin": "SVX", "destination": "IST", "flight_number": "TK1"},
                {"origin": "SAW", "destination": "DEL", "flight_number": "TK2"},
            ],
        }

        summary = kupibilet_aggregate_control_summary(
            direction="outbound",
            origin="SVX",
            destination="DEL",
            depart_date="2026-06-01",
            carriers=[],
            result={
                "source": "test",
                "raw_variant_count": 3,
                "unique_flight_count": 3,
                "cache": {"hit": False},
                "offers": [three_stop, airport_change, one_stop],
            },
        )

        self.assertEqual(summary["offer_count"], 1)
        self.assertEqual(summary["raw_offer_count"], 3)
        self.assertEqual(summary["suppressed_three_plus_count"], 1)
        self.assertEqual(summary["suppressed_airport_change_count"], 1)
        self.assertEqual([offer["id"] for offer in summary["top_offers"]], ["one-stop"])
        self.assertTrue(
            all(int(offer["connection_count"]) <= 2 for offer in summary["top_offers"])
        )

    def test_provider_aggregate_report_keeps_only_suppressed_three_stop_count(
        self,
    ) -> None:
        payload = report_payload()
        control = payload["live_search"]["aggregate_controls"][0]
        control["offer_count"] = 1
        control["raw_offer_count"] = 2
        control["suppressed_three_plus_count"] = 1
        control["suppressed_airport_change_count"] = 0
        control["top_offers"] = [aggregate_offer()]

        report = build_agent_report(payload)
        validate_agent_report(report)

        self.assertEqual(
            report["evidence"]["aggregate_controls"][0]["suppressed_three_plus_count"],
            1,
        )
        self.assertEqual(
            report["evidence"]["stop_policy_diagnostics"][
                "three_plus_suppressed_count"
            ],
            1,
        )
        self.assertEqual(
            [
                offer["id"]
                for offer in report["evidence"]["aggregate_controls"][0]["top_offers"]
            ],
            ["agg-su-del"],
        )
        self.assertTrue(
            all(
                int(offer.get("connection_count") or 0) <= 2
                for control in report["evidence"]["aggregate_controls"]
                for offer in control.get("top_offers") or []
            )
        )

    def test_provider_aggregate_summary_flags_airport_mismatch(self) -> None:
        summary = aggregate_offer_summary(
            {
                "id": "mow-mismatch",
                "price": 25000,
                "currency": "RUB",
                "number_of_changes": 1,
                "flight_numbers": ["DP404", "SU2132"],
                "segments": [
                    {
                        "flight_number": "DP404",
                        "marketing_carrier": "DP",
                        "operating_carrier": "DP",
                        "origin": "SVX",
                        "destination": "VKO",
                    },
                    {
                        "flight_number": "SU2132",
                        "marketing_carrier": "SU",
                        "operating_carrier": "SU",
                        "origin": "SVO",
                        "destination": "IST",
                    },
                ],
            }
        )

        self.assertEqual(summary["airport_mismatch_count"], 1)
        self.assertEqual(summary["airport_mismatches"][0]["arrival_airport"], "VKO")
        self.assertEqual(summary["airport_mismatches"][0]["departure_airport"], "SVO")


if __name__ == "__main__":
    unittest.main()
