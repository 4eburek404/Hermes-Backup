from __future__ import annotations

import asyncio
import time
import unittest
from importlib.metadata import version
from typing import Any

import anyio
import httpx2
try:
    from builtins import ExceptionGroup
except ImportError:  # pragma: no cover - Python 3.10 compatibility
    from exceptiongroup import ExceptionGroup

from mcp import Client
from mcp.client._memory import InMemoryTransport
from mcp.server.mcpserver import MCPServer
from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_PARAMS, Implementation

from flights_cli import __version__
from flights_cli.errors import CliError
from flights_cli.providers.tutu_client import _extract_tool_payload
from flights_cli.providers.tutu_mcp import (
    _exception_leaves,
    _final_tutu_error,
    _has_timeout_leaf,
    _is_retryable_transport_failure,
)


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
        self.closed = True

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
    server = MCPServer("tutu-direct-lifecycle-spike")

    @server.tool(name="get_avia_instructions")
    async def get_avia_instructions() -> Any:
        return playbook

    @server.tool(name="search_avia")
    async def search_avia(origin: str = "SVX") -> dict[str, object]:
        if search_started is not None:
            search_started.set()
        if block_search:
            await asyncio.Event().wait()
        return {"offers": [], "origin": origin}

    return server


async def direct_sdk_search(
    transport: Any,
    *,
    deadline: float,
) -> dict[str, Any]:
    operation = "initialize"
    remaining = max(0.0, deadline - time.monotonic())
    try:
        with anyio.fail_after(remaining):
            async with Client(
                transport,
                mode="legacy",
                client_info=Implementation(
                    name="hermes-flights-cli",
                    version=__version__,
                ),
                read_timeout_seconds=remaining,
                cache=None,
            ) as client:
                operation = "get_avia_instructions"
                playbook = _extract_tool_payload(
                    await client.call_tool(
                        "get_avia_instructions",
                        {},
                        read_timeout_seconds=max(
                            0.0, deadline - time.monotonic()
                        ),
                    ),
                    "get_avia_instructions",
                )
                if not isinstance(playbook, str) or not playbook.strip():
                    raise CliError(
                        "Tutu MCP get_avia_instructions returned an empty or unsupported playbook",
                        error_type="upstream_error",
                        details={
                            "provider": "tutu",
                            "tool": "get_avia_instructions",
                        },
                    )

                operation = "search_avia"
                payload = _extract_tool_payload(
                    await client.call_tool(
                        "search_avia",
                        {"origin": "SVX"},
                        read_timeout_seconds=max(
                            0.0, deadline - time.monotonic()
                        ),
                    ),
                    "search_avia",
                )
                if not isinstance(payload, dict):
                    raise CliError(
                        "Tutu MCP search_avia returned a non-object payload",
                        error_type="upstream_error",
                        details={
                            "provider": "tutu",
                            "tool": "search_avia",
                            "payload_type": type(payload).__name__,
                        },
                    )
                operation = "close"
                return payload
    except asyncio.CancelledError:
        raise
    except CliError:
        raise
    except Exception as exc:
        leaves = _exception_leaves(exc)
        if len(leaves) == 1 and isinstance(leaves[0], CliError):
            raise leaves[0] from exc
        setattr(exc, "_tutu_operation", operation)
        raise


async def direct_provider_search(
    transports: list[Any],
    *,
    timeout: float = 5.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    for attempt, transport in enumerate(transports, start=1):
        try:
            return await direct_sdk_search(transport, deadline=deadline)
        except CliError:
            raise
        except Exception as exc:
            operation = str(getattr(exc, "_tutu_operation", "mcp_session"))
            timed_out = _has_timeout_leaf(exc)
            if (
                not _is_retryable_transport_failure(exc)
                or attempt == len(transports)
                or deadline <= time.monotonic()
            ):
                raise _final_tutu_error(
                    exc,
                    operation=operation,
                    attempts=attempt,
                    timeout=timeout,
                    timed_out=timed_out,
                ) from exc
    raise AssertionError("at least one direct MCP transport is required")


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

        result = await direct_provider_search([transport])

        self.assertEqual(result, {"offers": [], "origin": "SVX"})
        self.assertTrue(transport.entered)
        self.assertTrue(transport.closed)

    async def test_empty_and_invalid_playbook_preserve_cli_error(self) -> None:
        for playbook in ("   ", {"not": "text"}):
            transport = TrackingTransport(tutu_server(playbook=playbook))
            with self.subTest(playbook=playbook), self.assertRaises(
                CliError
            ) as error:
                await direct_provider_search([transport])

            self.assertEqual(error.exception.error_type, "upstream_error")
            self.assertEqual(
                error.exception.details,
                {"provider": "tutu", "tool": "get_avia_instructions"},
            )
            self.assertTrue(transport.closed)

    async def test_raw_sdk_context_wraps_application_error_on_close(self) -> None:
        transport = TrackingTransport(tutu_server())
        original = CliError(
            "invalid playbook",
            error_type="upstream_error",
            details={"provider": "tutu", "tool": "get_avia_instructions"},
        )

        with self.assertRaises(ExceptionGroup) as error:
            async with Client(transport, mode="legacy", cache=None):
                raise original

        self.assertEqual(_exception_leaves(error.exception), [original])
        self.assertTrue(transport.closed)

    async def test_initialize_timeout_preserves_boundary_error_and_closes(self) -> None:
        transport = BlockingInitializeTransport()

        with self.assertRaises(CliError) as error:
            await direct_provider_search([transport], timeout=0.02)

        self.assertEqual(error.exception.error_type, "timeout")
        self.assertEqual(
            error.exception.details,
            {
                "provider": "tutu",
                "operation": "initialize",
                "tool": None,
                "attempts": 1,
                "deadline_seconds": 0.02,
                "terminal_error_types": ["TimeoutError"],
            },
        )
        self.assertTrue(transport.entered.is_set())
        self.assertTrue(transport.closed)

    async def test_call_timeout_preserves_boundary_error_and_closes(self) -> None:
        started = asyncio.Event()
        transport = TrackingTransport(
            tutu_server(search_started=started, block_search=True)
        )

        with self.assertRaises(CliError) as error:
            await direct_provider_search([transport], timeout=1.0)

        self.assertTrue(started.is_set())
        self.assertEqual(error.exception.error_type, "timeout")
        self.assertEqual(
            error.exception.details,
            {
                "provider": "tutu",
                "operation": "search_avia",
                "tool": "search_avia",
                "attempts": 1,
                "deadline_seconds": 1.0,
                "terminal_error_types": ["TimeoutError"],
            },
        )
        self.assertTrue(transport.closed)

    async def test_close_timeout_preserves_boundary_error_and_closes(self) -> None:
        close_started = asyncio.Event()
        transport = TrackingTransport(
            tutu_server(),
            close_started=close_started,
            block_close=True,
        )

        with self.assertRaises(CliError) as error:
            await direct_provider_search([transport], timeout=0.1)

        self.assertTrue(close_started.is_set())
        self.assertEqual(error.exception.error_type, "timeout")
        self.assertEqual(
            error.exception.details,
            {
                "provider": "tutu",
                "operation": "close",
                "tool": None,
                "attempts": 1,
                "deadline_seconds": 0.1,
                "terminal_error_types": ["TimeoutError"],
            },
        )
        self.assertTrue(transport.closed)

    async def test_external_cancellation_during_call_closes_without_remapping(
        self,
    ) -> None:
        started = asyncio.Event()
        transport = TrackingTransport(
            tutu_server(search_started=started, block_search=True)
        )
        task = asyncio.create_task(direct_provider_search([transport]))
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
                [
                    ExceptionGroup(
                        "stream failure",
                        [httpx2.ConnectError("offline")],
                    )
                ],
            )

        transports = [
            FailingTransport(nested_failure()),
            FailingTransport(nested_failure()),
        ]

        with self.assertRaises(CliError) as error:
            await direct_provider_search(transports)

        self.assertEqual(error.exception.error_type, "upstream_error")
        self.assertEqual(
            error.exception.details,
            {
                "provider": "tutu",
                "operation": "initialize",
                "tool": None,
                "attempts": 2,
                "deadline_seconds": 5.0,
                "terminal_error_types": ["ConnectError"],
            },
        )
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

        result = await direct_provider_search([failure, success])

        self.assertEqual(result["offers"], [])
        self.assertEqual(failure.entered, 1)
        self.assertTrue(success.closed)

    async def test_terminal_nonretryable_mcp_error_does_not_retry(self) -> None:
        terminal = FailingTransport(MCPError(INVALID_PARAMS, "bad request"))
        unused = TrackingTransport(tutu_server())

        with self.assertRaises(CliError) as error:
            await direct_provider_search([terminal, unused])

        self.assertEqual(error.exception.error_type, "upstream_error")
        self.assertEqual(
            error.exception.details,
            {
                "provider": "tutu",
                "operation": "initialize",
                "tool": None,
                "attempts": 1,
                "deadline_seconds": 5.0,
                "terminal_error_types": ["MCPError"],
            },
        )
        self.assertEqual(terminal.entered, 1)
        self.assertFalse(unused.entered)


if __name__ == "__main__":
    unittest.main()
