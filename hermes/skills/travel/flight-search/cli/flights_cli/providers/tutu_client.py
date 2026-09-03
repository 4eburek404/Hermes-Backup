"""Official MCP SDK client boundary for the Tutu flight tools."""

from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from typing import Any, AsyncIterator, TypeAlias

import httpx2
from anyio import fail_after, get_cancelled_exc_class
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client
from mcp.types import CallToolResult, Implementation, TextContent

from .. import __version__
from ..config import TUTU_MCP_DEFAULT_URL
from ..errors import CliError

TutuToolPayload: TypeAlias = dict[str, Any] | list[Any] | str


class Client:
    """MCP 2.0 client with the small interface Flight Search needs."""

    def __init__(
        self,
        server: str,
        *,
        mode: str,
        client_info: Implementation,
        read_timeout_seconds: float,
        cache: None,
    ) -> None:
        del mode, cache
        self.server = server
        self.client_info = client_info
        self.read_timeout_seconds = read_timeout_seconds
        self.protocol_version: str | int | None = None
        self.server_info: Implementation | None = None
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> Client:
        stack = AsyncExitStack()
        self._stack = stack
        try:
            http_client = await stack.enter_async_context(
                create_mcp_http_client(
                    timeout=httpx2.Timeout(
                        self.read_timeout_seconds,
                        read=self.read_timeout_seconds,
                    )
                )
            )
            read_stream, write_stream = await stack.enter_async_context(
                streamable_http_client(self.server, http_client=http_client)
            )
            session = await stack.enter_async_context(
                ClientSession(
                    read_stream,
                    write_stream,
                    read_timeout_seconds=self.read_timeout_seconds,
                    client_info=self.client_info,
                )
            )
            initialized = await session.initialize()
            self._session = session
            self.protocol_version = initialized.protocol_version
            self.server_info = initialized.server_info
        except BaseException:
            await stack.aclose()
            self._stack = None
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: Any,
    ) -> bool | None:
        stack = self._stack
        self._stack = None
        self._session = None
        if stack is None:
            return None
        return await stack.__aexit__(exc_type, exc, traceback)

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        read_timeout_seconds: float,
    ) -> CallToolResult:
        session = self._session
        if session is None:
            raise RuntimeError("MCP client must be entered before calling tools")
        return await session.call_tool(
            name,
            arguments,
            read_timeout_seconds=read_timeout_seconds,
        )


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
    """A single deadline-bound direct official MCP SDK session."""

    def __init__(self, *, url: str | None, deadline: float) -> None:
        self.url = normalize_tutu_mcp_url(url)
        self.deadline = deadline
        self.playbook: str | None = None
        self._client: Client | None = None
        self._active_operation: str | None = None
        self._session_context: AbstractAsyncContextManager[None] | None = None

    def remaining_timeout(self, operation: str) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            error = TimeoutError(f"Tutu MCP deadline exhausted before {operation}")
            setattr(error, "_tutu_operation", operation)
            raise error
        return remaining

    @property
    def protocol_version(self) -> str | None:
        return self._client.protocol_version if self._client is not None else None

    @property
    def server_info(self) -> Implementation | None:
        return self._client.server_info if self._client is not None else None

    @staticmethod
    def _sole_cli_error(exc: Exception) -> CliError | None:
        children = getattr(exc, "exceptions", None)
        if not isinstance(children, (tuple, list)) or not children:
            return exc if isinstance(exc, CliError) else None
        leaves: list[Exception] = []
        pending = list(children)
        while pending:
            child = pending.pop()
            if not isinstance(child, Exception):
                return None
            nested = getattr(child, "exceptions", None)
            if isinstance(nested, (tuple, list)) and nested:
                pending.extend(nested)
            else:
                leaves.append(child)
        if len(leaves) == 1 and isinstance(leaves[0], CliError):
            return leaves[0]
        return None

    async def _call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> TutuToolPayload:
        client = self._client
        if client is None:
            raise RuntimeError("TutuMcpClient must be entered before calling tools")
        remaining = self.remaining_timeout(tool_name)
        self._active_operation = tool_name
        try:
            result = await client.call_tool(
                tool_name,
                arguments,
                read_timeout_seconds=remaining,
            )
            payload = _extract_tool_payload(result, tool_name)
        except Exception as exc:
            setattr(exc, "_tutu_operation", tool_name)
            raise
        self._active_operation = None
        return payload

    @asynccontextmanager
    async def _direct_session(self) -> AsyncIterator[None]:
        """Own the SDK context directly in the caller task."""

        remaining = self.remaining_timeout("initialize")
        self._active_operation = "initialize"
        deadline_scope: Any = None
        try:
            with fail_after(remaining) as deadline_scope:
                async with Client(
                    self.url,
                    mode="legacy",
                    client_info=Implementation(
                        name="hermes-flights-cli",
                        version=__version__,
                    ),
                    read_timeout_seconds=remaining,
                    cache=None,
                ) as client:
                    self._client = client
                    self._active_operation = None
                    playbook = await self._call_tool("get_avia_instructions", {})
                    if not isinstance(playbook, str) or not playbook.strip():
                        raise CliError(
                            "Tutu MCP get_avia_instructions returned an empty or unsupported playbook",
                            error_type="upstream_error",
                            details={
                                "provider": "tutu",
                                "tool": "get_avia_instructions",
                            },
                        )
                    self.playbook = playbook
                    self._active_operation = None
                    try:
                        yield
                    except BaseException:
                        raise
                    else:
                        self._active_operation = "close"
        except get_cancelled_exc_class():
            raise
        except Exception as exc:
            task = asyncio.current_task()
            if task is not None and task.cancelling():
                raise get_cancelled_exc_class() from None
            if deadline_scope is not None and deadline_scope.cancel_called:
                operation = self._active_operation or "initialize"
                timeout_error = TimeoutError(
                    f"Tutu MCP deadline exhausted during {operation}"
                )
                setattr(timeout_error, "_tutu_operation", operation)
                raise timeout_error from exc
            cli_error = self._sole_cli_error(exc)
            if cli_error is not None:
                if cli_error is exc:
                    raise
                raise cli_error from exc
            if not hasattr(exc, "_tutu_operation"):
                setattr(
                    exc,
                    "_tutu_operation",
                    self._active_operation or "initialize",
                )
            raise
        finally:
            self._client = None
            self._active_operation = None

    async def __aenter__(self) -> TutuMcpClient:
        if self._session_context is not None:
            raise RuntimeError("TutuMcpClient cannot be entered more than once")
        context = self._direct_session()
        self._session_context = context
        try:
            await context.__aenter__()
        except BaseException as failure:
            self._session_context = None
            task = asyncio.current_task()
            if (
                not isinstance(failure, get_cancelled_exc_class())
                and task is not None
                and task.cancelling()
            ):
                raise get_cancelled_exc_class() from None
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: Any,
    ) -> None:
        context = self._session_context
        if context is None:
            return
        self._session_context = None
        try:
            await context.__aexit__(exc_type, exc, traceback)
        except BaseException:
            task = asyncio.current_task()
            if (
                isinstance(exc, get_cancelled_exc_class())
                and task is not None
                and task.cancelling()
            ):
                raise exc.with_traceback(traceback)
            raise

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
