"""Official MCP SDK client boundary for the Tutu flight tools."""

from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import AsyncExitStack
from typing import Any, TypeAlias

import httpx2
from anyio import fail_after, get_cancelled_exc_class
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, Implementation, TextContent

from .. import __version__
from ..config import TUTU_MCP_DEFAULT_URL
from ..errors import CliError

TutuToolPayload: TypeAlias = dict[str, Any] | list[Any] | str


def default_tutu_mcp_url() -> str:
    return os.getenv("FLIGHTS_TUTU_MCP_URL", TUTU_MCP_DEFAULT_URL)


def normalize_tutu_mcp_url(value: str | None) -> str:
    raw = (value or default_tutu_mcp_url()).strip()
    if not raw:
        raise CliError("Tutu MCP URL is required", error_type="validation_error")
    try:
        parsed = httpx2.URL(raw)
    except (TypeError, ValueError) as exc:
        raise CliError(
            "Tutu MCP URL is invalid", error_type="validation_error"
        ) from exc
    if parsed.scheme not in {"http", "https"}:
        raise CliError(
            "Tutu MCP URL must use http or https",
            error_type="validation_error",
        )
    if not parsed.host:
        raise CliError(
            "Tutu MCP URL must include a host", error_type="validation_error"
        )
    if parsed.path.endswith("/mcp/"):
        parsed = parsed.copy_with(path=parsed.path[:-1])
    return str(parsed)


def _unwrap_payload(value: Any) -> TutuToolPayload | None:
    if isinstance(value, dict):
        if set(value) == {"result"} and isinstance(value["result"], (dict, list, str)):
            return _decode_payload(value["result"])
        return value
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return _decode_payload(value)
    return None


def _decode_payload(value: str | dict[str, Any] | list[Any]) -> TutuToolPayload:
    if not isinstance(value, str):
        unwrapped = _unwrap_payload(value)
        if unwrapped is not None:
            return unwrapped
        raise TypeError(f"unsupported payload: {type(value).__name__}")
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return value
    unwrapped = _unwrap_payload(decoded)
    return value if unwrapped is None else unwrapped


def _extract_tool_payload(result: CallToolResult, tool_name: str) -> TutuToolPayload:
    if result.is_error:
        messages = [
            item.text
            for item in result.content
            if isinstance(item, TextContent) and item.text
        ]
        raise CliError(
            f"Tutu MCP tool {tool_name} failed: "
            + ("; ".join(messages) or "unknown error"),
            error_type="upstream_error",
            details={"provider": "tutu", "tool": tool_name},
        )

    structured = _unwrap_payload(result.structured_content)
    if structured is not None:
        return structured

    for item in result.content:
        if isinstance(item, TextContent):
            return _decode_payload(item.text)
    raise CliError(
        f"Tutu MCP tool {tool_name} returned an unsupported payload",
        error_type="upstream_error",
        details={"provider": "tutu", "tool": tool_name},
    )


class TutuMcpClient:
    """A single deadline-bound Tutu MCP session."""

    def __init__(self, *, url: str | None, deadline: float) -> None:
        self.url = normalize_tutu_mcp_url(url)
        self.deadline = deadline
        self.playbook: str | None = None
        self._client: Client | None = None
        self._http_client: httpx2.AsyncClient | None = None
        self._active_operation: str | None = None
        self._deadline_scope: Any = None
        self._external_cancellation_operation: str | None = None
        self._session_task: asyncio.Task[None] | None = None
        self._command_queue: (
            asyncio.Queue[
                tuple[
                    str | None,
                    dict[str, Any],
                    asyncio.Future[TutuToolPayload | None],
                ]
            ]
            | None
        ) = None

    def remaining_timeout(self, operation: str) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            error = TimeoutError(f"Tutu MCP deadline exhausted before {operation}")
            setattr(error, "_tutu_operation", operation)
            raise error
        return remaining

    def _http_timeout(self, remaining: float) -> httpx2.Timeout:
        return httpx2.Timeout(
            remaining,
            connect=min(6.0, remaining),
            read=remaining,
            write=remaining,
            pool=remaining,
        )

    def _refresh_http_timeout(self, operation: str) -> float:
        remaining = self.remaining_timeout(operation)
        if self._http_client is not None:
            self._http_client.timeout = self._http_timeout(remaining)
        return remaining

    async def _close_stack(
        self,
        stack: AsyncExitStack,
        exc_type: type[BaseException] | None = None,
        exc: BaseException | None = None,
        traceback: Any = None,
    ) -> bool:
        operation = self._active_operation if exc is not None else "close"
        refresh_error: TimeoutError | None = None
        try:
            self._refresh_http_timeout("close")
        except TimeoutError as error:
            refresh_error = error
        effective_exc = exc if exc is not None else refresh_error
        effective_type = (
            exc_type
            if exc is not None
            else type(refresh_error)
            if refresh_error is not None
            else None
        )
        effective_traceback = (
            traceback
            if exc is not None
            else getattr(effective_exc, "__traceback__", None)
        )
        try:
            suppressed = await stack.__aexit__(
                effective_type,
                effective_exc,
                effective_traceback,
            )
        except Exception as close_error:
            if exc is not None:
                internal_cancellation_exposed_root = (
                    isinstance(exc, get_cancelled_exc_class())
                    and self._external_cancellation_operation is None
                    and not (
                        self._deadline_scope is not None
                        and self._deadline_scope.cancel_called
                    )
                    and bool(getattr(close_error, "exceptions", None))
                )
                if not internal_cancellation_exposed_root:
                    return False
            setattr(close_error, "_tutu_operation", operation or "close")
            raise
        if refresh_error is not None and exc is None and not suppressed:
            setattr(refresh_error, "_tutu_operation", "close")
            raise refresh_error
        return bool(suppressed)

    @property
    def protocol_version(self) -> str | None:
        return self._client.protocol_version if self._client is not None else None

    @property
    def server_info(self) -> Implementation | None:
        return self._client.server_info if self._client is not None else None

    @staticmethod
    def _resolve_failure(
        response: asyncio.Future[Any] | None,
        failure: BaseException,
    ) -> None:
        if response is None or response.done():
            return
        if isinstance(failure, get_cancelled_exc_class()):
            response.cancel()
        else:
            response.set_exception(failure)

    @staticmethod
    async def _drain_task(task: asyncio.Task[Any]) -> None:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except BaseException:
                break
        try:
            task.result()
        except BaseException:
            pass

    def _reset_session(self) -> None:
        self._client = None
        self._http_client = None
        self._active_operation = None
        self._deadline_scope = None
        self._external_cancellation_operation = None
        self._session_task = None
        self._command_queue = None

    async def _await_response(
        self,
        response: asyncio.Future[TutuToolPayload | None],
        *,
        operation: str,
    ) -> TutuToolPayload | None:
        task = self._session_task
        if task is None:
            raise RuntimeError("Tutu MCP session worker is not running")
        try:
            done, _ = await asyncio.wait(
                (response, task),
                return_when=asyncio.FIRST_COMPLETED,
            )
        except asyncio.CancelledError:
            self._external_cancellation_operation = operation
            if response.done():
                try:
                    response.result()
                except BaseException:
                    pass
            else:
                response.cancel()
            if not task.done():
                task.cancel()
            await self._drain_task(task)
            raise
        if response in done:
            return response.result()
        response.cancel()
        task.result()
        raise RuntimeError(
            f"Tutu MCP session worker exited before {operation} completed"
        )

    async def _call_tool_in_session(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> TutuToolPayload:
        if self._client is None:
            raise RuntimeError("Tutu MCP SDK client is not initialized")
        remaining = self._refresh_http_timeout(tool_name)
        self._active_operation = tool_name
        try:
            result = await self._client.call_tool(
                tool_name,
                arguments,
                read_timeout_seconds=remaining,
            )
        except Exception as exc:
            setattr(exc, "_tutu_operation", tool_name)
            raise
        payload = _extract_tool_payload(result, tool_name)
        self._active_operation = None
        return payload

    async def _session_worker(
        self,
        ready: asyncio.Future[TutuToolPayload | None],
        commands: asyncio.Queue[
            tuple[
                str | None,
                dict[str, Any],
                asyncio.Future[TutuToolPayload | None],
            ]
        ],
    ) -> None:
        response: asyncio.Future[TutuToolPayload | None] | None = ready
        try:
            remaining = self.remaining_timeout("initialize")
            async with AsyncExitStack() as stack:
                self._deadline_scope = stack.enter_context(fail_after(remaining))
                resources = AsyncExitStack()

                async def close_resources(
                    exc_type: type[BaseException] | None,
                    exc: BaseException | None,
                    traceback: Any,
                ) -> bool:
                    return await self._close_stack(
                        resources,
                        exc_type,
                        exc,
                        traceback,
                    )

                stack.push_async_exit(close_resources)
                http_client = await resources.enter_async_context(
                    httpx2.AsyncClient(
                        http2=False,
                        follow_redirects=True,
                        timeout=self._http_timeout(remaining),
                    )
                )
                self._http_client = http_client
                transport = streamable_http_client(
                    self.url,
                    http_client=http_client,
                    terminate_on_close=True,
                )
                client = Client(
                    transport,
                    mode="legacy",
                    client_info=Implementation(
                        name="hermes-flights-cli",
                        version=__version__,
                    ),
                    read_timeout_seconds=remaining,
                    cache=None,
                )
                resources.push_async_exit(client.__aexit__)
                self._refresh_http_timeout("initialize")
                self._active_operation = "initialize"
                try:
                    await client.__aenter__()
                except Exception as exc:
                    setattr(exc, "_tutu_operation", "initialize")
                    raise
                self._active_operation = None
                self._client = client
                playbook_payload = await self._call_tool_in_session(
                    "get_avia_instructions", {}
                )
                if (
                    not isinstance(playbook_payload, str)
                    or not playbook_payload.strip()
                ):
                    raise CliError(
                        "Tutu MCP get_avia_instructions returned an empty or unsupported playbook",
                        error_type="upstream_error",
                        details={
                            "provider": "tutu",
                            "tool": "get_avia_instructions",
                        },
                    )
                self.playbook = playbook_payload
                ready.set_result(None)
                response = None

                while True:
                    tool_name, arguments, response = await commands.get()
                    if tool_name is None:
                        self._active_operation = "close"
                        break
                    try:
                        payload = await self._call_tool_in_session(
                            tool_name,
                            arguments,
                        )
                    except Exception as failure:
                        response.set_exception(failure)
                    else:
                        response.set_result(payload)
                    response = None
            if response is not None and not response.done():
                response.set_result(None)
        except BaseException as failure:
            if not hasattr(failure, "_tutu_operation"):
                is_external_cancellation = (
                    isinstance(failure, get_cancelled_exc_class())
                    and self._external_cancellation_operation is not None
                )
                if not is_external_cancellation:
                    setattr(
                        failure,
                        "_tutu_operation",
                        self._active_operation or "initialize",
                    )
            self._resolve_failure(response, failure)
            raise
        finally:
            self._client = None
            self._http_client = None
            self._active_operation = None
            self._deadline_scope = None

    async def __aenter__(self) -> TutuMcpClient:
        self.remaining_timeout("initialize")
        if self._session_task is not None:
            raise RuntimeError("TutuMcpClient cannot be entered more than once")
        loop = asyncio.get_running_loop()
        ready: asyncio.Future[TutuToolPayload | None] = loop.create_future()
        commands: asyncio.Queue[
            tuple[
                str | None,
                dict[str, Any],
                asyncio.Future[TutuToolPayload | None],
            ]
        ] = asyncio.Queue()
        self._command_queue = commands
        self._session_task = asyncio.create_task(
            self._session_worker(ready, commands),
            name="tutu-mcp-session",
        )
        try:
            await self._await_response(ready, operation="initialize")
        except BaseException:
            task = self._session_task
            if task is not None:
                await self._drain_task(task)
            self._reset_session()
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: Any,
    ) -> None:
        task = self._session_task
        commands = self._command_queue
        if task is None:
            return
        try:
            if task.done():
                await self._drain_task(task)
                if exc is None:
                    task.result()
                return
            if isinstance(exc, get_cancelled_exc_class()):
                self._external_cancellation_operation = (
                    self._external_cancellation_operation
                    or self._active_operation
                    or "close"
                )
                task.cancel()
                await self._drain_task(task)
                return
            if commands is None:
                raise RuntimeError("Tutu MCP command queue is not available")
            close_response: asyncio.Future[TutuToolPayload | None] = (
                asyncio.get_running_loop().create_future()
            )
            commands.put_nowait((None, {}, close_response))
            try:
                await self._await_response(close_response, operation="close")
                await self._drain_task(task)
            except Exception:
                await self._drain_task(task)
                if exc is None:
                    raise
        finally:
            self._reset_session()

    async def _call_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> TutuToolPayload:
        self.remaining_timeout(tool_name)
        task = self._session_task
        commands = self._command_queue
        if task is None or commands is None:
            raise RuntimeError("TutuMcpClient must be entered before calling tools")
        if task.done():
            await self._drain_task(task)
            task.result()
        response: asyncio.Future[TutuToolPayload | None] = (
            asyncio.get_running_loop().create_future()
        )
        commands.put_nowait((tool_name, arguments, response))
        payload = await self._await_response(response, operation=tool_name)
        if payload is None:
            raise RuntimeError(f"Tutu MCP tool {tool_name} returned no payload")
        return payload

    async def search_avia(self, arguments: dict[str, Any]) -> dict[str, Any]:
        payload = await self._call_tool("search_avia", arguments)
        if isinstance(payload, dict):
            return payload
        raise CliError(
            "Tutu MCP tool search_avia returned a non-object payload",
            error_type="upstream_error",
            details={
                "provider": "tutu",
                "tool": "search_avia",
                "payload_type": type(payload).__name__,
            },
        )
