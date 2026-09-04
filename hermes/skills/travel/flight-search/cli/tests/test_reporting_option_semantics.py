from __future__ import annotations

import unittest

from flights_cli.reporting.catalog_semantics import (
    direction_segments,
    option_direction,
    option_has_transfer,
    option_transfer_topology,
    route_requested_round_trip,
)


class ReportingOptionSemanticsTests(unittest.TestCase):
    def test_round_trip_detection_uses_route_dates(self) -> None:
        route = {"dates": {"depart": "2026-08-01", "return_date": "2026-08-08"}}

        self.assertTrue(route_requested_round_trip(route))
        self.assertFalse(
            route_requested_round_trip({"dates": {"depart": "2026-08-01"}})
        )

    def test_option_direction_uses_explicit_field_provider_aggregate_id_and_segment_fallback(
        self,
    ) -> None:
        self.assertEqual(option_direction({"direction": "return"}), "return")
        self.assertEqual(
            option_direction({"id": "provider-aggregate:outbound:1"}), "outbound"
        )
        self.assertEqual(
            option_direction(
                {"segments": [{"direction": "outbound"}, {"direction": "outbound"}]}
            ),
            "outbound",
        )
        self.assertIsNone(
            option_direction(
                {"segments": [{"direction": "outbound"}, {"direction": "return"}]}
            )
        )

    def test_direction_segments_filters_structured_segment_direction(self) -> None:
        option = {
            "segments": [
                {"direction": "outbound", "id": 1},
                {"direction": "return", "id": 2},
                "bad",
            ]
        }

        self.assertEqual(
            direction_segments(option, "outbound"), [{"direction": "outbound", "id": 1}]
        )

    def test_transfer_topology_counts_connections_per_direction(self) -> None:
        option = {
            "detail_status": "full",
            "segments": [
                {"direction": "outbound", "origin": "SVX", "destination": "SVO"},
                {"direction": "outbound", "origin": "SVO", "destination": "DEL"},
                {"direction": "return", "origin": "DEL", "destination": "SVX"},
            ],
        }

        topology = option_transfer_topology(option)

        self.assertTrue(topology["proven"])
        self.assertEqual(topology["max_connections"], 1)
        self.assertEqual(topology["journey_count"], 2)
        self.assertIs(option_has_transfer(topology), True)

    def test_non_stop_round_trip_proves_no_transfer(self) -> None:
        topology = option_transfer_topology(
            {
                "detail_status": "full",
                "segments": [
                    {"direction": "outbound", "origin": "SVX", "destination": "SVO"},
                    {"direction": "return", "origin": "SVO", "destination": "SVX"},
                ],
            }
        )

        self.assertEqual(topology["max_connections"], 0)
        self.assertEqual(topology["journey_count"], 2)
        self.assertIs(option_has_transfer(topology), False)

    def test_transfer_topology_is_unproven_without_visible_segments(self) -> None:
        for option in (
            {"detail_status": "full", "segments": []},
            {
                "detail_status": "summary_only",
                "segments": [{"direction": "outbound", "origin": "SVX"}],
            },
        ):
            with self.subTest(option=option):
                topology = option_transfer_topology(option)

                self.assertFalse(topology["proven"])
                self.assertIsNone(option_has_transfer(topology))


if __name__ == "__main__":
    unittest.main()
