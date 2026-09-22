#!/usr/bin/env python3
"""Executable specification for the Ural Reservation raw-response boundary.

This specification deliberately targets the carrier boundary, not the complete
undocumented Ural schema.  It is expected to expose RED cases until production
adds one validation owner between HTTP JSON and ``convert_to_itinerary``.

Target responsibility is explicit: HTTP JSON -> Ural response validation ->
converter -> canonical itinerary validation.  This file does not duplicate
canonical airport, datetime, timezone, or itinerary-semantic rules.

Run from the skill root with ``python3 specs/ural_raw_contract_spec.py``.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "specs" / "fixtures" / "ural" / "reservation.json"
sys.path.insert(0, str(SCRIPTS))

BOOKING_URL = "https://service.uralairlines.ru/?pnr=ABC123&lastName=IVANOV"
SYNTHETIC_API = "https://ural-api.test/api/"


def fixture_response() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class UralRawReservationContractSpecification(unittest.TestCase):
    maxDiff = None

    def _build(self, response: Any) -> dict[str, Any]:
        from flight_calendar.carriers import ural

        config = ural.DeploymentConfig("12345", SYNTHETIC_API, "synthetic-api-key")
        with (
            mock.patch.object(ural, "load_deployment_config", return_value=config),
            mock.patch.object(ural, "compute_timestamp_diff", return_value=0),
            mock.patch.object(ural, "generate_api_key_header", return_value="synthetic"),
            mock.patch.object(ural, "http_json", return_value=response),
        ):
            return ural.build_itinerary(BOOKING_URL)

    def _assert_rejected_before_converter(
        self,
        response: Any,
        *,
        forbidden_text: str | None = None,
    ) -> None:
        from flight_calendar.carriers import ural

        converter_calls: list[Any] = []
        real_converter = ural.convert_to_itinerary

        def observe_converter(data: dict[str, Any], booking_url: str | None = None) -> dict[str, Any]:
            converter_calls.append(data)
            return real_converter(data, booking_url=booking_url)

        with mock.patch.object(ural, "convert_to_itinerary", side_effect=observe_converter):
            with self.assertRaises(ValueError) as context:
                self._build(response)

        self.assertEqual(
            len(converter_calls),
            0,
            "raw response must be rejected before conversion",
        )
        if forbidden_text is not None:
            self.assertNotIn(forbidden_text, str(context.exception))

    def test_checked_in_fixture_is_valid_and_converts_to_expected_itinerary(self) -> None:
        response = fixture_response()
        itinerary = self._build(response)

        self.assertEqual(
            itinerary["flights"],
            [
                {
                    "flight_number": "U6 273",
                    "departure": {"airport": "DME", "local": "2026-09-21T08:25"},
                    "arrival": {"airport": "SVX", "local": "2026-09-21T12:55"},
                    "aircraft": "Airbus A320",
                },
                {
                    "flight_number": "U6 270",
                    "departure": {"airport": "SVX", "local": "2026-09-24T20:30"},
                    "arrival": {"airport": "DME", "local": "2026-09-24T21:00"},
                    "aircraft": "Airbus A321",
                },
            ],
        )
        self.assertEqual(itinerary["pnr"], "ABC123")
        self.assertEqual(itinerary["passenger"], "SANITIZED PASSENGER")
        self.assertEqual(itinerary["ticket_number"], "0000000000000")

    def test_optional_reservation_details_are_not_required(self) -> None:
        response = fixture_response()
        data = response["data"]
        for key in ("number", "passengers", "tickets"):
            data.pop(key)
        for group in ("outboundFlights", "returnFlights"):
            for segment in data["journey"][group]:
                segment.pop("aircraft")
                segment.pop("operatingCarrier")
        itinerary = self._build(response)

        self.assertEqual(len(itinerary["flights"]), 2)
        self.assertNotIn("pnr", itinerary)
        self.assertNotIn("passenger", itinerary)
        self.assertNotIn("ticket_number", itinerary)
        self.assertNotIn("aircraft", itinerary["flights"][0])

    def test_non_object_json_is_a_controlled_carrier_failure(self) -> None:
        self._assert_rejected_before_converter([])

    def test_success_false_is_business_failure_before_converter_and_private_errors_stay_private(self) -> None:
        response = fixture_response()
        response["success"] = False
        response["errors"] = [{"message": "PRIVATE CARRIER DETAIL"}]
        self._assert_rejected_before_converter(
            response,
            forbidden_text="PRIVATE CARRIER DETAIL",
        )

    def test_missing_success_is_not_an_accepted_reservation(self) -> None:
        response = fixture_response()
        response.pop("success")
        self._assert_rejected_before_converter(response)

    def test_missing_data_is_not_passed_to_converter(self) -> None:
        response = fixture_response()
        response.pop("data")
        self._assert_rejected_before_converter(response)

    def test_malformed_data_is_a_controlled_carrier_failure(self) -> None:
        response = fixture_response()
        response["data"] = []
        self._assert_rejected_before_converter(response)

    def test_missing_or_wrong_type_journey_is_a_controlled_carrier_failure(self) -> None:
        for journey in (None, "not-an-object"):
            with self.subTest(journey=journey):
                response = fixture_response()
                response["data"]["journey"] = journey
                self._assert_rejected_before_converter(response)

    def test_journey_without_usable_flight_segments_is_a_controlled_failure(self) -> None:
        response = fixture_response()
        response["data"]["journey"] = {
            "outboundFlights": [],
            "returnFlights": [],
            "separateFlights": [],
        }
        self._assert_rejected_before_converter(response)

    def test_journey_group_with_wrong_type_is_a_controlled_failure(self) -> None:
        response = fixture_response()
        response["data"]["journey"]["outboundFlights"] = {}
        self._assert_rejected_before_converter(response)

    def test_each_usable_segment_field_is_required_at_raw_boundary(self) -> None:
        required_fields = (
            "origin",
            "destination",
            "departureDate",
            "arrivalDate",
            "flightNumber",
        )
        for field in required_fields:
            with self.subTest(field=field):
                response = fixture_response()
                response["data"]["journey"]["outboundFlights"][0].pop(field)
                self._assert_rejected_before_converter(response)

        response = fixture_response()
        segment = response["data"]["journey"]["outboundFlights"][0]
        segment.pop("marketingCarrier")
        segment.pop("operatingCarrier")
        self._assert_rejected_before_converter(response)

    def test_malformed_nested_passenger_ticket_and_segment_are_controlled(self) -> None:
        cases: list[tuple[str, dict[str, Any]]] = []

        response = fixture_response()
        response["data"]["passengers"] = [None]
        cases.append(("passenger element", response))

        response = fixture_response()
        response["data"]["tickets"] = [None]
        cases.append(("ticket element", response))

        response = fixture_response()
        response["data"]["journey"]["outboundFlights"] = [None]
        cases.append(("segment element", response))

        for label, malformed in cases:
            with self.subTest(case=label):
                self._assert_rejected_before_converter(malformed)


if __name__ == "__main__":
    unittest.main()
