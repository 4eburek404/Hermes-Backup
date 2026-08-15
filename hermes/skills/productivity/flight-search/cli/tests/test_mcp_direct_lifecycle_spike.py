from __future__ import annotations

import asyncio
import time
import unittest
from contextlib import contextmanager
from datetime import date, timedelta
from importlib.metadata import version
from typing import Any, Iterator
from unittest.mock import patch

import httpx2
import pytest
try:
    from builtins import ExceptionGroup
except ImportError:  # pragma: no cover - Python 3.10 compatibility
    from exceptiongroup import ExceptionGroup

from mcp import Client as OfficialClient
from mcp.client._memory import InMemoryTransport
from mcp.server.mcpserver import MCPServer
from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_PARAMS

from flights_cli.errors import CliError
from flights_cli.providers.tutu_client import TutuMcpClient
from flights_cli.providers.tutu_mcp import _fetch_tutu_avia_search_async


class TrackingTransport:
    def __init__(
        self,
        server: MCPServer[Any],
        *,
        close_started: asyncio.Event | None = None,
        block_close: bool = False,
    ) -> None:
        self._inner = InMemoryTransport(server)
        self._close_started = close_started
        self._block_close = block_close
        self.entered = False
        self.closed = False

    async def __aenter__(self):  # type: ignore[no-untyped-def]
        streams = await self._inner.__aenter__()
        self.entered = True
        return streams

    async def __aexit__(self, *args: object) -> None:
        if self._close_started is not None:
            self._close_started.set()
        try:
            if self._block_close:
                await asyncio.Event().wait()
        finally:
            try:
                await self._inner.__aexit__(*args)  # type: ignore[arg-type]
            finally:
                self.closed = True


class BlockingInitializeTransport:
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.closed = False

    async def __aenter__(self):  # type: ignore[no-untyped-def]
        self.entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.closed = True

    async def __aexit__(self, *args: object) -> None:
        self.closed = True


class FailingTransport:
    def __init__(self, failure: Exception) -> None:
        self.failure = failure
        self.entered = 0

    async def __aenter__(self):  # type: ignore[no-untyped-def]
        self.entered += 1
        raise self.failure

    async def __aexit__(self, *args: object) -> None:
        return None


def tutu_server(
    *,
    playbook: object = "# Tutu playbook",
    search_started: asyncio.Event | None = None,
    block_search: bool = False,
) -> MCPServer[Any]:
    server = MCPServer("tutu-direct-lifecycle")

    @server.tool(name="get_avia_instructions")
    async def get_avia_instructions() -> Any:
        return playbook

    @server.tool(name="search_avia")
    async def search_avia(
        origin: str = "SVX",
        destination: str = "AMS",
        departure_date: str = "2026-08-15",
        adults: int = 1,
        view: str = "compact",
        sort: str = "departure_asc",
        page_size: int = 30,
        page: int | None = None,
    ) -> dict[str, object]:
        del destination, departure_date, adults, view, sort, page_size, page
        if search_started is not None:
            search_started.set()
        if block_search:
            await asyncio.Event().wait()
        return {"offers": [], "meta": {"has_more": False}, "origin": origin}

    return server


@contextmanager
def production_clients(transports: list[Any]) -> Iterator[None]:
    pending = iter(transports)

    def build_client(server: object, **kwargs: object) -> OfficialClient:
        if server != "https://mcp.tutu.ru/mcp":
            raise AssertionError(f"unexpected MCP URL: {server!r}")
        return OfficialClient(next(pending), **kwargs)

    with patch("flights_cli.providers.tutu_client.Client", side_effect=build_client):
        yield


async def production_client_search(
    transport: Any,
    *,
    timeout: float = 5.0,
) -> tuple[TutuMcpClient, dict[str, Any]]:
    client = TutuMcpClient(
        url="https://mcp.tutu.ru/mcp",
        deadline=time.monotonic() + timeout,
    )
    with production_clients([transport]):
        async with client:
            result = await client.search_avia({"origin": "SVX"})
    return client, result


async def production_provider_search(
    transports: list[Any],
    *,
    timeout: float = 5.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    with production_clients(transports):
        return await _fetch_tutu_avia_search_async(
            "SVX",
            "AMS",
            date(2026, 8, 15),
            currency="RUB",
            only_carriers=None,
            direct_only=False,
            limit=20,
            timeout=timeout,
            mcp_url="https://mcp.tutu.ru/mcp",
            store=None,
            return_date=None,
            origin_airports=None,
            destination_airports=None,
            deadline=deadline,
        )


class DirectMcpLifecycleSpikeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        current = asyncio.current_task()
        self._baseline_tasks = {
            task for task in asyncio.all_tasks() if task is not current
        }

    async def asyncTearDown(self) -> None:
        current = asyncio.current_task()
        leaked: set[asyncio.Task[Any]] = set()
        for _ in range(20):
            leaked = {
                task
                for task in asyncio.all_tasks()
                if task is not current
                and task not in self._baseline_tasks
                and not task.done()
            }
            if not leaked:
                break
            await asyncio.sleep(0)
        self.assertEqual(
            [(task.get_name(), repr(task.get_coro())) for task in leaked],
            [],
        )

    async def test_pinned_sdk_normal_initialize_playbook_search_close(self) -> None:
        self.assertEqual(version("mcp"), "2.0.0")
        transport = TrackingTransport(tutu_server())

        client, result = await production_client_search(transport)

        self.assertEqual(result["offers"], [])
        self.assertEqual(client.playbook, "# Tutu playbook")
        self.assertIsNone(client.protocol_version)
        self.assertIsNone(client.server_info)
        self.assertTrue(transport.entered)
        self.assertTrue(transport.closed)

    @pytest.mark.live_provider
    async def test_live_tutu_initialize_playbook_search_close_has_no_leaks(
        self,
    ) -> None:
        current = asyncio.current_task()
        baseline = {
            task
            for task in asyncio.all_tasks()
            if task is not current and not task.done()
        }
        client = TutuMcpClient(
            url=None,
            deadline=time.monotonic() + 60,
        )
        departure_date = date.today() + timedelta(days=45)

        async with client:
            self.assertIsInstance(client.playbook, str)
            self.assertTrue(client.playbook.strip())
            result = await client.search_avia(
                {
                    "origin": "Москва",
                    "destination": "Санкт-Петербург",
                    "departure_date": departure_date.isoformat(),
                    "adults": 1,
                    "view": "compact",
                    "sort": "departure_asc",
                    "page_size": 1,
                }
            )

        self.assertIsInstance(result, dict)
        self.assertIsNone(client._client)
        self.assertIsNone(client._session_context)
        self.assertIsNone(client.protocol_version)
        self.assertIsNone(client.server_info)

        leaked: set[asyncio.Task[Any]] = set()
        for _ in range(20):
            leaked = {
                task
                for task in asyncio.all_tasks()
                if task is not current
                and task not in baseline
                and not task.done()
            }
            if not leaked:
                break
            await asyncio.sleep(0)
        self.assertEqual(
            [(task.get_name(), repr(task.get_coro())) for task in leaked],
            [],
        )

    async def test_empty_and_invalid_playbook_preserve_cli_error(self) -> None:
        for playbook in ("   ", {"not": "text"}):
            transport = TrackingTransport(tutu_server(playbook=playbook))
            with self.subTest(playbook=playbook), self.assertRaises(
                CliError
            ) as error:
                await production_client_search(transport)

            self.assertEqual(error.exception.error_type, "upstream_error")
            self.assertEqual(
                error.exception.details,
                {"provider": "tutu", "tool": "get_avia_instructions"},
            )
            self.assertTrue(transport.closed)

    async def test_initialize_timeout_preserves_boundary_error_and_closes(self) -> None:
        transport = BlockingInitializeTransport()

        with self.assertRaises(CliError) as error:
            await production_provider_search([transport], timeout=0.02)

        self.assertEqual(error.exception.error_type, "timeout")
        self.assertEqual(error.exception.details["operation"], "initialize")
        self.assertEqual(error.exception.details["attempts"], 1)
        self.assertEqual(error.exception.details["terminal_error_types"], ["TimeoutError"])
        self.assertTrue(transport.entered.is_set())
        self.assertTrue(transport.closed)

    async def test_call_timeout_preserves_boundary_error_and_closes(self) -> None:
        started = asyncio.Event()
        transport = TrackingTransport(
            tutu_server(search_started=started, block_search=True)
        )

        with self.assertRaises(CliError) as error:
            await production_provider_search([transport], timeout=1.0)

        self.assertTrue(started.is_set())
        self.assertEqual(error.exception.error_type, "timeout")
        self.assertEqual(error.exception.details["operation"], "search_avia")
        self.assertEqual(error.exception.details["tool"], "search_avia")
        self.assertTrue(transport.closed)

    async def test_close_timeout_preserves_boundary_error_and_closes(self) -> None:
        close_started = asyncio.Event()
        transport = TrackingTransport(
            tutu_server(),
            close_started=close_started,
            block_close=True,
        )

        with self.assertRaises(CliError) as error:
            await production_provider_search([transport], timeout=0.1)

        self.assertTrue(close_started.is_set())
        self.assertEqual(error.exception.error_type, "timeout")
        self.assertEqual(error.exception.details["operation"], "close")
        self.assertIsNone(error.exception.details["tool"])
        self.assertTrue(transport.closed)

    async def test_external_cancellation_during_call_closes_without_remapping(
        self,
    ) -> None:
        started = asyncio.Event()
        transport = TrackingTransport(
            tutu_server(search_started=started, block_search=True)
        )
        with production_clients([transport]):
            task = asyncio.create_task(
                production_client_search_in_current_patch(started)
            )
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError) as error:
                await task

        self.assertIsNone(getattr(error.exception, "_tutu_operation", None))
        self.assertTrue(task.cancelled())
        self.assertTrue(transport.closed)

    async def test_nested_transport_failures_preserve_leaf_error_details(self) -> None:
        def nested_failure() -> ExceptionGroup:
            return ExceptionGroup(
                "transport task group",
                [ExceptionGroup("stream failure", [httpx2.ConnectError("offline")])],
            )

        transports = [
            FailingTransport(nested_failure()),
            FailingTransport(nested_failure()),
        ]

        with self.assertRaises(CliError) as error:
            await production_provider_search(transports)

        self.assertEqual(error.exception.error_type, "upstream_error")
        self.assertEqual(error.exception.details["operation"], "initialize")
        self.assertEqual(error.exception.details["attempts"], 2)
        self.assertEqual(error.exception.details["terminal_error_types"], ["ConnectError"])
        self.assertEqual([transport.entered for transport in transports], [1, 1])

    async def test_first_nested_transport_failure_then_success_retries_once(
        self,
    ) -> None:
        failure = FailingTransport(
            ExceptionGroup(
                "transport task group",
                [httpx2.ReadError("connection dropped")],
            )
        )
        success = TrackingTransport(tutu_server())

        result = await production_provider_search([failure, success])

        self.assertEqual(result["offer_count"], 0)
        self.assertEqual(failure.entered, 1)
        self.assertTrue(success.closed)

    async def test_terminal_nonretryable_mcp_error_does_not_retry(self) -> None:
        terminal = FailingTransport(MCPError(INVALID_PARAMS, "bad request"))
        unused = TrackingTransport(tutu_server())

        with self.assertRaises(CliError) as error:
            await production_provider_search([terminal, unused])

        self.assertEqual(error.exception.error_type, "upstream_error")
        self.assertEqual(error.exception.details["operation"], "initialize")
        self.assertEqual(error.exception.details["attempts"], 1)
        self.assertEqual(error.exception.details["terminal_error_types"], ["MCPError"])
        self.assertEqual(terminal.entered, 1)
        self.assertFalse(unused.entered)


async def production_client_search_in_current_patch(
    started: asyncio.Event,
) -> dict[str, Any]:
    del started
    client = TutuMcpClient(
        url="https://mcp.tutu.ru/mcp",
        deadline=time.monotonic() + 5,
    )
    async with client:
        return await client.search_avia({"origin": "SVX"})


if __name__ == "__main__":
    unittest.main()
