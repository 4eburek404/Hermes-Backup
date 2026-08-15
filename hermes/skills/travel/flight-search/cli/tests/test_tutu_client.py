from __future__ import annotations

import asyncio
import json
import time
import unittest
from unittest.mock import patch

import httpx2

try:
    from builtins import ExceptionGroup
except ImportError:  # pragma: no cover - Python 3.10 compatibility
    from exceptiongroup import ExceptionGroup

from mcp.types import CallToolResult, Implementation, TextContent

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


class FakeSdkClient:
    protocol_version = "2025-11-25"
    server_info = Implementation(name="fake-tutu", version="1")

    def __init__(self, server: object, **kwargs: object) -> None:
        self.server = server
        self.kwargs = kwargs
        self.calls: list[tuple[str, dict[str, object], dict[str, object]]] = []
        self.closed = False

    async def __aenter__(self) -> FakeSdkClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        self.closed = True

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, object],
        **kwargs: object,
    ) -> CallToolResult:
        self.calls.append((name, arguments, kwargs))
        text = (
            "# Tutu playbook" if name == "get_avia_instructions" else '{"offers": []}'
        )
        return CallToolResult(content=[TextContent(type="text", text=text)])


class TutuMcpClientLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_initialize_deadline_wins_over_sdk_cleanup_failure(self) -> None:
        class FailingInitializeCleanupClient(FakeSdkClient):
            async def __aenter__(self) -> FailingInitializeCleanupClient:
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    raise httpx2.ReadError("initialize cleanup failed") from None

        with (
            patch(
                "flights_cli.providers.tutu_client.Client",
                FailingInitializeCleanupClient,
            ),
            self.assertRaises(TimeoutError) as error,
        ):
            await TutuMcpClient(
                url="https://mcp.tutu.ru/mcp",
                deadline=time.monotonic() + 0.02,
            ).__aenter__()

        self.assertEqual(
            getattr(error.exception, "_tutu_operation", None),
            "initialize",
        )

    async def test_search_deadline_wins_over_sdk_cleanup_failure(self) -> None:
        class FailingSearchCleanupClient(FakeSdkClient):
            async def __aexit__(self, *args: object) -> None:
                del args
                raise httpx2.ReadError("search cleanup failed")

            async def call_tool(
                self,
                name: str,
                arguments: dict[str, object],
                **kwargs: object,
            ) -> CallToolResult:
                if name == "get_avia_instructions":
                    return await super().call_tool(name, arguments, **kwargs)
                await asyncio.Event().wait()
                raise AssertionError("unreachable")

        with (
            patch(
                "flights_cli.providers.tutu_client.Client",
                FailingSearchCleanupClient,
            ),
            self.assertRaises(TimeoutError) as error,
        ):
            async with TutuMcpClient(
                url="https://mcp.tutu.ru/mcp",
                deadline=time.monotonic() + 0.02,
            ) as client:
                await client.search_avia({})

        self.assertEqual(
            getattr(error.exception, "_tutu_operation", None),
            "search_avia",
        )

    async def test_initialize_cancellation_wins_over_sdk_cleanup_failure(
        self,
    ) -> None:
        started = asyncio.Event()
        cleanup_attempts: list[str] = []

        class FailingInitializeCleanupClient(FakeSdkClient):
            async def __aenter__(self) -> FailingInitializeCleanupClient:
                started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    self.closed = True
                    cleanup_attempts.append("initialize")
                    raise httpx2.ReadError("initialize cleanup failed") from None

        client = TutuMcpClient(
            url="https://mcp.tutu.ru/mcp",
            deadline=time.monotonic() + 5,
        )
        with patch(
            "flights_cli.providers.tutu_client.Client",
            FailingInitializeCleanupClient,
        ):
            task = asyncio.create_task(client.__aenter__())
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError) as error:
                await task

        self.assertIsNone(getattr(error.exception, "_tutu_operation", None))
        self.assertTrue(task.cancelled())
        self.assertEqual(cleanup_attempts, ["initialize"])
        self.assertIsNone(client._session_context)

    async def test_search_cancellation_wins_over_sdk_cleanup_failure(self) -> None:
        started = asyncio.Event()
        cleanup_attempts: list[str] = []
        sdk_clients: list[FailingSearchCleanupClient] = []

        class FailingSearchCleanupClient(FakeSdkClient):
            async def __aexit__(self, *args: object) -> None:
                del args
                self.closed = True
                cleanup_attempts.append("search")
                raise httpx2.ReadError("search cleanup failed")

            async def call_tool(
                self,
                name: str,
                arguments: dict[str, object],
                **kwargs: object,
            ) -> CallToolResult:
                if name == "get_avia_instructions":
                    return await super().call_tool(name, arguments, **kwargs)
                started.set()
                await asyncio.Event().wait()
                raise AssertionError("unreachable")

        def build_client(
            server: object, **kwargs: object
        ) -> FailingSearchCleanupClient:
            sdk = FailingSearchCleanupClient(server, **kwargs)
            sdk_clients.append(sdk)
            return sdk

        client = TutuMcpClient(
            url="https://mcp.tutu.ru/mcp",
            deadline=time.monotonic() + 5,
        )

        async def search() -> None:
            async with client:
                await client.search_avia({})

        with patch(
            "flights_cli.providers.tutu_client.Client",
            side_effect=build_client,
        ):
            task = asyncio.create_task(search())
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError) as error:
                await task

        self.assertIsNone(getattr(error.exception, "_tutu_operation", None))
        self.assertTrue(task.cancelled())
        self.assertEqual(cleanup_attempts, ["search"])
        self.assertTrue(sdk_clients[0].closed)
        self.assertIsNone(client._session_context)

    async def test_expired_deadline_before_initialize_retains_operation(self) -> None:
        with (
            patch("flights_cli.providers.tutu_client.Client") as sdk_client,
            self.assertRaises(TimeoutError) as error,
        ):
            await TutuMcpClient(
                url="https://mcp.tutu.ru/mcp",
                deadline=time.monotonic() - 1,
            ).__aenter__()

        sdk_client.assert_not_called()
        self.assertEqual(
            getattr(error.exception, "_tutu_operation", None),
            "initialize",
        )

    async def test_expired_deadline_before_search_retains_tool_operation(self) -> None:
        client = TutuMcpClient(
            url="https://mcp.tutu.ru/mcp",
            deadline=time.monotonic() - 1,
        )
        client._client = FakeSdkClient("unused")  # type: ignore[assignment]

        with self.assertRaises(TimeoutError) as error:
            await client.search_avia({})

        self.assertEqual(
            getattr(error.exception, "_tutu_operation", None),
            "search_avia",
        )

    async def test_direct_sdk_context_configuration_and_playbook_preflight(
        self,
    ) -> None:
        sdk_clients: list[FakeSdkClient] = []

        def build_client(server: object, **kwargs: object) -> FakeSdkClient:
            client = FakeSdkClient(server, **kwargs)
            sdk_clients.append(client)
            return client

        with patch(
            "flights_cli.providers.tutu_client.Client", side_effect=build_client
        ):
            async with TutuMcpClient(
                url="https://mcp.tutu.ru/mcp/",
                deadline=time.monotonic() + 5,
            ) as client:
                self.assertEqual(client.playbook, "# Tutu playbook")
                self.assertEqual(client.protocol_version, "2025-11-25")
                self.assertEqual(client.server_info, FakeSdkClient.server_info)
                self.assertEqual(
                    await client.search_avia({"origin": "SVX"}), {"offers": []}
                )

        self.assertEqual(len(sdk_clients), 1)
        sdk = sdk_clients[0]
        self.assertEqual(sdk.server, "https://mcp.tutu.ru/mcp")
        self.assertEqual(sdk.kwargs["mode"], "legacy")
        self.assertIsNone(sdk.kwargs["cache"])
        self.assertGreater(float(sdk.kwargs["read_timeout_seconds"]), 0)
        self.assertEqual(
            [call[0] for call in sdk.calls],
            ["get_avia_instructions", "search_avia"],
        )
        self.assertTrue(sdk.closed)
        self.assertIsNone(client.protocol_version)
        self.assertIsNone(client.server_info)

    async def test_complete_tool_call_is_bounded_by_absolute_deadline(self) -> None:
        class SlowSdkClient(FakeSdkClient):
            async def call_tool(
                self,
                name: str,
                arguments: dict[str, object],
                **kwargs: object,
            ) -> CallToolResult:
                if name == "search_avia":
                    await asyncio.sleep(0.1)
                return await super().call_tool(name, arguments, **kwargs)

        with patch("flights_cli.providers.tutu_client.Client", SlowSdkClient):
            started = time.monotonic()
            with self.assertRaises(TimeoutError) as error:
                async with TutuMcpClient(
                    url="https://mcp.tutu.ru/mcp",
                    deadline=started + 0.03,
                ) as client:
                    await client.search_avia({})

        self.assertLess(time.monotonic() - started, 0.1)
        self.assertEqual(
            getattr(error.exception, "_tutu_operation", None),
            "search_avia",
        )

    async def test_initialize_and_close_are_bounded_and_tagged(self) -> None:
        class SlowInitializeSdkClient(FakeSdkClient):
            async def __aenter__(self) -> SlowInitializeSdkClient:
                await asyncio.sleep(0.1)
                return self

        with (
            patch("flights_cli.providers.tutu_client.Client", SlowInitializeSdkClient),
            self.assertRaises(TimeoutError) as initialize_error,
        ):
            await TutuMcpClient(
                url="https://mcp.tutu.ru/mcp",
                deadline=time.monotonic() + 0.03,
            ).__aenter__()
        self.assertEqual(
            getattr(initialize_error.exception, "_tutu_operation", None),
            "initialize",
        )

        class SlowCloseSdkClient(FakeSdkClient):
            async def __aexit__(self, *args: object) -> None:
                await asyncio.sleep(0.1)

        with (
            patch("flights_cli.providers.tutu_client.Client", SlowCloseSdkClient),
            self.assertRaises(TimeoutError) as close_error,
        ):
            async with TutuMcpClient(
                url="https://mcp.tutu.ru/mcp",
                deadline=time.monotonic() + 0.03,
            ):
                pass
        self.assertEqual(
            getattr(close_error.exception, "_tutu_operation", None),
            "close",
        )

    async def test_sole_cli_error_leaf_survives_nested_sdk_teardown(self) -> None:
        class WrappingSdkClient(FakeSdkClient):
            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc: BaseException | None,
                traceback: object,
            ) -> None:
                del exc_type, traceback
                assert isinstance(exc, CliError)
                raise ExceptionGroup("SDK teardown", [ExceptionGroup("tool", [exc])])

            async def call_tool(
                self,
                name: str,
                arguments: dict[str, object],
                **kwargs: object,
            ) -> CallToolResult:
                if name == "get_avia_instructions":
                    return await super().call_tool(name, arguments, **kwargs)
                return CallToolResult(
                    isError=True,
                    content=[TextContent(type="text", text="bad request")],
                )

        with (
            patch("flights_cli.providers.tutu_client.Client", WrappingSdkClient),
            self.assertRaises(CliError) as error,
        ):
            async with TutuMcpClient(
                url="https://mcp.tutu.ru/mcp",
                deadline=time.monotonic() + 5,
            ) as client:
                await client.search_avia({})

        self.assertEqual(error.exception.error_type, "upstream_error")
        self.assertEqual(
            error.exception.details,
            {"provider": "tutu", "tool": "search_avia"},
        )
        self.assertIn("bad request", str(error.exception))

    async def test_empty_playbook_is_rejected_without_search(self) -> None:
        class EmptyPlaybookSdkClient(FakeSdkClient):
            async def call_tool(
                self,
                name: str,
                arguments: dict[str, object],
                **kwargs: object,
            ) -> CallToolResult:
                return CallToolResult(content=[TextContent(type="text", text="   ")])

        with (
            patch("flights_cli.providers.tutu_client.Client", EmptyPlaybookSdkClient),
            self.assertRaises(CliError) as error,
        ):
            async with TutuMcpClient(
                url="https://mcp.tutu.ru/mcp",
                deadline=time.monotonic() + 5,
            ):
                self.fail("empty playbook must prevent entering the session")

        self.assertEqual(error.exception.details["tool"], "get_avia_instructions")

    async def test_search_requires_object_payload(self) -> None:
        class NonObjectSearchSdkClient(FakeSdkClient):
            async def call_tool(
                self,
                name: str,
                arguments: dict[str, object],
                **kwargs: object,
            ) -> CallToolResult:
                if name == "get_avia_instructions":
                    return await super().call_tool(name, arguments, **kwargs)
                return CallToolResult(
                    content=[TextContent(type="text", text='["not", "an", "object"]')],
                )

        with (
            patch("flights_cli.providers.tutu_client.Client", NonObjectSearchSdkClient),
            self.assertRaises(CliError) as error,
        ):
            async with TutuMcpClient(
                url="https://mcp.tutu.ru/mcp",
                deadline=time.monotonic() + 5,
            ) as client:
                await client.search_avia({})

        self.assertEqual(error.exception.details["tool"], "search_avia")
        self.assertEqual(error.exception.details["payload_type"], "list")


if __name__ == "__main__":
    unittest.main()
