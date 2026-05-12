from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from flights_cli.cli import build_parser
from flights_cli.errors import CliError
from flights_cli.providers.fli_mcp import (
    decode_mcp_response,
    fli_result_to_segment_result,
    parse_fli_flight_search,
    providers_for_segment,
    resolve_fli_airport,
)
from flights_cli.store import Store


def store_with_airports(test_case: unittest.TestCase) -> Store:
    tmp_dir = tempfile.TemporaryDirectory()
    test_case.addCleanup(tmp_dir.cleanup)
    cache = Path(tmp_dir.name)
    (cache / "airports_en.json").write_text(
        """
        [
          {"code": "IST", "country_code": "TR", "flightable": true, "name": "Istanbul New Airport", "name_translations": {"en": "Istanbul New Airport"}},
          {"code": "ISL", "country_code": "TR", "flightable": false, "name": "Istanbul Ataturk Airport", "name_translations": {"en": "Istanbul Ataturk Airport"}},
          {"code": "SAW", "country_code": "TR", "flightable": true, "name": "Sabiha Gokcen International Airport", "name_translations": {"en": "Sabiha Gokcen International Airport"}},
          {"code": "CDG", "country_code": "FR", "flightable": true, "name": "Charles de Gaulle Airport", "name_translations": {"en": "Charles de Gaulle Airport"}},
          {"code": "LHR", "country_code": "GB", "flightable": true, "name": "London Heathrow Airport", "name_translations": {"en": "London Heathrow Airport"}},
          {"code": "DXB", "country_code": "AE", "flightable": true, "name": "Dubai Airport", "name_translations": {"en": "Dubai Airport"}},
          {"code": "AMS", "country_code": "NL", "flightable": true, "name": "Amsterdam Airport Schiphol", "name_translations": {"en": "Amsterdam Airport Schiphol"}},
          {"code": "BCN", "city_code": "BCN", "country_code": "ES", "flightable": true, "name": "Barcelona-El Prat Airport", "name_translations": {"en": "Barcelona-El Prat Airport"}},
          {"code": "XJB", "city_code": "BCN", "country_code": "ES", "flightable": true, "name": "Barcelona Bus Station", "name_translations": {"en": "Barcelona Bus Station"}}
        ]
        """,
        encoding="utf-8",
    )
    return Store(cache)


class FliMcpTests(unittest.TestCase):
    def test_fli_search_parser_defaults_to_self_hosted_mcp_url(self) -> None:
        args = build_parser().parse_args(
            [
                "fli-search",
                "IST",
                "LHR",
                "--depart-date",
                "2026-08-15",
                "--direct-only",
                "--only-carrier",
                "TK",
            ]
        )

        self.assertEqual(args.command_name, "fli-search")
        self.assertEqual(args.mcp_url, "http://127.0.0.1:8000/mcp")
        self.assertTrue(args.direct_only)
        self.assertEqual(args.only_carrier, ["TK"])
        self.assertEqual(args.cache_ttl_seconds, 21600)

    def test_live_assemble_parser_uses_auto_provider_policy(self) -> None:
        args = build_parser().parse_args(
            [
                "route",
                "live-assemble",
                "SVX",
                "LHR",
                "--depart-date",
                "2026-08-15",
            ]
        )

        self.assertEqual(args.command_name, "route live-assemble")
        self.assertEqual(args.provider_policy, "auto")
        self.assertEqual(args.fli_mcp_url, "http://127.0.0.1:8000/mcp")
        self.assertEqual(args.segment_limit, 30)

    def test_parse_fli_flight_search_normalizes_segment_result(self) -> None:
        raw = {
            "success": True,
            "count": 1,
            "trip_type": "ONE_WAY",
            "flights": [
                {
                    "price": 245,
                    "currency": "USD",
                    "legs": [
                        {
                            "departure_airport": "Airport.IST",
                            "arrival_airport": "Airport.LHR",
                            "departure_time": "2026-08-15T10:20:00+03:00",
                            "arrival_time": "2026-08-15T12:30:00+01:00",
                            "duration": "4 hr 10 min",
                            "airline_code": "TK",
                            "flight_number": "1987",
                        }
                    ],
                }
            ],
        }

        result = parse_fli_flight_search(
            raw,
            origin="IST",
            destination="LHR",
            depart_date="2026-08-15",
            currency="RUB",
            mcp_url="http://127.0.0.1:8000/mcp",
            store=store_with_airports(self),
        )
        segment = fli_result_to_segment_result(result, direction="outbound", leg="hub_to_destination")

        self.assertEqual(result["offer_count"], 1)
        self.assertEqual(result["offers"][0]["flight_numbers"], ["TK1987"])
        self.assertEqual(result["offers"][0]["duration"], 250)
        self.assertEqual(segment["source_key"], "fli_mcp_search_flights")
        self.assertEqual(segment["offers"][0]["source"], "FLI MCP search_flights")
        self.assertEqual(segment["offers"][0]["segments"][0]["carrier"], "TK")

    def test_resolve_fli_airport_maps_observed_airport_names(self) -> None:
        store = store_with_airports(self)

        cases = {
            "Istanbul Airport": "IST",
            "Charles de Gaulle International Airport": "CDG",
            "London Heathrow Airport": "LHR",
            "Dubai International Airport": "DXB",
            "Amsterdam Airport Schiphol": "AMS",
        }

        for name, code in cases.items():
            with self.subTest(name=name):
                self.assertEqual(resolve_fli_airport(name, store=store, field="airport"), code)

    def test_resolve_fli_airport_prefers_query_code_for_ambiguous_fli_name(self) -> None:
        store = store_with_airports(self)

        with self.assertRaises(CliError):
            resolve_fli_airport("Barcelona International Airport", store=store, field="arrival_airport")

        self.assertEqual(
            resolve_fli_airport(
                "Barcelona International Airport",
                store=store,
                field="arrival_airport",
                preferred_code="BCN",
            ),
            "BCN",
        )

    def test_parse_fli_flight_search_uses_query_destination_for_ambiguous_final_airport(self) -> None:
        raw = {
            "success": True,
            "count": 1,
            "trip_type": "ONE_WAY",
            "flights": [
                {
                    "price": 21691,
                    "currency": "RUB",
                    "legs": [
                        {
                            "departure_airport": "Istanbul Airport",
                            "arrival_airport": "Barcelona International Airport",
                            "departure_time": "2026-08-16T18:10:00",
                            "arrival_time": "2026-08-16T21:00:00",
                            "duration": 230,
                            "airline": "Vueling",
                            "airline_code": "VY",
                            "flight_number": "3071",
                        }
                    ],
                }
            ],
        }

        result = parse_fli_flight_search(
            raw,
            origin="IST",
            destination="BCN",
            depart_date="2026-08-16",
            currency="RUB",
            mcp_url="http://127.0.0.1:8000/mcp",
            store=store_with_airports(self),
        )

        offer = result["offers"][0]
        self.assertEqual(offer["origin"], "IST")
        self.assertEqual(offer["destination"], "BCN")
        self.assertEqual(offer["flights"][0]["origin"], "IST")
        self.assertEqual(offer["flights"][0]["destination"], "BCN")

    def test_parse_fli_flight_search_maps_real_fli_airport_names(self) -> None:
        raw = {
            "success": True,
            "count": 1,
            "trip_type": "ONE_WAY",
            "flights": [
                {
                    "price": 11124,
                    "currency": "RUB",
                    "legs": [
                        {
                            "departure_airport": "Istanbul Airport",
                            "arrival_airport": "Charles de Gaulle International Airport",
                            "departure_time": "2026-07-19T10:10:00",
                            "arrival_time": "2026-07-19T12:50:00",
                            "duration": 220,
                            "airline": "Turkish Airlines",
                            "airline_code": "TK",
                            "flight_number": "1823",
                        }
                    ],
                }
            ],
        }

        result = parse_fli_flight_search(
            raw,
            origin="IST",
            destination="CDG",
            depart_date="2026-07-19",
            currency="RUB",
            mcp_url="http://127.0.0.1:8000/mcp",
            store=store_with_airports(self),
        )

        offer = result["offers"][0]
        self.assertEqual(offer["origin"], "IST")
        self.assertEqual(offer["destination"], "CDG")
        self.assertEqual(offer["flights"][0]["origin"], "IST")
        self.assertEqual(offer["flights"][0]["destination"], "CDG")

    def test_decode_mcp_event_stream_extracts_jsonrpc_result(self) -> None:
        payload = b'event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{"structuredContent":{"success":true,"flights":[]}}}\n\n'

        decoded = decode_mcp_response(payload, "text/event-stream")

        self.assertEqual(decoded["result"]["structuredContent"]["flights"], [])

    def test_provider_policy_uses_kupibilet_for_ru_touching_and_fli_for_global(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = Path(tmp_dir)
            (cache / "airports_en.json").write_text(
                """
                [
                  {"code": "SVX", "country_code": "RU", "flightable": true},
                  {"code": "IST", "country_code": "TR", "flightable": true},
                  {"code": "LHR", "country_code": "GB", "flightable": true}
                ]
                """,
                encoding="utf-8",
            )
            store = Store(cache)

            self.assertEqual(providers_for_segment({"origin": "SVX", "destination": "IST"}, store, "auto"), ["kupibilet"])
            self.assertEqual(providers_for_segment({"origin": "IST", "destination": "LHR"}, store, "auto"), ["fli"])
            self.assertEqual(providers_for_segment({"origin": "IST", "destination": "LHR"}, store, "both"), ["kupibilet", "fli"])


if __name__ == "__main__":
    unittest.main()
