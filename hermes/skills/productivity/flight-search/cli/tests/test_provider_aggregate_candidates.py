from __future__ import annotations

import unittest

from flights_cli.execution.aggregate_control_runner import aggregate_control_summary, aggregate_offer_summary
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
                    {"type": "full_route_aggregate", "direction": "outbound", "origin": "SVX", "destination": "DEL", "date": "2026-06-01"}
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
    def test_provider_aggregate_offer_is_labeled_candidate_not_protected_fare(self) -> None:
        report = build_agent_report(report_payload())
        validate_agent_report(report)

        aggregate = next(
            item for item in report["priority_options"] if item.get("category") == "provider_aggregate_candidate"
        )
        self.assertEqual(aggregate["id"], "provider-aggregate:outbound:agg-su-del")
        self.assertEqual(aggregate["detail_status"], "full")
        self.assertEqual(aggregate["price"], {"amount": 42000, "currency": "RUB"})
        self.assertEqual([segment["flight_number"] for segment in aggregate["segments"]], ["SU1419", "SU232"])
        self.assertIn("ticketing_protection=unknown", aggregate["ticketing_note"])
        self.assertIn("booking screen", aggregate["ticketing_note"])
        self.assertIn("Provider aggregate candidate", " ".join(report["answer_lines"]))

    def test_provider_aggregate_frontier_prefers_fewer_stops_over_cheapest_garbage(self) -> None:
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
        frontier = {**aggregate_offer(), "id": "frontier", "price": 42000, "change_count": 1}
        payload["live_search"]["aggregate_controls"][0]["top_offers"] = [cheap_garbage, frontier]

        report = build_agent_report(payload)

        self.assertEqual(report["aggregate_controls"][0]["top_offers"][0]["id"], "frontier")
        self.assertEqual(report["priority_options"][0]["id"], "provider-aggregate:outbound:frontier")

    def test_provider_aggregate_execution_cuts_three_stop_before_model_payload(self) -> None:
        one_stop = {
            "id": "one-stop",
            "price": 42000,
            "currency": "RUB",
            "number_of_changes": 1,
            "duration": 520,
            "flights": [
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
            "flights": [
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
            "flights": [
                {"origin": "SVX", "destination": "IST", "flight_number": "TK1"},
                {"origin": "SAW", "destination": "DEL", "flight_number": "TK2"},
            ],
        }

        summary = aggregate_control_summary(
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
        self.assertTrue(all(int(offer["connection_count"]) <= 2 for offer in summary["top_offers"]))

    def test_provider_aggregate_report_keeps_only_suppressed_three_stop_count(self) -> None:
        payload = report_payload()
        control = payload["live_search"]["aggregate_controls"][0]
        control["offer_count"] = 1
        control["raw_offer_count"] = 2
        control["suppressed_three_plus_count"] = 1
        control["suppressed_airport_change_count"] = 0
        control["top_offers"] = [aggregate_offer()]

        report = build_agent_report(payload)
        validate_agent_report(report)

        self.assertEqual(report["aggregate_controls"][0]["suppressed_three_plus_count"], 1)
        self.assertEqual(report["stop_policy_diagnostics"]["three_plus_suppressed_count"], 1)
        self.assertEqual([offer["id"] for offer in report["aggregate_controls"][0]["top_offers"]], ["agg-su-del"])
        self.assertTrue(
            all(
                int(offer.get("connection_count") or 0) <= 2
                for control in report["aggregate_controls"]
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
                "flights": [
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
