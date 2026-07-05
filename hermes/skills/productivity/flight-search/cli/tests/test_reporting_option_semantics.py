from __future__ import annotations

import unittest

from flights_cli.reporting.option_semantics import (
    direction_segments,
    option_direction,
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


if __name__ == "__main__":
    unittest.main()
