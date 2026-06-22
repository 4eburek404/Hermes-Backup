from __future__ import annotations

import unittest

from flights_cli.providers.fli_mcp import fli_result_to_segment_result
from flights_cli.providers.kupibilet import kupibilet_result_to_segment_result
from flights_cli.providers.segment_normalization import normalize_segment_flight


def provider_result(*, source: str, raw_count_key: str) -> dict:
    result = {
        "origin": "SVX",
        "destination": "IST",
        "depart_date": "2026-08-15",
        "currency": "RUB",
        "source": source,
        "source_url": "https://example.test/search",
        "unique_flight_count": 1,
        "offers": [
            {
                "id": "offer-1",
                "price": 12500,
                "currency": "RUB",
                "number_of_changes": 0,
                "duration": 180,
                "segments": [
                    {
                        "flight_number": "SU100",
                        "marketing_carrier": "SU",
                        "operating_carrier": "SU",
                "origin": "SVX",
                "destination": "IST",
                "departure_terminal": "A",
                "arrival_terminal": "I",
                "departure_at": "2026-08-15T08:00:00+05:00",
                "arrival_at": "2026-08-15T10:30:00+03:00",
                "aircraft": "320",
                        "duration": 180,
                    }
                ],
            }
        ],
    }
    result[raw_count_key] = 1
    return result


class ProviderSegmentNormalizationTests(unittest.TestCase):
    def test_normalize_segment_flight_shape(self) -> None:
        normalized = normalize_segment_flight(
            {
                "flight_number": "TK1987",
                "origin": "IST",
                "destination": "LHR",
                "departure_terminal": "C",
                "arrival_terminal": "2",
                "departure_at": "2026-08-15T10:20:00+03:00",
                "arrival_at": "2026-08-15T12:30:00+01:00",
            }
        )

        self.assertEqual(normalized["origin"], "IST")
        self.assertEqual(normalized["destination"], "LHR")
        self.assertEqual(normalized["departure_terminal"], "C")
        self.assertEqual(normalized["arrival_terminal"], "2")
        self.assertEqual(normalized["carrier"], "TK")
        self.assertEqual(normalized["flight_number"], "TK1987")

    def test_fli_and_kupibilet_segment_results_share_offer_shape(self) -> None:
        kupibilet = kupibilet_result_to_segment_result(
            provider_result(source="kupibilet", raw_count_key="raw_variant_count"),
            direction="outbound",
            leg="direct_outbound",
        )
        fli = fli_result_to_segment_result(
            provider_result(source="fli", raw_count_key="raw_count"),
            direction="outbound",
            leg="direct_outbound",
        )

        shared_offer_keys = {
            "id",
            "direction",
            "leg",
            "query_origin",
            "query_destination",
            "query_date",
            "origin",
            "destination",
            "departure_airport",
            "arrival_airport",
            "departure_at",
            "arrival_at",
            "price",
            "currency",
            "carrier",
            "main_airline",
            "changes",
            "duration_min",
            "source",
            "segments",
            "transfers",
            "internal_connection_count",
        }
        self.assertEqual(set(kupibilet["offers"][0]), shared_offer_keys)
        self.assertEqual(set(fli["offers"][0]), shared_offer_keys)
        self.assertEqual(kupibilet["offers"][0]["segments"][0].keys(), fli["offers"][0]["segments"][0].keys())
        self.assertEqual(kupibilet["source_key"], "kupibilet_frontend_search")
        self.assertEqual(fli["source_key"], "fli_mcp_search_flights")
        self.assertEqual(kupibilet["offers"][0]["source"], "Kupibilet frontend_search direct-only")
        self.assertEqual(fli["offers"][0]["source"], "FLI MCP search_flights")


if __name__ == "__main__":
    unittest.main()
