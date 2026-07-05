from __future__ import annotations

import unittest

from flights_cli.adapters.providers.kupibilet_adapter import (
    aggregate_offer_summary,
    kupibilet_aggregate_control_summary,
)
from flights_cli.reporting.provider_aggregate_options import (
    aggregate_control_summary,
    provider_aggregate_candidate_options,
)
from flights_cli.services.agent_report import build_agent_report
from flights_cli.services.agent_report_contract import validate_agent_report
from tests.fixtures.agent_reports import (
    add_return_aggregate_control,
    aggregate_offer,
    provider_report_payload,
    return_aggregate_offer,
)


class ProviderAggregateCandidateTests(unittest.TestCase):
    def candidate_options(
        self, payload: dict, *, requested_round_trip: bool = False
    ) -> list[dict]:
        controls = [
            aggregate_control_summary(item)
            for item in payload["live_search"]["aggregate_controls"]
        ]
        return provider_aggregate_candidate_options(
            controls,
            limit=5,
            preferred_available=False,
            requested_round_trip=requested_round_trip,
        )

    def catalog_item(self, report: dict, option_id: str) -> dict:
        return next(
            item
            for item in report["user_answer"]["catalog"]["items"]
            if item.get("option_id") == option_id
        )

    def test_provider_aggregate_offer_is_canonical_catalog_item(self) -> None:
        report = build_agent_report(provider_report_payload())
        validate_agent_report(report)

        aggregate = self.catalog_item(report, "provider-aggregate:outbound:agg-su-del")
        outbound = aggregate["directions"]["outbound"]
        self.assertEqual(aggregate["detail_status"], "full")
        self.assertEqual(
            aggregate["total_price"],
            {
                "amount": 42000,
                "currency": "RUB",
                "display": "42 000 ₽",
                "source": "provider_aggregate",
                "confidence": "medium",
            },
        )
        self.assertEqual(
            [segment["flight_number"] for segment in outbound["segments"]],
            ["SU1419", "SU232"],
        )
        self.assertEqual(aggregate["journey_scope"], "one_way")
        self.assertEqual(aggregate["ticketing_model"], "provider_aggregate")
        self.assertIn("provider_aggregate", aggregate["badges"])
        self.assertEqual(set(report["frontier"]), {"decision_frontier"})

    def test_provider_aggregate_times_include_layover_from_segment_timestamps(
        self,
    ) -> None:
        payload = provider_report_payload()
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

        aggregate = self.candidate_options(payload)[0]

        self.assertEqual(aggregate["flight_time_min"], 300)
        self.assertEqual(aggregate["layover_total_min"], 360)
        self.assertEqual(aggregate["itinerary_elapsed_min"], 660)
        self.assertIsNone(aggregate["elapsed"])

    def test_provider_aggregate_missing_timestamps_falls_back_to_flight_time_only(
        self,
    ) -> None:
        payload = provider_report_payload()
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

        aggregate = self.candidate_options(payload)[0]

        self.assertEqual(aggregate["flight_time_min"], 545)
        self.assertIsNone(aggregate["itinerary_elapsed_min"])
        self.assertIsNone(aggregate["layover_total_min"])

    def test_round_trip_directional_controls_create_one_two_one_way_pair(self) -> None:
        payload = provider_report_payload()
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

        provider_options = self.candidate_options(payload, requested_round_trip=True)
        outbound = next(
            item for item in provider_options if item.get("direction") == "outbound"
        )
        inbound = next(
            item for item in provider_options if item.get("direction") == "return"
        )
        pair = next(
            item
            for item in provider_options
            if item.get("journey_scope") == "two_one_way_pair"
        )

        self.assertEqual(outbound["journey_scope"], "outbound_only")
        self.assertEqual(inbound["journey_scope"], "return_only")
        self.assertEqual(pair["journey_scope"], "two_one_way_pair")
        self.assertTrue(pair["covers_requested_trip"])
        self.assertEqual(pair["ticketing_model"], "separate_one_way_offers")
        self.assertEqual(pair["price"], {"amount": 64000, "currency": "RUB"})
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

    def test_two_one_way_pair_does_not_sum_different_currencies(self) -> None:
        payload = provider_report_payload()
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

        pair = next(
            item
            for item in self.candidate_options(payload, requested_round_trip=True)
            if item.get("journey_scope") == "two_one_way_pair"
        )

        self.assertEqual(pair["price"], {"amount": None, "currency": None})

    def test_provider_aggregate_frontier_prefers_fewer_stops_over_cheapest_garbage(
        self,
    ) -> None:
        payload = provider_report_payload()
        cheap_garbage = {
            **aggregate_offer(),
            "id": "cheap-garbage",
            "price": 10000,
            "change_count": 3,
            "segments": [
                {"origin": "SVX", "destination": "A", "flight_number": "A1"},
                {"origin": "A", "destination": "B", "flight_number": "B2"},
                {"origin": "B", "destination": "C", "flight_number": "C3"},
                {"origin": "C", "destination": "DEL", "flight_number": "D4"},
            ],
        }
        frontier = {**aggregate_offer(), "id": "frontier", "price": 42000}
        payload["live_search"]["aggregate_controls"][0]["top_offers"] = [
            cheap_garbage,
            frontier,
        ]

        selected = self.candidate_options(payload)[0]

        self.assertEqual(selected["id"], "provider-aggregate:outbound:frontier")

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
