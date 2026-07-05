from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from flights_cli.adapters.providers.tutu_adapter import TutuProviderAdapter
from flights_cli.providers.tutu_mcp import (
    MCP_PROTOCOL_VERSION,
    TUTU_MAX_PAGES,
    TUTU_PAGE_SIZE,
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
          {"code": "TK", "name": "Turkish Airlines", "name_translations": {"en": "Turkish Airlines"}}
        ]
        """,
        encoding="utf-8",
    )
    (cache / "airlines_ru.json").write_text(
        """
        [
          {"code": "SU", "name": "Аэрофлот", "name_translations": {"en": "Aeroflot"}},
          {"code": "TK", "name": "Турецкие авиалинии", "name_translations": {"en": "Turkish Airlines"}}
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


def tutu_offer(offer_id: str, legs: list[list[dict]], *, price: int = 10000) -> dict:
    return {
        "offer_id": offer_id,
        "price": {"amount": price, "currency": "RUB"},
        "duration_min": 180,
        "legs": [{"segments": segments} for segments in legs],
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

    def test_direct_only_filters_connected_tutu_offers(self) -> None:
        store = store_with_tutu_catalog(self)
        raw = {
            "offers": [
                tutu_offer("direct", [[tutu_segment("SVX", "AMS", "100")]]),
                tutu_offer(
                    "connected",
                    [
                        [
                            tutu_segment("SVX", "IST", "101"),
                            tutu_segment("IST", "AMS", "102"),
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
            direct_only=True,
            store=store,
        )

        self.assertEqual([offer["id"] for offer in result["offers"]], ["direct"])
        self.assertEqual(result["skipped"]["not_direct"], 1)
        self.assertTrue(result["filters"]["direct_only"])

    def test_carrier_filter_requires_each_segment_to_match(self) -> None:
        store = store_with_tutu_catalog(self)
        raw = {
            "offers": [
                tutu_offer("su", [[tutu_segment("SVX", "AMS", "100", carrier="SU")]]),
                tutu_offer("tk", [[tutu_segment("SVX", "AMS", "200", carrier="TK")]]),
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

        self.assertEqual([offer["id"] for offer in result["offers"]], ["su"])
        self.assertEqual(result["skipped"]["carrier"], 1)
        self.assertEqual(result["filters"]["only_carriers"], ["SU"])

    def test_carrier_filter_matches_tutu_localized_name_without_flight_number(
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
                    [[tutu_segment("SVX", "AMS", "", carrier="Турецкие авиалинии")]],
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

        self.assertEqual([offer["id"] for offer in result["offers"]], ["su-name"])
        self.assertEqual(result["offers"][0]["flight_numbers"], [])
        self.assertEqual(result["offers"][0]["marketing_carriers"], ["SU"])
        self.assertEqual(result["skipped"]["carrier"], 1)

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
        self.assertEqual(exact["skipped"]["airport_scope"], 1)
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
                "direct_only": True,
                "limit": 17,
                "use_cache": False,
            }
        )

        self.assertTrue(calls[0]["direct_only"])
        self.assertEqual(calls[0]["only_carriers"], ["SU"])
        self.assertEqual(calls[0]["limit"], 17)
        self.assertIsNone(calls[0]["return_date"])

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


if __name__ == "__main__":
    unittest.main()
