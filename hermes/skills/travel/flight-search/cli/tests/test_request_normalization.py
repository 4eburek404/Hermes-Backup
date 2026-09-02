from __future__ import annotations

import unittest

from flights_cli.errors import CliError
from flights_cli.pipeline.search_request import search_request_from_payload

from helpers import future_departure_date


class RequestNormalizationTests(unittest.TestCase):
    def test_version_is_optional_on_input_and_canonical_on_echo(self) -> None:
        """Вход без версии принимается; эхо всегда называет текущую.

        Раньше здесь проверялся переезд v3 к v4: версий входа было две, и
        одна нормализовалась в другую. С .v1 версия одна, нормализовать
        нечего — остаётся умолчание и канонический повтор.
        """
        depart = future_departure_date()
        request = search_request_from_payload(
            {
                "origin": "pus",
                "destination": "svx",
                "depart_date": depart.isoformat(),
            }
        )

        self.assertEqual(request.origin, "PUS")
        self.assertEqual(
            request.to_payload()["schema_version"], "flight_search_request.v1"
        )

    def test_superseded_input_versions_are_rejected(self) -> None:
        depart = future_departure_date()
        for version in ("flight_search_request.v3", "flight_search_request.v4"):
            with self.subTest(version=version), self.assertRaises(CliError):
                search_request_from_payload(
                    {
                        "schema_version": version,
                        "origin": "PUS",
                        "destination": "SVX",
                        "depart_date": depart.isoformat(),
                    }
                )


if __name__ == "__main__":
    unittest.main()
