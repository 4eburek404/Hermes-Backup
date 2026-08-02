from __future__ import annotations

import asyncio
import json
import time
import unittest
from unittest.mock import patch

import anyio
import httpx2
from mcp.types import CallToolResult, TextContent

from flights_cli.errors import CliError
from flights_cli.providers.tutu_client import (
    TutuMcpClient,
    _extract_tool_payload,
    normalize_tutu_mcp_url,
)


class TutuMcpClientPayloadTests(unittest.TestCase):
    def test_normalize_url_accepts_http_and_removes_only_mcp_trailing_slash(
        self,
    ) -> None:
        self.assertEqual(
            normalize_tutu_mcp_url("https://mcp.tutu.ru/mcp/"),
            "https://mcp.tutu.ru/mcp",
        )
        self.assertEqual(
            normalize_tutu_mcp_url("http://127.0.0.1:8765/custom/"),
            "http://127.0.0.1:8765/custom/",
        )

    def test_normalize_url_rejects_unsupported_or_hostless_urls(self) -> None:
        for value in ("ftp://mcp.tutu.ru/mcp", "https:///mcp"):
            with self.subTest(value=value), self.assertRaises(CliError) as error:
                normalize_tutu_mcp_url(value)
            self.assertEqual(error.exception.error_type, "validation_error")

    def test_extract_prefers_structured_content_and_unwraps_result(self) -> None:
        result = CallToolResult(
            content=[TextContent(type="text", text='{"ignored": true}')],
            structuredContent={"result": {"offers": []}},
        )

        self.assertEqual(_extract_tool_payload(result, "search_avia"), {"offers": []})

    def test_extract_decodes_typed_text_and_recursive_tutu_wrapper(self) -> None:
        wrapped = json.dumps({"result": json.dumps({"result": '{"offers": []}'})})
        result = CallToolResult(
            content=[TextContent(type="text", text=wrapped)],
        )

        self.assertEqual(_extract_tool_payload(result, "search_avia"), {"offers": []})

    def test_extract_preserves_non_json_playbook_text(self) -> None:
        result = CallToolResult(
            content=[TextContent(type="text", text="# Avia\nUse search_avia")],
        )

        self.assertEqual(
            _extract_tool_payload(result, "get_avia_instructions"),
            "# Avia\nUse search_avia",
        )

    def test_extract_tool_error_is_non_retryable_cli_error(self) -> None:
        result = CallToolResult(
            isError=True,
            content=[TextContent(type="text", text="bad request")],
        )

        with self.assertRaises(CliError) as error:
            _extract_tool_payload(result, "search_avia")

        self.assertEqual(error.exception.error_type, "upstream_error")
        self.assertIn("bad request", str(error.exception))


class TutuMcpClientLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_internal_task_group_cancel_surfaces_transport_root_cause(
        self,
    ) -> None:
        events: list[str] = []

        class FakeHttpClient:
            def __init__(self, **kwargs: object) -> None:
                self.timeout = kwargs["timeout"]

            async def __aenter__(self) -> "FakeHttpClient":
                events.append("http_enter")
                return self

            async def __aexit__(self, *args: object) -> None:
                events.append("http_exit")

        class FailingTaskGroupSdkClient:
            protocol_version = "2025-11-25"
            server_info = None

            def __init__(self, server: object, **kwargs: object) -> None:
                pass

            async def __aenter__(self) -> "FailingTaskGroupSdkClient":
                events.append("sdk_enter")
                self.task_group = anyio.create_task_group()
                await self.task_group.__aenter__()
                return self

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc: BaseException | None,
                traceback: object,
            ) -> object:
                events.append("sdk_exit")
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

                async def fail_post() -> None:
                    await anyio.sleep(0)
                    raise httpx2.ConnectTimeout("POST connect timed out")

                self.task_group.start_soon(fail_post)
                await anyio.sleep_forever()
                raise AssertionError("unreachable")

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
                FailingTaskGroupSdkClient,
            ),
            patch(
                "asyncio.current_task",
                return_value=object(),
            ),
            self.assertRaises(Exception) as error,
        ):
            async with TutuMcpClient(
                url="https://mcp.tutu.ru/mcp",
                deadline=time.monotonic() + 5,
            ) as client:
                await client.search_avia({})

        leaves = getattr(error.exception, "exceptions", (error.exception,))
        self.assertTrue(any(isinstance(leaf, httpx2.ConnectTimeout) for leaf in leaves))
        self.assertEqual(
            getattr(error.exception, "_tutu_operation", None),
            "search_avia",
        )
        self.assertEqual(
            events,
            ["http_enter", "sdk_enter", "sdk_exit", "http_exit"],
        )

    async def test_own_deadline_converts_with_nested_sdk_task_group(self) -> None:
        events: list[str] = []

        class FakeHttpClient:
            def __init__(self, **kwargs: object) -> None:
                self.timeout = kwargs["timeout"]

            async def __aenter__(self) -> "FakeHttpClient":
                events.append("http_enter")
                return self

            async def __aexit__(self, *args: object) -> None:
                events.append("http_exit")

        class SlowTaskGroupSdkClient:
            protocol_version = "2025-11-25"
            server_info = None

            def __init__(self, server: object, **kwargs: object) -> None:
                pass

            async def __aenter__(self) -> "SlowTaskGroupSdkClient":
                events.append("sdk_enter")
                self.task_group = anyio.create_task_group()
                await self.task_group.__aenter__()
                return self

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc: BaseException | None,
                traceback: object,
            ) -> object:
                events.append("sdk_exit")
                self.task_group.cancel_scope.cancel()
                return await self.task_group.__aexit__(exc_type, exc, traceback)

            async def call_tool(
                self,
                name: str,
                arguments: dict[str, object],
                **kwargs: object,
            ) -> CallToolResult:
                if name == "search_avia":
                    await anyio.sleep_forever()
                return CallToolResult(
                    content=[TextContent(type="text", text="# Playbook")]
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
                SlowTaskGroupSdkClient,
            ),
            self.assertRaises(TimeoutError) as error,
        ):
            async with TutuMcpClient(
                url="https://mcp.tutu.ru/mcp",
                deadline=time.monotonic() + 0.03,
            ) as client:
                await client.search_avia({})

        self.assertEqual(
            getattr(error.exception, "_tutu_operation", None),
            "search_avia",
        )
        self.assertEqual(
            events,
            ["http_enter", "sdk_enter", "sdk_exit", "http_exit"],
        )

    async def test_expired_deadline_before_initialize_retains_operation(self) -> None:
        with (
            patch("flights_cli.providers.tutu_client.httpx2.AsyncClient") as http,
            self.assertRaises(TimeoutError) as error,
        ):
            await TutuMcpClient(
                url="https://mcp.tutu.ru/mcp",
                deadline=time.monotonic() - 1,
            ).__aenter__()

        http.assert_not_called()
        self.assertEqual(
            getattr(error.exception, "_tutu_operation", None),
            "initialize",
        )

    async def test_deadline_expiry_between_precheck_and_worker_is_reported(
        self,
    ) -> None:
        client = TutuMcpClient(
            url="https://mcp.tutu.ru/mcp",
            deadline=time.monotonic() + 5,
        )
        with (
            patch.object(
                client,
                "remaining_timeout",
                side_effect=[1.0, TimeoutError("deadline exhausted")],
            ),
            self.assertRaises(TimeoutError) as error,
        ):
            await asyncio.wait_for(client.__aenter__(), timeout=0.2)

        self.assertEqual(
            getattr(error.exception, "_tutu_operation", None),
            "initialize",
        )
        self.assertIsNone(client._session_task)

    async def test_expired_deadline_before_search_retains_tool_operation(self) -> None:
        class UnexpectedSdkClient:
            async def call_tool(self, *args: object, **kwargs: object) -> None:
                self.fail("search_avia must not call the SDK after deadline expiry")

        client = TutuMcpClient(
            url="https://mcp.tutu.ru/mcp",
            deadline=time.monotonic() - 1,
        )
        client._client = UnexpectedSdkClient()  # type: ignore[assignment]

        with self.assertRaises(TimeoutError) as error:
            await client.search_avia({})

        self.assertEqual(
            getattr(error.exception, "_tutu_operation", None),
            "search_avia",
        )

    async def test_cancel_during_initialize_survives_sdk_close_failure(self) -> None:
        events: list[str] = []
        initialize_started = asyncio.Event()

        class CleanupError(Exception):
            def __init__(self) -> None:
                super().__init__("cleanup failed")
                self.exceptions = (httpx2.ReadError("close failed"),)

        class FakeHttpClient:
            def __init__(self, **kwargs: object) -> None:
                self.timeout = kwargs["timeout"]

            async def __aenter__(self) -> "FakeHttpClient":
                events.append("http_enter")
                return self

            async def __aexit__(self, *args: object) -> None:
                events.append("http_exit")

        class CancelledSdkClient:
            protocol_version = "2025-11-25"
            server_info = None

            def __init__(self, server: object, **kwargs: object) -> None:
                pass

            async def __aenter__(self) -> "CancelledSdkClient":
                events.append("sdk_enter")
                initialize_started.set()
                await asyncio.Event().wait()
                return self

            async def __aexit__(self, *args: object) -> None:
                events.append("sdk_exit")
                raise CleanupError

        with (
            patch(
                "flights_cli.providers.tutu_client.httpx2.AsyncClient",
                FakeHttpClient,
            ),
            patch(
                "flights_cli.providers.tutu_client.streamable_http_client",
                return_value=object(),
            ),
            patch("flights_cli.providers.tutu_client.Client", CancelledSdkClient),
        ):
            task = asyncio.create_task(
                TutuMcpClient(
                    url="https://mcp.tutu.ru/mcp",
                    deadline=time.monotonic() + 5,
                ).__aenter__()
            )
            await initialize_started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError) as error:
                await task

        self.assertIsNone(getattr(error.exception, "_tutu_operation", None))
        self.assertTrue(task.cancelled())
        self.assertEqual(
            events,
            ["http_enter", "sdk_enter", "sdk_exit", "http_exit"],
        )

    async def test_cancel_during_search_survives_sdk_close_failure(self) -> None:
        events: list[str] = []
        search_started = asyncio.Event()

        class CleanupError(Exception):
            def __init__(self) -> None:
                super().__init__("cleanup failed")
                self.exceptions = (httpx2.ReadError("close failed"),)

        class FakeHttpClient:
            def __init__(self, **kwargs: object) -> None:
                self.timeout = kwargs["timeout"]

            async def __aenter__(self) -> "FakeHttpClient":
                events.append("http_enter")
                return self

            async def __aexit__(self, *args: object) -> None:
                events.append("http_exit")

        class CancelledSdkClient:
            protocol_version = "2025-11-25"
            server_info = None

            def __init__(self, server: object, **kwargs: object) -> None:
                pass

            async def __aenter__(self) -> "CancelledSdkClient":
                events.append("sdk_enter")
                return self

            async def __aexit__(self, *args: object) -> None:
                events.append("sdk_exit")
                raise CleanupError

            async def call_tool(
                self,
                name: str,
                arguments: dict[str, object],
                **kwargs: object,
            ) -> CallToolResult:
                if name == "search_avia":
                    search_started.set()
                    await asyncio.Event().wait()
                return CallToolResult(
                    content=[TextContent(type="text", text="# Playbook")]
                )

        async def run_search() -> None:
            async with TutuMcpClient(
                url="https://mcp.tutu.ru/mcp",
                deadline=time.monotonic() + 5,
            ) as client:
                await client.search_avia({})

        with (
            patch(
                "flights_cli.providers.tutu_client.httpx2.AsyncClient",
                FakeHttpClient,
            ),
            patch(
                "flights_cli.providers.tutu_client.streamable_http_client",
                return_value=object(),
            ),
            patch("flights_cli.providers.tutu_client.Client", CancelledSdkClient),
        ):
            task = asyncio.create_task(run_search())
            await search_started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError) as error:
                await task

        self.assertIsNone(getattr(error.exception, "_tutu_operation", None))
        self.assertTrue(task.cancelled())
        self.assertEqual(
            events,
            ["http_enter", "sdk_enter", "sdk_exit", "http_exit"],
        )

    async def test_worker_exit_between_precheck_and_enqueue_does_not_hang(
        self,
    ) -> None:
        worker_exit = asyncio.Event()
        transport_error = httpx2.ReadError("session worker failed")

        async def fail_worker() -> None:
            await worker_exit.wait()
            raise transport_error

        class ExitWorkerQueue:
            def put_nowait(self, item: object) -> None:
                del item
                worker_exit.set()

        client = TutuMcpClient(
            url="https://mcp.tutu.ru/mcp",
            deadline=time.monotonic() + 5,
        )
        worker = asyncio.create_task(fail_worker())
        client._session_task = worker
        client._command_queue = ExitWorkerQueue()  # type: ignore[assignment]

        with self.assertRaises(httpx2.ReadError) as error:
            await asyncio.wait_for(client.search_avia({}), timeout=0.2)

        self.assertIs(error.exception, transport_error)
        self.assertTrue(worker.done())

    async def test_caller_cancel_wins_when_response_completes_same_turn(self) -> None:
        cleanup_finished = asyncio.Event()

        async def session_worker() -> None:
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                cleanup_finished.set()

        class CompleteAndCancelQueue:
            def put_nowait(
                self,
                item: tuple[
                    str | None,
                    dict[str, object],
                    asyncio.Future[object],
                ],
            ) -> None:
                response = item[2]
                caller = asyncio.current_task()
                assert caller is not None

                def complete_and_cancel() -> None:
                    response.set_result({"offers": []})
                    caller.cancel()

                asyncio.get_running_loop().call_soon(complete_and_cancel)

        client = TutuMcpClient(
            url="https://mcp.tutu.ru/mcp",
            deadline=time.monotonic() + 5,
        )
        worker = asyncio.create_task(session_worker())
        client._session_task = worker
        client._command_queue = CompleteAndCancelQueue()  # type: ignore[assignment]
        caller = asyncio.create_task(client.search_avia({}))
        try:
            with self.assertRaises(asyncio.CancelledError):
                await caller
        finally:
            if not worker.done():
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)

        self.assertTrue(caller.cancelled())
        self.assertTrue(worker.done())
        self.assertTrue(cleanup_finished.is_set())

    async def test_close_failure_is_tagged_with_close_operation(self) -> None:
        class FakeHttpClient:
            timeout: object | None = None

        class FailingStack:
            async def __aexit__(self, *args: object) -> None:
                raise httpx2.ReadTimeout("close stalled")

        client = TutuMcpClient(
            url="https://mcp.tutu.ru/mcp",
            deadline=time.monotonic() + 5,
        )
        client._http_client = FakeHttpClient()  # type: ignore[assignment]

        with self.assertRaises(httpx2.ReadTimeout) as error:
            await client._close_stack(FailingStack())  # type: ignore[arg-type]

        self.assertEqual(
            getattr(error.exception, "_tutu_operation", None),
            "close",
        )

    async def test_complete_tool_call_is_bounded_by_absolute_deadline(self) -> None:
        events: list[str] = []

        class FakeHttpClient:
            def __init__(self, **kwargs: object) -> None:
                self.timeout = kwargs["timeout"]

            async def __aenter__(self) -> "FakeHttpClient":
                events.append("http_enter")
                return self

            async def __aexit__(self, *args: object) -> None:
                events.append("http_exit")

        class SlowSdkClient:
            protocol_version = "2025-11-25"
            server_info = None

            def __init__(self, server: object, **kwargs: object) -> None:
                pass

            async def __aenter__(self) -> "SlowSdkClient":
                events.append("sdk_enter")
                return self

            async def __aexit__(self, *args: object) -> None:
                events.append("sdk_exit")

            async def call_tool(
                self,
                name: str,
                arguments: dict[str, object],
                **kwargs: object,
            ) -> CallToolResult:
                if name == "search_avia":
                    await asyncio.sleep(0.1)
                    text = '{"offers": []}'
                else:
                    text = "# Playbook"
                return CallToolResult(content=[TextContent(type="text", text=text)])

        with (
            patch(
                "flights_cli.providers.tutu_client.httpx2.AsyncClient",
                FakeHttpClient,
            ),
            patch(
                "flights_cli.providers.tutu_client.streamable_http_client",
                return_value=object(),
            ),
            patch("flights_cli.providers.tutu_client.Client", SlowSdkClient),
        ):
            started = time.monotonic()
            with self.assertRaises(TimeoutError) as error:
                async with TutuMcpClient(
                    url="https://mcp.tutu.ru/mcp",
                    deadline=started + 0.03,
                ) as client:
                    await client.search_avia({})
            self.assertLess(time.monotonic() - started, 0.1)
        self.assertEqual(
            events,
            ["http_enter", "sdk_enter", "sdk_exit", "http_exit"],
        )
        self.assertEqual(
            getattr(error.exception, "_tutu_operation", None),
            "search_avia",
        )

    async def test_initialize_deadline_timeout_retains_operation(self) -> None:
        events: list[str] = []

        class FakeHttpClient:
            def __init__(self, **kwargs: object) -> None:
                self.timeout = kwargs["timeout"]

            async def __aenter__(self) -> "FakeHttpClient":
                events.append("http_enter")
                return self

            async def __aexit__(self, *args: object) -> None:
                events.append("http_exit")

        class SlowInitializeSdkClient:
            protocol_version = "2025-11-25"
            server_info = None

            def __init__(self, server: object, **kwargs: object) -> None:
                pass

            async def __aenter__(self) -> "SlowInitializeSdkClient":
                events.append("sdk_enter")
                await asyncio.sleep(0.1)
                return self

            async def __aexit__(self, *args: object) -> None:
                events.append("sdk_exit")

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
                SlowInitializeSdkClient,
            ),
        ):
            with self.assertRaises(TimeoutError) as error:
                await TutuMcpClient(
                    url="https://mcp.tutu.ru/mcp",
                    deadline=time.monotonic() + 0.03,
                ).__aenter__()

        self.assertEqual(
            events,
            ["http_enter", "sdk_enter", "sdk_exit", "http_exit"],
        )
        self.assertEqual(
            getattr(error.exception, "_tutu_operation", None),
            "initialize",
        )

    async def test_client_and_transport_close_are_bounded_by_deadline(self) -> None:
        class FakeHttpClient:
            def __init__(self, **kwargs: object) -> None:
                self.timeout = kwargs["timeout"]

            async def __aenter__(self) -> "FakeHttpClient":
                return self

            async def __aexit__(self, *args: object) -> None:
                return None

        class SlowCloseSdkClient:
            protocol_version = "2025-11-25"
            server_info = None

            def __init__(self, server: object, **kwargs: object) -> None:
                pass

            async def __aenter__(self) -> "SlowCloseSdkClient":
                return self

            async def __aexit__(self, *args: object) -> None:
                await asyncio.sleep(0.12)

            async def call_tool(
                self,
                name: str,
                arguments: dict[str, object],
                **kwargs: object,
            ) -> CallToolResult:
                return CallToolResult(
                    content=[TextContent(type="text", text="# Playbook")]
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
            patch("flights_cli.providers.tutu_client.Client", SlowCloseSdkClient),
        ):
            started = time.monotonic()
            with self.assertRaises(TimeoutError):
                async with TutuMcpClient(
                    url="https://mcp.tutu.ru/mcp",
                    deadline=started + 0.04,
                ):
                    pass
            self.assertLess(time.monotonic() - started, 0.1)

    async def test_uses_custom_http_transport_legacy_mode_and_loads_playbook_once(
        self,
    ) -> None:
        events: list[object] = []
        transport = object()

        class FakeHttpClient:
            def __init__(self, **kwargs: object) -> None:
                events.append(("http_client", kwargs))

            async def __aenter__(self) -> "FakeHttpClient":
                return self

            async def __aexit__(self, *args: object) -> None:
                events.append("http_close")

        class FakeSdkClient:
            protocol_version = "2025-11-25"
            server_info = None

            def __init__(self, server: object, **kwargs: object) -> None:
                events.append(("sdk_client", server, kwargs))

            async def __aenter__(self) -> "FakeSdkClient":
                events.append("initialize")
                return self

            async def __aexit__(self, *args: object) -> None:
                events.append("sdk_close")

            async def call_tool(
                self,
                name: str,
                arguments: dict[str, object],
                **kwargs: object,
            ) -> CallToolResult:
                events.append(("tool", name, arguments, kwargs))
                text = (
                    "# Tutu playbook"
                    if name == "get_avia_instructions"
                    else '{"offers": []}'
                )
                return CallToolResult(content=[TextContent(type="text", text=text)])

        with (
            patch(
                "flights_cli.providers.tutu_client.httpx2.AsyncClient",
                FakeHttpClient,
            ),
            patch(
                "flights_cli.providers.tutu_client.streamable_http_client",
                side_effect=lambda url, **kwargs: (
                    events.append(("transport", url, kwargs)) or transport
                ),
            ),
            patch("flights_cli.providers.tutu_client.Client", FakeSdkClient),
        ):
            async with TutuMcpClient(
                url="https://mcp.tutu.ru/mcp/",
                deadline=time.monotonic() + 5,
            ) as client:
                self.assertEqual(client.playbook, "# Tutu playbook")
                self.assertEqual(
                    await client.search_avia({"origin": "SVX"}), {"offers": []}
                )

        tool_events = [
            event for event in events if isinstance(event, tuple) and event[0] == "tool"
        ]
        self.assertEqual(
            [event[1] for event in tool_events],
            ["get_avia_instructions", "search_avia"],
        )
        sdk_event = next(
            event
            for event in events
            if isinstance(event, tuple) and event[0] == "sdk_client"
        )
        self.assertIs(sdk_event[1], transport)
        self.assertEqual(sdk_event[2]["mode"], "legacy")
        self.assertIsNone(sdk_event[2]["cache"])
        transport_event = next(
            event
            for event in events
            if isinstance(event, tuple) and event[0] == "transport"
        )
        self.assertTrue(transport_event[2]["terminate_on_close"])
        self.assertIsInstance(transport_event[2]["http_client"], FakeHttpClient)
        http_event = next(
            event
            for event in events
            if isinstance(event, tuple) and event[0] == "http_client"
        )
        self.assertFalse(http_event[1]["http2"])
        self.assertTrue(http_event[1]["follow_redirects"])

    async def test_empty_playbook_is_rejected_without_search(self) -> None:
        class FakeHttpClient:
            def __init__(self, **kwargs: object) -> None:
                pass

            async def __aenter__(self) -> "FakeHttpClient":
                return self

            async def __aexit__(self, *args: object) -> None:
                return None

        class EmptyPlaybookSdkClient:
            protocol_version = "2025-11-25"
            server_info = None

            def __init__(self, server: object, **kwargs: object) -> None:
                pass

            async def __aenter__(self) -> "EmptyPlaybookSdkClient":
                return self

            async def __aexit__(self, *args: object) -> None:
                return None

            async def call_tool(
                self,
                name: str,
                arguments: dict[str, object],
                **kwargs: object,
            ) -> CallToolResult:
                return CallToolResult(content=[TextContent(type="text", text="   ")])

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
                EmptyPlaybookSdkClient,
            ),
            self.assertRaises(CliError) as error,
        ):
            async with TutuMcpClient(
                url="https://mcp.tutu.ru/mcp",
                deadline=time.monotonic() + 5,
            ):
                self.fail("empty playbook must prevent entering the session")

        self.assertEqual(error.exception.details["tool"], "get_avia_instructions")

    async def test_search_requires_object_payload(self) -> None:
        class FakeClient(TutuMcpClient):
            async def _call_tool(  # type: ignore[override]
                self, tool_name: str, arguments: dict[str, object]
            ) -> list[object]:
                return []

        client = FakeClient(
            url="https://mcp.tutu.ru/mcp",
            deadline=time.monotonic() + 5,
        )

        with self.assertRaises(CliError) as error:
            await client.search_avia({})

        self.assertEqual(error.exception.details["tool"], "search_avia")
        self.assertEqual(error.exception.details["payload_type"], "list")


if __name__ == "__main__":
    unittest.main()
