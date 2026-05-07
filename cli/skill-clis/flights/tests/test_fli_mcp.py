from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from flights_cli.cli import build_parser
from flights_cli.providers.fli_mcp import (
    decode_mcp_response,
    fli_result_to_segment_result,
    parse_fli_flight_search,
    providers_for_segment,
)
from flights_cli.store import Store


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
        )
        segment = fli_result_to_segment_result(result, direction="outbound", leg="hub_to_destination")

        self.assertEqual(result["offer_count"], 1)
        self.assertEqual(result["offers"][0]["flight_numbers"], ["TK1987"])
        self.assertEqual(result["offers"][0]["duration"], 250)
        self.assertEqual(segment["source_key"], "fli_mcp_search_flights")
        self.assertEqual(segment["offers"][0]["source"], "FLI MCP search_flights")
        self.assertEqual(segment["offers"][0]["segments"][0]["carrier"], "TK")

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
