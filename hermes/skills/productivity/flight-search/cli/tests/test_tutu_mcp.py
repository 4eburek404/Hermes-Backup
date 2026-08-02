from __future__ import annotations

import asyncio
import gc
import json
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from unittest.mock import patch

import anyio
import httpx2
from mcp.shared.exceptions import MCPError
from mcp.types import (
    CONNECTION_CLOSED,
    INVALID_PARAMS,
    CallToolResult,
    TextContent,
)

from flights_cli.adapters.providers.tutu_adapter import TutuProviderAdapter
from flights_cli.errors import CliError
from flights_cli.providers import tutu_mcp as tutu_mcp_module
from flights_cli.providers.tutu_client import TutuMcpClient
from flights_cli.providers.tutu_mcp import (
    TUTU_MAX_PAGES,
    TUTU_MAX_SCOPE_PAGES,
    TUTU_PAGE_SIZE,
    cached_tutu_avia_search,
    fetch_tutu_avia_search,
    parse_tutu_avia_search as compatibility_parse_tutu_avia_search,
)
from flights_cli.providers.tutu_parser import parse_tutu_avia_search
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


def fake_tutu_client(handler):  # type: ignore[no-untyped-def]
    class FakeTutuMcpClient:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        async def __aenter__(self) -> "FakeTutuMcpClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def search_avia(self, arguments: dict) -> dict:
            return handler("search_avia", arguments)

    return patch("flights_cli.providers.tutu_mcp.TutuMcpClient", FakeTutuMcpClient)


class TutuMcpProviderTests(unittest.TestCase):
    def test_tutu_mcp_reexports_canonical_parser(self) -> None:
        self.assertIs(compatibility_parse_tutu_avia_search, parse_tutu_avia_search)

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

        with fake_tutu_client(fake_call):
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

        with fake_tutu_client(fake_call):
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

        with fake_tutu_client(fake_call):
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

        with fake_tutu_client(fake_call):
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

        with fake_tutu_client(fake_call):
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

        with fake_tutu_client(fake_call):
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

        with fake_tutu_client(fake_call):
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

    def test_transient_page_failure_retries_whole_workflow_in_new_session(
        self,
    ) -> None:
        sessions: list[list[int]] = []
        deadlines: list[float] = []

        class FakeClient:
            def __init__(self, **kwargs: object) -> None:
                self.calls: list[int] = []
                sessions.append(self.calls)
                deadlines.append(float(kwargs["deadline"]))

            async def __aenter__(self) -> "FakeClient":
                return self

            async def __aexit__(self, *args: object) -> None:
                return None

            async def search_avia(self, arguments: dict) -> dict:
                page = int(arguments.get("page") or 1)
                self.calls.append(page)
                if len(sessions) == 1 and page == 2:
                    raise httpx2.ReadError("truncated response")
                return {
                    "offers": [
                        tutu_offer(
                            f"session-{len(sessions)}-page-{page}",
                            [[tutu_segment("SVX", "AMS", str(page))]],
                        )
                    ],
                    "meta": {"has_more": page == 1},
                }

        async def no_wait(delay: float) -> None:
            self.assertEqual(delay, 0.25)

        with (
            patch("flights_cli.providers.tutu_mcp.TutuMcpClient", FakeClient),
            patch("flights_cli.providers.tutu_mcp.asyncio.sleep", no_wait),
        ):
            result = fetch_tutu_avia_search(
                "SVX",
                "AMS",
                date(2026, 8, 15),
                currency="RUB",
                timeout=5,
            )

        self.assertEqual(sessions, [[1, 2], [1, 2]])
        self.assertEqual(len(set(deadlines)), 1)
        self.assertEqual(result["pagination"]["pages_fetched"], 2)

    def test_sdk_task_group_connect_timeout_retries_in_new_session(self) -> None:
        sessions = 0

        class FakeHttpClient:
            def __init__(self, **kwargs: object) -> None:
                self.timeout = kwargs["timeout"]

            async def __aenter__(self) -> "FakeHttpClient":
                return self

            async def __aexit__(self, *args: object) -> None:
                return None

        class TaskGroupSdkClient:
            protocol_version = "2025-11-25"
            server_info = None

            def __init__(self, server: object, **kwargs: object) -> None:
                nonlocal sessions
                sessions += 1
                self.session_number = sessions

            async def __aenter__(self) -> "TaskGroupSdkClient":
                self.task_group = anyio.create_task_group()
                await self.task_group.__aenter__()
                return self

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc: BaseException | None,
                traceback: object,
            ) -> object:
                self.task_group.cancel_scope.cancel()
                return await self.task_group.__aexit__(exc_type, exc, traceback)

            async def call_tool(
                self,
                name: str,
                arguments: dict[str, object],
                **kwargs: object,
            ) -> CallToolResult:
                if name == "get_avia_instructions":
                    return CallToolResult(
                        content=[TextContent(type="text", text="# Playbook")]
                    )
                if self.session_number == 1:

                    async def fail_post() -> None:
                        await anyio.sleep(0)
                        raise httpx2.ConnectTimeout("POST connect timed out")

                    self.task_group.start_soon(fail_post)
                    await anyio.sleep_forever()
                return CallToolResult(
                    content=[
                        TextContent(
                            type="text",
                            text='{"offers": [], "meta": {"has_more": false}}',
                        )
                    ]
                )

        async def no_wait(delay: float) -> None:
            self.assertEqual(delay, 0.25)

        with (
            patch(
                "flights_cli.providers.tutu_client.httpx2.AsyncClient",
                FakeHttpClient,
            ),
            patch(
                "flights_cli.providers.tutu_client.streamable_http_client",
                return_value=object(),
            ),
            patch(
                "flights_cli.providers.tutu_client.Client",
                TaskGroupSdkClient,
            ),
            patch("flights_cli.providers.tutu_mcp.asyncio.sleep", no_wait),
        ):
            result = fetch_tutu_avia_search(
                "SVX",
                "AMS",
                date(2026, 8, 15),
                currency="RUB",
                timeout=5,
            )

        self.assertEqual(sessions, 2)
        self.assertEqual(result["offer_count"], 0)

    def test_two_transient_failures_return_bounded_cli_error(self) -> None:
        sessions = 0

        class FakeClient:
            def __init__(self, **kwargs: object) -> None:
                nonlocal sessions
                sessions += 1

            async def __aenter__(self) -> "FakeClient":
                error = httpx2.ConnectError("offline")
                error._tutu_operation = "initialize"  # type: ignore[attr-defined]
                raise error

            async def __aexit__(self, *args: object) -> None:
                return None

        async def no_wait(delay: float) -> None:
            return None

        with (
            patch("flights_cli.providers.tutu_mcp.TutuMcpClient", FakeClient),
            patch("flights_cli.providers.tutu_mcp.asyncio.sleep", no_wait),
            self.assertRaises(CliError) as error,
        ):
            fetch_tutu_avia_search(
                "SVX",
                "AMS",
                date(2026, 8, 15),
                currency="RUB",
                timeout=5,
            )

        self.assertEqual(sessions, 2)
        self.assertEqual(error.exception.details["provider"], "tutu")
        self.assertEqual(error.exception.details["attempts"], 2)
        self.assertEqual(error.exception.details["deadline_seconds"], 5.0)
        self.assertEqual(
            error.exception.details["terminal_error_types"], ["ConnectError"]
        )

    def test_exhausted_backoff_budget_prevents_second_session(self) -> None:
        sessions = 0

        class FakeClient:
            def __init__(self, **kwargs: object) -> None:
                nonlocal sessions
                sessions += 1

            async def __aenter__(self) -> "FakeClient":
                error = httpx2.ConnectError("offline")
                error._tutu_operation = "initialize"  # type: ignore[attr-defined]
                raise error

            async def __aexit__(self, *args: object) -> None:
                return None

        with (
            patch("flights_cli.providers.tutu_mcp.TutuMcpClient", FakeClient),
            self.assertRaises(CliError) as error,
        ):
            fetch_tutu_avia_search(
                "SVX",
                "AMS",
                date(2026, 8, 15),
                currency="RUB",
                timeout=0.1,  # type: ignore[arg-type]
            )

        self.assertEqual(sessions, 1)
        self.assertEqual(error.exception.error_type, "timeout")
        self.assertEqual(error.exception.details["operation"], "initialize")

    def test_search_timeout_keeps_tool_when_budget_prevents_retry(self) -> None:
        sessions = 0

        class FakeClient:
            def __init__(self, **kwargs: object) -> None:
                nonlocal sessions
                sessions += 1

            async def __aenter__(self) -> "FakeClient":
                return self

            async def __aexit__(self, *args: object) -> None:
                return None

            async def search_avia(self, arguments: dict) -> dict:
                error = TimeoutError("search deadline")
                error._tutu_operation = "search_avia"  # type: ignore[attr-defined]
                raise error

        with (
            patch("flights_cli.providers.tutu_mcp.TutuMcpClient", FakeClient),
            self.assertRaises(CliError) as error,
        ):
            fetch_tutu_avia_search(
                "SVX",
                "AMS",
                date(2026, 8, 15),
                currency="RUB",
                timeout=0.1,  # type: ignore[arg-type]
            )

        self.assertEqual(sessions, 1)
        self.assertEqual(error.exception.error_type, "timeout")
        self.assertEqual(error.exception.details["operation"], "search_avia")
        self.assertEqual(error.exception.details["tool"], "search_avia")

    def test_expired_client_deadline_retains_final_operation_and_tool(self) -> None:
        for operation in ("initialize", "search_avia"):
            sessions = 0

            class ExpiredDeadlineClient:
                def __init__(self, **kwargs: object) -> None:
                    nonlocal sessions
                    sessions += 1

                async def __aenter__(self) -> "ExpiredDeadlineClient":
                    if operation == "initialize":
                        self._expire(operation)
                    return self

                async def __aexit__(self, *args: object) -> None:
                    return None

                async def search_avia(self, arguments: dict) -> dict:
                    self._expire("search_avia")
                    raise AssertionError("unreachable")

                @staticmethod
                def _expire(active_operation: str) -> None:
                    TutuMcpClient(
                        url="https://mcp.tutu.ru/mcp",
                        deadline=time.monotonic() - 1,
                    ).remaining_timeout(active_operation)

            with (
                self.subTest(operation=operation),
                patch(
                    "flights_cli.providers.tutu_mcp.TutuMcpClient",
                    ExpiredDeadlineClient,
                ),
                self.assertRaises(CliError) as error,
            ):
                fetch_tutu_avia_search(
                    "SVX",
                    "AMS",
                    date(2026, 8, 15),
                    currency="RUB",
                    timeout=0.1,  # type: ignore[arg-type]
                )

            self.assertEqual(sessions, 1)
            self.assertEqual(error.exception.details["operation"], operation)
            self.assertEqual(
                error.exception.details["tool"],
                "search_avia" if operation == "search_avia" else None,
            )

    def test_close_timeout_is_reported_as_close_operation(self) -> None:
        class FakeClient:
            def __init__(self, **kwargs: object) -> None:
                pass

            async def __aenter__(self) -> "FakeClient":
                return self

            async def __aexit__(self, *args: object) -> None:
                error = TimeoutError("close timed out")
                error._tutu_operation = "close"  # type: ignore[attr-defined]
                raise error

            async def search_avia(self, arguments: dict) -> dict:
                return {"offers": [], "meta": {"has_more": False}}

        async def no_wait(delay: float) -> None:
            return None

        with (
            patch("flights_cli.providers.tutu_mcp.TutuMcpClient", FakeClient),
            patch("flights_cli.providers.tutu_mcp.asyncio.sleep", no_wait),
            self.assertRaises(CliError) as error,
        ):
            fetch_tutu_avia_search(
                "SVX",
                "AMS",
                date(2026, 8, 15),
                currency="RUB",
                timeout=5,
            )

        self.assertEqual(error.exception.details["operation"], "close")
        self.assertEqual(error.exception.details["attempts"], 2)

    def test_distinct_asyncio_timeout_error_is_explicitly_retryable(self) -> None:
        class SyntheticAsyncTimeout(Exception):
            pass

        with patch.object(
            tutu_mcp_module.asyncio,
            "TimeoutError",
            SyntheticAsyncTimeout,
        ):
            self.assertTrue(
                tutu_mcp_module._is_retryable_transport_failure(
                    SyntheticAsyncTimeout("async timeout")
                )
            )
            self.assertTrue(
                tutu_mcp_module._has_timeout_leaf(
                    SyntheticAsyncTimeout("async timeout")
                )
            )

    def test_nonretryable_tool_error_does_not_open_second_session(self) -> None:
        sessions = 0

        class FakeClient:
            def __init__(self, **kwargs: object) -> None:
                nonlocal sessions
                sessions += 1

            async def __aenter__(self) -> "FakeClient":
                return self

            async def __aexit__(self, *args: object) -> None:
                return None

            async def search_avia(self, arguments: dict) -> dict:
                raise CliError("bad tool arguments", error_type="upstream_error")

        with (
            patch("flights_cli.providers.tutu_mcp.TutuMcpClient", FakeClient),
            self.assertRaises(CliError),
        ):
            fetch_tutu_avia_search(
                "SVX",
                "AMS",
                date(2026, 8, 15),
                currency="RUB",
            )

        self.assertEqual(sessions, 1)

    def test_tool_error_survives_close_failure_without_retry(self) -> None:
        sessions = 0
        events: list[str] = []

        class FakeHttpClient:
            def __init__(self, **kwargs: object) -> None:
                self.timeout = kwargs["timeout"]

            async def __aenter__(self) -> "FakeHttpClient":
                events.append("http_enter")
                return self

            async def __aexit__(self, *args: object) -> None:
                events.append("http_exit")

        class ToolErrorSdkClient:
            protocol_version = "2025-11-25"
            server_info = None

            def __init__(self, server: object, **kwargs: object) -> None:
                nonlocal sessions
                sessions += 1

            async def __aenter__(self) -> "ToolErrorSdkClient":
                events.append("sdk_enter")
                return self

            async def __aexit__(self, *args: object) -> None:
                events.append("sdk_exit")
                raise httpx2.ReadError("close failed")

            async def call_tool(
                self,
                name: str,
                arguments: dict[str, object],
                **kwargs: object,
            ) -> CallToolResult:
                if name == "get_avia_instructions":
                    return CallToolResult(
                        content=[TextContent(type="text", text="# Playbook")]
                    )
                return CallToolResult(
                    isError=True,
                    content=[TextContent(type="text", text="bad request")],
                )

        with (
            patch(
                "flights_cli.providers.tutu_client.httpx2.AsyncClient",
                FakeHttpClient,
            ),
            patch(
                "flights_cli.providers.tutu_client.streamable_http_client",
                return_value=object(),
            ),
            patch(
                "flights_cli.providers.tutu_client.Client",
                ToolErrorSdkClient,
            ),
            self.assertRaises(CliError) as error,
        ):
            fetch_tutu_avia_search(
                "SVX",
                "AMS",
                date(2026, 8, 15),
                currency="RUB",
                timeout=5,
            )

        self.assertEqual(sessions, 1)
        self.assertEqual(error.exception.details["tool"], "search_avia")
        self.assertIn("bad request", str(error.exception))
        self.assertEqual(
            events,
            ["http_enter", "sdk_enter", "sdk_exit", "http_exit"],
        )

    def test_protocol_payload_failures_never_retry(self) -> None:
        failures = [
            CliError("empty playbook", error_type="upstream_error"),
            json.JSONDecodeError("malformed", "{", 1),
            CliError("bad search shape", error_type="upstream_error"),
        ]
        for failure in failures:
            sessions = 0

            class FakeClient:
                def __init__(self, **kwargs: object) -> None:
                    nonlocal sessions
                    sessions += 1

                async def __aenter__(self) -> "FakeClient":
                    if isinstance(failure, CliError) and "empty" in str(failure):
                        raise failure
                    return self

                async def __aexit__(self, *args: object) -> None:
                    return None

                async def search_avia(self, arguments: dict) -> dict:
                    raise failure

            with (
                self.subTest(failure=type(failure).__name__, message=str(failure)),
                patch("flights_cli.providers.tutu_mcp.TutuMcpClient", FakeClient),
                self.assertRaises(CliError),
            ):
                fetch_tutu_avia_search(
                    "SVX",
                    "AMS",
                    date(2026, 8, 15),
                    currency="RUB",
                )
            self.assertEqual(sessions, 1)

    def test_nested_transient_group_retries_but_application_mcp_error_does_not(
        self,
    ) -> None:
        class NestedError(Exception):
            def __init__(self, *exceptions: Exception) -> None:
                super().__init__("nested")
                self.exceptions = exceptions

        async def no_wait(delay: float) -> None:
            return None

        transient_sessions = 0

        class TransientClient:
            def __init__(self, **kwargs: object) -> None:
                nonlocal transient_sessions
                transient_sessions += 1

            async def __aenter__(self) -> "TransientClient":
                if transient_sessions == 1:
                    raise NestedError(
                        httpx2.ConnectError("offline"),
                        NestedError(MCPError(CONNECTION_CLOSED, "connection closed")),
                    )
                return self

            async def __aexit__(self, *args: object) -> None:
                return None

            async def search_avia(self, arguments: dict) -> dict:
                return {"offers": [], "meta": {"has_more": False}}

        with (
            patch("flights_cli.providers.tutu_mcp.TutuMcpClient", TransientClient),
            patch("flights_cli.providers.tutu_mcp.asyncio.sleep", no_wait),
        ):
            fetch_tutu_avia_search(
                "SVX",
                "AMS",
                date(2026, 8, 15),
                currency="RUB",
            )
        self.assertEqual(transient_sessions, 2)

        application_sessions = 0

        class ApplicationErrorClient:
            def __init__(self, **kwargs: object) -> None:
                nonlocal application_sessions
                application_sessions += 1

            async def __aenter__(self) -> "ApplicationErrorClient":
                raise MCPError(INVALID_PARAMS, "invalid params")

            async def __aexit__(self, *args: object) -> None:
                return None

        with (
            patch(
                "flights_cli.providers.tutu_mcp.TutuMcpClient",
                ApplicationErrorClient,
            ),
            self.assertRaises(CliError),
        ):
            fetch_tutu_avia_search(
                "SVX",
                "AMS",
                date(2026, 8, 15),
                currency="RUB",
            )
        self.assertEqual(application_sessions, 1)

    def test_parallel_sync_calls_use_independent_event_loops_and_sessions(self) -> None:
        barrier = threading.Barrier(2)
        loop_ids: list[int] = []
        sessions: list[object] = []
        lock = threading.Lock()

        class FakeClient:
            def __init__(self, **kwargs: object) -> None:
                with lock:
                    sessions.append(self)

            async def __aenter__(self) -> "FakeClient":
                with lock:
                    loop_ids.append(id(asyncio.get_running_loop()))
                barrier.wait(timeout=5)
                return self

            async def __aexit__(self, *args: object) -> None:
                return None

            async def search_avia(self, arguments: dict) -> dict:
                return {"offers": [], "meta": {"has_more": False}}

        def run_search() -> dict:
            return fetch_tutu_avia_search(
                "SVX",
                "AMS",
                date(2026, 8, 15),
                currency="RUB",
            )

        with patch("flights_cli.providers.tutu_mcp.TutuMcpClient", FakeClient):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(lambda _: run_search(), range(2)))

        self.assertEqual(len(results), 2)
        self.assertEqual(len(sessions), 2)
        self.assertEqual(len(set(loop_ids)), 2)


class TutuMcpSyncContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_provider_rejects_active_event_loop_before_coroutine(
        self,
    ) -> None:
        with self.assertRaises(CliError) as error:
            fetch_tutu_avia_search(
                "SVX",
                "AMS",
                date(2026, 8, 15),
                currency="RUB",
            )

        self.assertEqual(error.exception.error_type, "sync_contract_error")
        self.assertIn("active event loop", str(error.exception))

    async def test_parent_cancel_never_reaches_retry_classifier(self) -> None:
        class CleanupError(Exception):
            def __init__(self) -> None:
                super().__init__("cleanup failed")
                self.exceptions = (httpx2.ReadError("transport cleanup failed"),)

        for operation in ("initialize", "search_avia"):
            started = asyncio.Event()
            sessions = 0
            cleanup_attempts = 0

            class CancelledClient:
                def __init__(self, **kwargs: object) -> None:
                    nonlocal sessions
                    sessions += 1

                async def __aenter__(self) -> "CancelledClient":
                    nonlocal cleanup_attempts
                    if sessions > 1:
                        raise CliError(
                            "caller cancellation reached retry",
                            error_type="upstream_error",
                        )
                    if operation == "initialize":
                        started.set()
                        try:
                            await asyncio.Event().wait()
                        except BaseException:
                            cleanup_attempts += 1
                            raise CleanupError from None
                    return self

                async def __aexit__(self, *args: object) -> None:
                    nonlocal cleanup_attempts
                    cleanup_attempts += 1
                    raise CleanupError

                async def search_avia(self, arguments: dict) -> dict:
                    started.set()
                    await asyncio.Event().wait()
                    raise AssertionError("unreachable")

            with (
                self.subTest(operation=operation),
                patch(
                    "flights_cli.providers.tutu_mcp.TutuMcpClient",
                    CancelledClient,
                ),
            ):
                task = asyncio.create_task(
                    tutu_mcp_module._fetch_tutu_avia_search_async(
                        "SVX",
                        "AMS",
                        date(2026, 8, 15),
                        currency="RUB",
                        only_carriers=None,
                        direct_only=False,
                        limit=20,
                        timeout=5,
                        mcp_url="https://mcp.tutu.ru/mcp",
                        store=None,
                        return_date=None,
                        origin_airports=None,
                        destination_airports=None,
                        deadline=time.monotonic() + 5,
                    )
                )
                await started.wait()
                task.cancel()
                with self.assertRaises(asyncio.CancelledError) as error:
                    await task

            self.assertIsNone(getattr(error.exception, "_tutu_operation", None))
            self.assertTrue(task.cancelled())
            self.assertEqual(sessions, 1)
            self.assertEqual(cleanup_attempts, 1)

    async def test_repeated_parent_cancel_drains_attempt_without_task_leak(
        self,
    ) -> None:
        cleanup_started = asyncio.Event()
        cleanup_release = asyncio.Event()
        cleanup_finished = asyncio.Event()
        loop_errors: list[dict[str, object]] = []

        class CleanupError(Exception):
            def __init__(self) -> None:
                super().__init__("cleanup failed")
                self.exceptions = (httpx2.ReadError("transport cleanup failed"),)

        class CancelledClient:
            def __init__(self, **kwargs: object) -> None:
                pass

            async def __aenter__(self) -> "CancelledClient":
                return self

            async def __aexit__(self, *args: object) -> None:
                cleanup_started.set()
                try:
                    await cleanup_release.wait()
                finally:
                    cleanup_finished.set()
                raise CleanupError

            async def search_avia(self, arguments: dict) -> dict:
                await asyncio.Event().wait()
                raise AssertionError("unreachable")

        loop = asyncio.get_running_loop()
        previous_handler = loop.get_exception_handler()
        loop.set_exception_handler(lambda _loop, context: loop_errors.append(context))
        try:
            with patch(
                "flights_cli.providers.tutu_mcp.TutuMcpClient",
                CancelledClient,
            ):
                task = asyncio.create_task(
                    tutu_mcp_module._fetch_tutu_avia_search_async(
                        "SVX",
                        "AMS",
                        date(2026, 8, 15),
                        currency="RUB",
                        only_carriers=None,
                        direct_only=False,
                        limit=20,
                        timeout=5,
                        mcp_url="https://mcp.tutu.ru/mcp",
                        store=None,
                        return_date=None,
                        origin_airports=None,
                        destination_airports=None,
                        deadline=time.monotonic() + 5,
                    )
                )
                await asyncio.sleep(0)
                task.cancel()
                await cleanup_started.wait()
                task.cancel()
                await asyncio.sleep(0)
                parent_finished_before_cleanup = task.done()
                cleanup_release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                await asyncio.wait_for(cleanup_finished.wait(), timeout=1)
                await asyncio.sleep(0)
                gc.collect()
                await asyncio.sleep(0)
        finally:
            cleanup_release.set()
            loop.set_exception_handler(previous_handler)

        self.assertFalse(parent_finished_before_cleanup)
        self.assertEqual(loop_errors, [])

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

    def test_parser_rejects_cross_airport_connection_via_connection_policy(
        self,
    ) -> None:
        store = store_with_tutu_catalog(self)
        raw = {
            "offers": [
                tutu_offer(
                    "cross-airport",
                    [
                        [
                            tutu_segment("SVX", "IST", "100"),
                            tutu_segment("SAW", "AMS", "101"),
                        ]
                    ],
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

        self.assertEqual(result["offer_count"], 0)
        self.assertEqual(result["skipped"]["airport_change"], 1)

    def test_parser_rejects_missing_and_reversed_segment_times(self) -> None:
        store = store_with_tutu_catalog(self)
        raw = {
            "offers": [
                tutu_offer(
                    "missing-departure",
                    [[tutu_segment("SVX", "AMS", "100", depart="")]],
                ),
                tutu_offer(
                    "missing-arrival",
                    [[tutu_segment("SVX", "AMS", "101", arrive="")]],
                ),
                tutu_offer(
                    "reversed",
                    [
                        [
                            tutu_segment(
                                "SVX",
                                "AMS",
                                "102",
                                depart="2026-08-15T10:00:00+05:00",
                                arrive="2026-08-15T09:00:00+05:00",
                            )
                        ]
                    ],
                ),
                tutu_offer("valid", [[tutu_segment("SVX", "AMS", "103")]]),
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

        self.assertEqual([offer["id"] for offer in result["offers"]], ["valid"])
        self.assertEqual(result["skipped"]["missing_segment_time"], 2)
        self.assertEqual(result["skipped"]["segment_arrival_before_departure"], 1)

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
        self.assertEqual(result.query["return_date"], "2026-08-22")
        self.assertEqual(result.query["origin_airports"], ["SVX"])
        self.assertEqual(result.query["destination_airports"], ["AER"])


if __name__ == "__main__":
    unittest.main()
