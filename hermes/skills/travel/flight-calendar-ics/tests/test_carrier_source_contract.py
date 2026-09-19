"""Carrier adapters own source credentials and source-shape validation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class CarrierSourceContractTests(unittest.TestCase):
    def test_adapters_accept_their_supported_aliases_and_fragments(self) -> None:
        from flight_calendar.carriers import redwings, s7, ural, utair

        cases = (
            (
                ural.parse_ural_source,
                "https://service.uralairlines.ru/?pnrNumber=abc123&surname=ivanov",
                ("ABC123", "IVANOV"),
            ),
            (
                utair.parse_utair_source,
                "https://www.utair.ru/order-manage?pnr=abc123&lastName=ivanov",
                ("ABC123", "IVANOV"),
            ),
            (
                redwings.parse_redwings_source,
                "https://flyredwings.com/booking/#/find/abc123/ACCESS_KEY/Submit",
                ("ABC123", "ACCESS_KEY"),
            ),
            (
                s7.parse_s7_source,
                "https://myb.s7.ru/myb/manage-order?booking_id=abc123&passenger_id=ivanov",
                ("ABC123", "ivanov"),
            ),
        )
        for parse_source, url, expected in cases:
            with self.subTest(url=url):
                locator, passenger, normalized_url = parse_source(url)
                self.assertEqual((locator, passenger), expected)
                self.assertEqual(normalized_url, url)

    def test_adapters_report_missing_source_credentials(self) -> None:
        from flight_calendar.carriers import redwings, s7, ural, utair
        from flight_calendar.errors import CliFailure

        cases = (
            (ural.parse_ural_source, "https://service.uralairlines.ru/"),
            (utair.parse_utair_source, "https://www.utair.ru/order-manage"),
            (redwings.parse_redwings_source, "https://flyredwings.com/booking/"),
            (s7.parse_s7_source, "https://myb.s7.ru/myb/manage-order"),
        )
        for parse_source, url in cases:
            with self.subTest(url=url):
                with self.assertRaises(CliFailure) as ctx:
                    parse_source(url)
                self.assertEqual(ctx.exception.code, "route_input_insufficient")

    def test_adapters_reject_present_invalid_source_values(self) -> None:
        from flight_calendar.carriers import redwings, s7, ural, utair

        cases = (
            (ural.parse_ural_source, "https://service.uralairlines.ru/?pnr=BAD&lastName=IVANOV"),
            (utair.parse_utair_source, "https://www.utair.ru/order-manage?rloc=BAD&last_name=IVANOV"),
            (redwings.parse_redwings_source, "https://flyredwings.com/booking/#/find/BAD/X/Submit"),
            (s7.parse_s7_source, "https://myb.s7.ru/myb/manage-order?bookingId=BAD&passengerId=ivanov"),
        )
        for parse_source, url in cases:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    parse_source(url)


if __name__ == "__main__":
    unittest.main()