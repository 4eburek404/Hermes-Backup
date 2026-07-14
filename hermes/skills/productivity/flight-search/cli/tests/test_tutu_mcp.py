from __future__ import annotations

import http.client
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from flights_cli.adapters.providers.tutu_adapter import TutuProviderAdapter
from flights_cli.errors import CliError
from flights_cli.providers.tutu_mcp import (
    MCP_PROTOCOL_VERSION,
    TUTU_MAX_PAGES,
    TUTU_MAX_SCOPE_PAGES,
    TUTU_PAGE_SIZE,
    cached_tutu_avia_search,
    extract_tool_payload,
    fetch_tutu_avia_search,
    parse_tutu_avia_search,
    tutu_mcp_http_post,
)
from flights_cli.store import Store

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "providers"
CATALOG_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "catalog"


def store_with_tutu_catalog(test_case: unittest.TestCase) -> Store:
    tmp_dir = tempfile.TemporaryDirectory()
    test_case.addCleanup(tmp_dir.cleanup)
    cache = Path(tmp_dir.name)
    (cache / "cities_ru.json").write_text(
        """
        [
          {"code": "SVX", "name": "Екатеринбург", "country_code": "RU", "has_flightable_airport": true},
          {"code": "AMS", "name": "Амстердам", "country_code": "NL", "has_flightable_airport": true},
          {"code": "IST", "name": "Стамбул", "country_code": "TR", "has_flightable_airport": true},
          {"code": "LON", "name": "Лондон", "country_code": "GB", "has_flightable_airport": true},
          {"code": "AER", "name": "Сочи", "country_code": "RU", "has_flightable_airport": true}
        ]
        """,
        encoding="utf-8",
    )
    (cache / "airports_en.json").write_text(
        """
        [
          {"code": "SVX", "city_code": "SVX", "country_code": "RU", "flightable": true},
          {"code": "AMS", "city_code": "AMS", "country_code": "NL", "flightable": true},
          {"code": "IST", "city_code": "IST", "country_code": "TR", "flightable": true},
          {"code": "AER", "city_code": "AER", "country_code": "RU", "flightable": true},
          {"code": "LHR", "city_code": "LON", "country_code": "GB", "flightable": true},
          {"code": "LGW", "city_code": "LON", "country_code": "GB", "flightable": true},
          {"code": "STN", "city_code": "LON", "country_code": "GB", "flightable": true}
        ]
        """,
        encoding="utf-8",
    )
    (cache / "airlines_en.json").write_text(
        """
        [
          {"code": "SU", "name": "Aeroflot", "name_translations": {"en": "Aeroflot"}},
          {"code": "TK", "name": "Turkish Airlines", "name_translations": {"en": "Turkish Airlines"}},
          {"code": "LO", "name": "LOT Polish", "name_translations": {"en": "LOT Polish"}},
          {"code": "UT", "name": "Utair", "name_translations": {"en": "Utair"}},
          {"code": "ЮЭ", "name": "Utair", "name_translations": {"en": "Utair"}}
        ]
        """,
        encoding="utf-8",
    )
    (cache / "airlines_ru.json").write_text(
        """
        [
          {"code": "SU", "name": "Аэрофлот", "name_translations": {"en": "Aeroflot"}},
          {"code": "TK", "name": "Турецкие авиалинии", "name_translations": {"en": "Turkish Airlines"}},
          {"code": "LO", "name": "LOT Polish", "name_translations": {"en": "LOT Polish"}},
          {"code": "UT", "name": "ЮТэйр", "name_translations": {"en": "Utair"}}
        ]
        """,
        encoding="utf-8",
    )
    return Store(cache)


def tutu_segment(
    origin: str,
    destination: str,
    number: str,
    *,
    carrier: str = "SU",
    depart: str = "2026-08-15T10:00:00+05:00",
    arrive: str = "2026-08-15T12:00:00+03:00",
) -> dict:
    return {
        "from": f"City — Airport ({origin})",
        "to": f"City — Airport ({destination})",
        "carrier": carrier,
        "voyage_no": number,
        "departure_at": depart,
        "arrival_at": arrive,
        "duration_min": 120,
    }


def tutu_offer(
    offer_id: str, legs: list[list[dict]], *, price: int = 10000, **extra: object
) -> dict:
    return {
        "offer_id": offer_id,
        "price": {"amount": price, "currency": "RUB"},
        "duration_min": 180,
        "legs": [{"segments": segments} for segments in legs],
        **extra,
    }


class TutuMcpProviderTests(unittest.TestCase):
    def test_diagnose_probe_allows_tutu_provider(self) -> None:
        from flights_cli.cli import build_parser

        args = build_parser().parse_args(
            [
                "diagnose",
                "probe",
                "--provider",
                "tutu",
                "--request",
                "probe.json",
            ]
        )

        self.assertEqual(args.command_name, "diagnose probe")
        self.assertEqual(args.provider, "tutu")

    def test_http_post_sends_mcp_protocol_version_header(self) -> None:
        captured: dict[str, str] = {}

        class FakeResponse:
            headers = {"Content-Type": "application/json"}

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return b'{"jsonrpc":"2.0","result":{}}'

        def fake_urlopen(request, *, timeout: int):  # type: ignore[no-untyped-def]
            captured.update(
                {key.lower(): value for key, value in request.header_items()}
            )
            return FakeResponse()

        with patch(
            "flights_cli.providers.tutu_mcp.urllib.request.urlopen", fake_urlopen
        ):
            tutu_mcp_http_post(
                "https://mcp.tutu.ru/mcp", {"jsonrpc": "2.0"}, timeout=10
            )

        self.assertEqual(captured["mcp-protocol-version"], MCP_PROTOCOL_VERSION)
        self.assertIn("application/json", captured["accept"])
        self.assertIn("text/event-stream", captured["accept"])

    def test_http_post_retries_incomplete_read_once_and_succeeds(self) -> None:
        calls = 0

        class FakeResponse:
            headers = {"Content-Type": "application/json"}

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise http.client.IncompleteRead(b'{"jsonrpc"', 20)
                return b'{"jsonrpc":"2.0","result":{"ok":true}}'

        with (
            patch(
                "flights_cli.providers.tutu_mcp.urllib.request.urlopen",
                return_value=FakeResponse(),
            ),
            patch("flights_cli.providers.tutu_mcp.time.sleep") as sleep,
        ):
            response, session_id = tutu_mcp_http_post(
                "https://mcp.tutu.ru/mcp",
                {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": "search_avia"},
                },
                timeout=10,
            )

        self.assertEqual(response["result"], {"ok": True})
        self.assertIsNone(session_id)
        self.assertEqual(calls, 2)
        sleep.assert_called_once()

    def test_http_post_reports_incomplete_read_after_retries(self) -> None:
        class FakeResponse:
            headers = {"Content-Type": "application/json"}

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                raise http.client.IncompleteRead(b"partial", 10)

        with (
            patch(
                "flights_cli.providers.tutu_mcp.urllib.request.urlopen",
                return_value=FakeResponse(),
            ),
            patch("flights_cli.providers.tutu_mcp.time.sleep"),
            self.assertRaises(CliError) as error,
        ):
            tutu_mcp_http_post(
                "https://mcp.tutu.ru/mcp",
                {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": "search_avia"},
                },
                timeout=10,
            )

        self.assertEqual(error.exception.error_type, "upstream_incomplete_read")
        self.assertEqual(error.exception.details["failure_reason"], "incomplete_read")
        self.assertEqual(error.exception.details["tool"], "search_avia")
        self.assertEqual(error.exception.details["bytes_read"], len(b"partial"))
        self.assertEqual(error.exception.details["bytes_missing"], 10)
        self.assertEqual(
            error.exception.details["bytes_expected"], len(b"partial") + 10
        )

    def test_extract_tool_payload_accepts_structured_json(self) -> None:
        payload = extract_tool_payload(
            {"structuredContent": {"result": {"offers": []}}}
        )

        self.assertEqual(payload, {"offers": []})

    def test_extract_tool_payload_accepts_text_wrapped_json(self) -> None:
        payload = extract_tool_payload(
            {
                "content": [
                    {"type": "text", "text": json.dumps({"result": '{"offers":[]}'})}
                ]
            }
        )

        self.assertEqual(payload, {"offers": []})

    def test_extract_tool_payload_accepts_plain_text(self) -> None:
        payload = extract_tool_payload(
            {
                "content": [
                    {"type": "text", "text": "# Avia instructions\nUse search_avia."}
                ]
            }
        )

        self.assertEqual(payload, "# Avia instructions\nUse search_avia.")

    def test_extract_tool_payload_preserves_tool_errors(self) -> None:
        with self.assertRaises(CliError) as error:
            extract_tool_payload(
                {
                    "isError": True,
                    "content": [{"type": "text", "text": "bad request"}],
                }
            )

        self.assertEqual(error.exception.error_type, "upstream_error")
        self.assertIn("bad request", str(error.exception))

    def test_fetch_paginates_before_applying_display_limit(self) -> None:
        store = store_with_tutu_catalog(self)
        calls: list[dict] = []

        def fake_call(tool_name: str, arguments: dict, **kwargs: object) -> dict:
            calls.append(arguments)
            page = int(arguments.get("page") or 1)
            if page == 1:
                return {
                    "offers": [
                        tutu_offer(
                            "page-1",
                            [[tutu_segment("SVX", "AMS", "100")]],
                            price=20000,
                        )
                    ],
                    "meta": {"has_more": True},
                }
            return {
                "offers": [
                    tutu_offer(
                        "page-2",
                        [[tutu_segment("SVX", "AMS", "200")]],
                        price=10000,
                    )
                ],
                "meta": {"has_more": False},
            }

        with patch("flights_cli.providers.tutu_mcp.call_tutu_mcp_tool", fake_call):
            result = fetch_tutu_avia_search(
                "SVX",
                "AMS",
                date(2026, 8, 15),
                currency="RUB",
                limit=1,
                store=store,
            )

        self.assertEqual([call.get("page") for call in calls], [None, 2])
        self.assertEqual(calls[0]["page_size"], TUTU_PAGE_SIZE)
        self.assertEqual(result["raw_count"], 2)
        self.assertEqual(result["offer_count"], 1)
        self.assertEqual(result["pagination"]["pages_fetched"], 2)
        self.assertFalse(result["pagination"]["not_fetched_due_to_page_budget"])

    def test_fetch_passes_direct_only_and_resolved_carriers_to_mcp(self) -> None:
        store = store_with_tutu_catalog(self)
        calls: list[dict] = []

        def fake_call(tool_name: str, arguments: dict, **kwargs: object) -> dict:
            self.assertEqual(tool_name, "search_avia")
            calls.append(arguments)
            return {
                "offers": [],
                "meta": {
                    "has_more": False,
                    "carriers_available": ["Аэрофлот"],
                },
            }

        with patch("flights_cli.providers.tutu_mcp.call_tutu_mcp_tool", fake_call):
            fetch_tutu_avia_search(
                "SVX",
                "AMS",
                date(2026, 8, 15),
                currency="RUB",
                only_carriers=["SU"],
                direct_only=True,
                store=store,
            )

        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[0]["direct_only"])
        self.assertNotIn("carriers", calls[0])
        self.assertEqual(calls[0]["page_size"], 1)
        self.assertEqual(calls[1]["carriers"], ["Аэрофлот"])

    def test_fetch_omits_false_direct_only_and_uses_exact_unknown_carrier_facet(
        self,
    ) -> None:
        store = store_with_tutu_catalog(self)
        calls: list[dict] = []

        def fake_call(tool_name: str, arguments: dict, **kwargs: object) -> dict:
            calls.append(arguments)
            return {
                "offers": [],
                "meta": {
                    "has_more": False,
                    "carriers_available": ["Unknown Air"],
                },
            }

        with patch("flights_cli.providers.tutu_mcp.call_tutu_mcp_tool", fake_call):
            fetch_tutu_avia_search(
                "SVX",
                "AMS",
                date(2026, 8, 15),
                currency="RUB",
                only_carriers=["Unknown Air"],
                direct_only=False,
                store=store,
            )

        self.assertNotIn("direct_only", calls[0])
        self.assertEqual(calls[1]["carriers"], ["Unknown Air"])

    def test_fetch_resolves_lo_facet_and_ignores_invalid_duplicate_code(self) -> None:
        store = store_with_tutu_catalog(self)
        calls: list[dict] = []

        def fake_call(tool_name: str, arguments: dict, **kwargs: object) -> dict:
            calls.append(arguments)
            carrier = "LOT - Polish Airlines" if len(calls) == 1 else "Utair"
            return {
                "offers": [],
                "meta": {
                    "has_more": False,
                    "carriers_available": [
                        {"name": carrier, "offers_count": 12, "price_from": 8195.0}
                    ],
                },
            }

        with patch("flights_cli.providers.tutu_mcp.call_tutu_mcp_tool", fake_call):
            fetch_tutu_avia_search(
                "SVX",
                "AMS",
                date(2026, 8, 15),
                currency="RUB",
                only_carriers=["LO"],
                store=store,
            )

        self.assertEqual(calls[1]["carriers"], ["LOT - Polish Airlines"])

        segment = tutu_segment("SVX", "AMS", "100", carrier="Utair")
        result = parse_tutu_avia_search(
            {"offers": [tutu_offer("ut", [[segment]])]},
            origin="SVX",
            destination="AMS",
            depart_date="2026-08-15",
            currency="RUB",
            store=store,
            carrier_name_overrides={"utair": "UT"},
        )
        self.assertEqual(result["offers"][0]["marketing_carriers"], ["UT"])

    def test_fetch_uses_exact_iata_for_single_airport_scope(self) -> None:
        store = store_with_tutu_catalog(self)
        calls: list[dict] = []

        def fake_call(tool_name: str, arguments: dict, **kwargs: object) -> dict:
            calls.append(arguments)
            return {"offers": [], "meta": {"has_more": False}}

        with patch("flights_cli.providers.tutu_mcp.call_tutu_mcp_tool", fake_call):
            result = fetch_tutu_avia_search(
                "SVX",
                "LON",
                date(2026, 8, 15),
                currency="RUB",
                origin_airports=["SVX"],
                destination_airports=["LHR"],
                store=store,
            )

        self.assertEqual(calls[0]["origin"], "SVX")
        self.assertEqual(calls[0]["destination"], "LHR")
        self.assertEqual(result["pagination"]["destination_input_kind"], "airport")

    def test_cached_tutu_search_normalizes_scopes_in_key_and_fetch(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_fetch(
            origin: str, destination: str, depart_date: date, **kwargs: object
        ) -> dict:
            calls.append(dict(kwargs))
            return {"offers": []}

        common = {
            "currency": "RUB",
            "only_carriers": [],
            "direct_only": False,
            "limit": 20,
            "timeout": 10,
            "use_cache": False,
            "fetcher": fake_fetch,
        }
        first = cached_tutu_avia_search(
            "ORG",
            "DST",
            date(2026, 8, 15),
            **common,
            origin_airports=["AAB", "AAA", "aaa"],
            destination_airports=["BBB"],
        )
        equivalent = cached_tutu_avia_search(
            "ORG",
            "DST",
            date(2026, 8, 15),
            **common,
            origin_airports=["AAA", "AAB"],
            destination_airports=["bbb"],
        )
        different = cached_tutu_avia_search(
            "ORG",
            "DST",
            date(2026, 8, 15),
            **common,
            origin_airports=["AAA"],
            destination_airports=["BBC"],
        )

        self.assertEqual(calls[0]["origin_airports"], ["AAA", "AAB"])
        self.assertEqual(first["cache"]["key"], equivalent["cache"]["key"])
        self.assertNotEqual(first["cache"]["key"], different["cache"]["key"])

    def test_fetch_uses_city_query_and_larger_budget_for_multi_airport_scope(
        self,
    ) -> None:
        store = store_with_tutu_catalog(self)
        calls: list[dict] = []

        def fake_call(tool_name: str, arguments: dict, **kwargs: object) -> dict:
            calls.append(arguments)
            page = int(arguments.get("page") or 1)
            return {
                "offers": [
                    tutu_offer(
                        f"page-{page}",
                        [
                            [
                                tutu_segment(
                                    "SVX",
                                    "LHR",
                                    str(100 + page),
                                    depart=f"2026-08-15T{page:02d}:00:00+05:00",
                                    arrive=f"2026-08-15T{page + 2:02d}:00:00+03:00",
                                )
                            ]
                        ],
                    )
                ],
                "meta": {"has_more": True},
            }

        with patch("flights_cli.providers.tutu_mcp.call_tutu_mcp_tool", fake_call):
            result = fetch_tutu_avia_search(
                "SVX",
                "LON",
                date(2026, 8, 15),
                currency="RUB",
                origin_airports=["SVX"],
                destination_airports=["LHR", "LGW"],
                store=store,
            )

        self.assertEqual(calls[0]["destination"], "Лондон")
        self.assertEqual(len(calls), TUTU_MAX_SCOPE_PAGES)
        self.assertEqual(result["pagination"]["max_pages"], TUTU_MAX_SCOPE_PAGES)
        self.assertTrue(result["pagination"]["airport_scope_incomplete"])

    def test_fetch_rejects_plain_text_payload_for_search(self) -> None:
        store = store_with_tutu_catalog(self)

        with (
            patch(
                "flights_cli.providers.tutu_mcp.call_tutu_mcp_tool",
                return_value="# Avia instructions",
            ),
            self.assertRaises(CliError) as error,
        ):
            fetch_tutu_avia_search(
                "SVX",
                "AMS",
                date(2026, 8, 15),
                currency="RUB",
                store=store,
            )

        self.assertEqual(error.exception.error_type, "upstream_error")
        self.assertEqual(error.exception.details["tool"], "search_avia")

    def test_parser_keeps_provider_inventory_when_limit_covers_catalog(self) -> None:
        store = store_with_tutu_catalog(self)
        raw = {
            "offers": [
                tutu_offer(
                    f"offer-{index}",
                    [
                        [
                            tutu_segment(
                                "SVX",
                                "AMS",
                                f"SU{100 + index}",
                                depart=f"2026-08-15T10:{index:02d}:00+05:00",
                                arrive=f"2026-08-15T12:{index:02d}:00+03:00",
                            )
                        ]
                    ],
                    price=10000 + index,
                )
                for index in range(22)
            ]
        }

        result = parse_tutu_avia_search(
            raw,
            origin="SVX",
            destination="AMS",
            depart_date="2026-08-15",
            currency="RUB",
            direct_only=True,
            limit=30,
            store=store,
        )

        self.assertEqual(result["raw_count"], 22)
        self.assertEqual(result["unique_flight_count"], 22)
        self.assertEqual(result["offer_count"], 22)
        self.assertEqual(result["omitted_offer_count"], 0)
        self.assertEqual(len(result["offers"]), 22)

    def test_fetch_marks_remaining_pages_when_page_budget_is_exhausted(self) -> None:
        store = store_with_tutu_catalog(self)
        calls: list[dict] = []

        def fake_call(tool_name: str, arguments: dict, **kwargs: object) -> dict:
            calls.append(arguments)
            page = int(arguments.get("page") or 1)
            return {
                "offers": [
                    tutu_offer(
                        f"page-{page}",
                        [[tutu_segment("SVX", "AMS", str(100 + page))]],
                        price=10000 + page,
                    )
                ],
                "meta": {"has_more": True},
            }

        with patch("flights_cli.providers.tutu_mcp.call_tutu_mcp_tool", fake_call):
            result = fetch_tutu_avia_search(
                "SVX",
                "AMS",
                date(2026, 8, 15),
                currency="RUB",
                limit=20,
                store=store,
            )

        self.assertEqual(len(calls), TUTU_MAX_PAGES)
        self.assertEqual(result["pagination"]["pages_fetched"], TUTU_MAX_PAGES)
        self.assertTrue(result["pagination"]["not_fetched_due_to_page_budget"])

    def test_parser_does_not_apply_tutu_direct_or_carrier_postfilters(self) -> None:
        store = store_with_tutu_catalog(self)
        raw = {
            "offers": [
                tutu_offer(
                    "direct-su",
                    [[tutu_segment("SVX", "AMS", "100", carrier="SU")]],
                    price=10000,
                ),
                tutu_offer(
                    "connected-tk",
                    [
                        [
                            tutu_segment("SVX", "IST", "101", carrier="TK"),
                            tutu_segment("IST", "AMS", "102", carrier="TK"),
                        ]
                    ],
                    price=11000,
                ),
            ]
        }

        result = parse_tutu_avia_search(
            raw,
            origin="SVX",
            destination="AMS",
            depart_date="2026-08-15",
            currency="RUB",
            direct_only=True,
            only_carriers=["SU"],
            store=store,
        )

        self.assertEqual(
            [offer["id"] for offer in result["offers"]],
            ["direct-su", "connected-tk"],
        )
        self.assertNotIn("not_direct", result["skipped"])
        self.assertNotIn("carrier", result["skipped"])
        self.assertTrue(result["filters"]["direct_only"])
        self.assertEqual(result["filters"]["only_carriers"], ["SU"])

    def test_parser_resolves_tutu_localized_carrier_names_without_flight_number(
        self,
    ) -> None:
        store = store_with_tutu_catalog(self)
        raw = {
            "offers": [
                tutu_offer(
                    "su-name",
                    [[tutu_segment("SVX", "AMS", "", carrier="Аэрофлот")]],
                ),
                tutu_offer(
                    "tk-name",
                    [
                        [
                            tutu_segment(
                                "SVX",
                                "AMS",
                                "",
                                carrier="Турецкие авиалинии",
                                depart="2026-08-15T11:00:00+05:00",
                                arrive="2026-08-15T13:00:00+03:00",
                            )
                        ]
                    ],
                ),
            ]
        }

        result = parse_tutu_avia_search(
            raw,
            origin="SVX",
            destination="AMS",
            depart_date="2026-08-15",
            currency="RUB",
            only_carriers=["SU"],
            store=store,
        )

        self.assertEqual(
            [offer["id"] for offer in result["offers"]], ["su-name", "tk-name"]
        )
        su_offer = next(offer for offer in result["offers"] if offer["id"] == "su-name")
        self.assertEqual(su_offer["flight_numbers"], [])
        self.assertEqual(su_offer["marketing_carriers"], ["SU"])
        self.assertNotIn("carrier", result["skipped"])

    def test_airport_scope_keeps_airports_distinct_from_city_scope(self) -> None:
        store = store_with_tutu_catalog(self)
        raw = {
            "offers": [
                tutu_offer("wrong-airport", [[tutu_segment("SVX", "LGW", "100")]]),
                tutu_offer("exact-airport", [[tutu_segment("SVX", "LHR", "200")]]),
            ]
        }

        exact = parse_tutu_avia_search(
            raw,
            origin="SVX",
            destination="LHR",
            depart_date="2026-08-15",
            currency="RUB",
            store=store,
        )
        city = parse_tutu_avia_search(
            raw,
            origin="SVX",
            destination="LON",
            depart_date="2026-08-15",
            currency="RUB",
            store=store,
        )

        self.assertEqual([offer["id"] for offer in exact["offers"]], ["exact-airport"])
        self.assertEqual(exact["skipped"]["outside_airport_scope"], 1)
        self.assertEqual(
            sorted(offer["id"] for offer in city["offers"]),
            ["exact-airport", "wrong-airport"],
        )

    def test_round_trip_offer_keeps_outbound_and_return_journeys_separate(self) -> None:
        store = store_with_tutu_catalog(self)
        raw = {
            "offers": [
                tutu_offer(
                    "round-trip",
                    [
                        [tutu_segment("SVX", "AER", "100")],
                        [
                            tutu_segment(
                                "AER",
                                "SVX",
                                "101",
                                depart="2026-08-22T10:00:00+03:00",
                                arrive="2026-08-22T14:00:00+05:00",
                            )
                        ],
                    ],
                )
            ]
        }

        result = parse_tutu_avia_search(
            raw,
            origin="SVX",
            destination="AER",
            depart_date="2026-08-15",
            return_date="2026-08-22",
            currency="RUB",
            store=store,
        )
        offer = result["offers"][0]

        self.assertEqual(offer["journey_scope"], "round_trip")
        self.assertEqual(offer["origin"], "SVX")
        self.assertEqual(offer["destination"], "AER")
        self.assertEqual(len(offer["segments"]), 1)
        self.assertEqual(
            [journey["direction"] for journey in offer["journeys"]],
            ["outbound", "return"],
        )
        self.assertEqual(offer["number_of_changes"], 0)
        self.assertEqual(result["return_date"], "2026-08-22")

    def test_parser_preserves_tutu_self_transfer_evidence(self) -> None:
        store = store_with_tutu_catalog(self)
        raw = {
            "offers": [
                tutu_offer(
                    "multi-pnr",
                    [[tutu_segment("SVX", "AMS", "100")]],
                    is_multi_pnr=True,
                    has_self_transfer=True,
                    multi_pnr_note="Collect baggage and check in again.",
                )
            ]
        }

        result = parse_tutu_avia_search(
            raw,
            origin="SVX",
            destination="AMS",
            depart_date="2026-08-15",
            currency="RUB",
            store=store,
        )

        offer = result["offers"][0]
        self.assertIs(offer["self_transfer"], True)
        self.assertEqual(offer["self_transfer_source"], "tutu")
        self.assertEqual(
            offer["self_transfer_note"], "Collect baggage and check in again."
        )

    def test_round_trip_fixture_normalizes_provider_offer(self) -> None:
        payload = json.loads(
            (FIXTURE_DIR / "tutu_search_avia_svx_aer_round_trip.json").read_text(
                encoding="utf-8"
            )
        )
        query = payload["query"]
        result = parse_tutu_avia_search(
            payload["raw"],
            origin=query["origin"],
            destination=query["destination"],
            depart_date=query["depart_date"],
            return_date=query["return_date"],
            currency=query["currency"],
            direct_only=query["direct_only"],
            store=Store(CATALOG_FIXTURE_DIR),
        )

        self.assertEqual(result["return_date"], "2026-08-22")
        self.assertEqual(result["offer_count"], 1)
        offer = result["offers"][0]
        self.assertEqual(offer["journey_scope"], "round_trip")
        self.assertEqual(offer["ticketing_model"], "provider_order_unverified")
        self.assertEqual(offer["marketing_carriers"], ["U6"])
        self.assertEqual(
            [journey["direction"] for journey in offer["journeys"]],
            ["outbound", "return"],
        )

    def test_segment_adapter_passes_direct_only_without_return_date(self) -> None:
        store = store_with_tutu_catalog(self)
        calls: list[dict] = []

        def fake_fetcher(
            origin: str, destination: str, depart_date: date, **kwargs: object
        ) -> dict:
            calls.append(kwargs)
            return {
                "origin": origin,
                "destination": destination,
                "depart_date": depart_date.isoformat(),
                "currency": kwargs["currency"],
                "source": "fake",
                "source_url": "https://mcp.tutu.ru/mcp",
                "raw_count": 0,
                "unique_flight_count": 0,
                "offer_count": 0,
                "skipped": {},
                "filters": {
                    "direct_only": kwargs["direct_only"],
                    "only_carriers": kwargs["only_carriers"],
                },
                "offers": [],
            }

        adapter = TutuProviderAdapter(store=store, fetcher=fake_fetcher)
        adapter.search_segment(
            {
                "probe_id": "seg-1",
                "direction": "outbound",
                "leg": "direct_destination_control",
                "origin": "SVX",
                "destination": "AMS",
                "date": "2026-08-15",
                "currency": "RUB",
                "only_carriers": ["SU"],
                "origin_airports": [" svx ", "SVX"],
                "destination_airports": ["ams"],
                "direct_only": True,
                "limit": 17,
                "use_cache": False,
            }
        )

        self.assertTrue(calls[0]["direct_only"])
        self.assertEqual(calls[0]["only_carriers"], ["SU"])
        self.assertEqual(calls[0]["limit"], 17)
        self.assertIsNone(calls[0]["return_date"])
        self.assertEqual(calls[0]["origin_airports"], ["SVX"])
        self.assertEqual(calls[0]["destination_airports"], ["AMS"])

    def test_aggregate_adapter_passes_return_date_and_keeps_round_trip_capability(
        self,
    ) -> None:
        store = store_with_tutu_catalog(self)
        calls: list[dict] = []

        def fake_fetcher(
            origin: str, destination: str, depart_date: date, **kwargs: object
        ) -> dict:
            calls.append(kwargs)
            return {
                "origin": origin,
                "destination": destination,
                "depart_date": depart_date.isoformat(),
                "return_date": kwargs["return_date"].isoformat(),
                "currency": kwargs["currency"],
                "source": "fake",
                "source_url": "https://mcp.tutu.ru/mcp",
                "raw_count": 0,
                "unique_flight_count": 0,
                "offer_count": 0,
                "skipped": {},
                "filters": {
                    "direct_only": kwargs["direct_only"],
                    "only_carriers": kwargs["only_carriers"],
                },
                "offers": [],
            }

        adapter = TutuProviderAdapter(store=store, fetcher=fake_fetcher)
        result = adapter.search_aggregate(
            {
                "probe_id": "agg-1",
                "origin": "SVX",
                "destination": "AER",
                "date": "2026-08-15",
                "return_date": "2026-08-22",
                "currency": "RUB",
                "only_carriers": ["SU"],
                "origin_airports": ["svx"],
                "destination_airports": [" aer ", "AER"],
                "direct_only": True,
                "limit": 23,
                "use_cache": False,
            }
        )

        self.assertEqual(calls[0]["return_date"], date(2026, 8, 22))
        self.assertTrue(calls[0]["direct_only"])
        self.assertEqual(calls[0]["limit"], 23)
        self.assertTrue(adapter.capabilities.supports_round_trip)
        self.assertEqual(result.query["return_date"], "2026-08-22")
        self.assertEqual(result.query["origin_airports"], ["SVX"])
        self.assertEqual(result.query["destination_airports"], ["AER"])


if __name__ == "__main__":
    unittest.main()
