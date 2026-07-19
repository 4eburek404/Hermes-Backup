from __future__ import annotations

import http.client
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from .. import __version__
from ..config import TUTU_MCP_DEFAULT_URL
from ..errors import CliError

MCP_PROTOCOL_VERSION = "2025-06-18"
TUTU_MCP_INCOMPLETE_READ_RETRIES = 2

UrlOpen = Callable[..., Any]
Sleeper = Callable[[float], None]


def default_tutu_mcp_url() -> str:
    return os.getenv("FLIGHTS_TUTU_MCP_URL", TUTU_MCP_DEFAULT_URL)


def normalize_tutu_mcp_url(value: str | None) -> str:
    url = (value or default_tutu_mcp_url()).strip()
    if not url:
        raise CliError("Tutu MCP URL is required", error_type="validation_error")
    if url.endswith("/mcp/"):
        url = url[:-1]
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError as exc:
        raise CliError(
            "Tutu MCP URL is invalid", error_type="validation_error"
        ) from exc
    if parsed.scheme not in {"http", "https"}:
        raise CliError(
            "Tutu MCP URL must use http or https",
            error_type="validation_error",
        )
    if not parsed.netloc or not parsed.hostname:
        raise CliError(
            "Tutu MCP URL must include a host", error_type="validation_error"
        )
    return url


def decode_mcp_response(raw: bytes, content_type: str | None) -> dict[str, Any]:
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return {}
    if "text/event-stream" in (content_type or "").lower():
        events: list[dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                item = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                events.append(item)
        if not events:
            raise CliError(
                "Tutu MCP returned an empty event stream", error_type="upstream_error"
            )
        for item in reversed(events):
            if "result" in item or "error" in item:
                return item
        return events[-1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CliError(
            f"Tutu MCP returned invalid JSON: {exc}", error_type="upstream_error"
        ) from exc
    if not isinstance(data, dict):
        raise CliError(
            "Tutu MCP response must be a JSON object", error_type="upstream_error"
        )
    return data


def tutu_mcp_http_post(
    url: str,
    payload: dict[str, Any],
    *,
    timeout: int,
    session_id: str | None = None,
    urlopen: UrlOpen = urllib.request.urlopen,
    sleep: Sleeper = time.sleep,
) -> tuple[dict[str, Any], str | None]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
        "User-Agent": f"flights-cli/{__version__}",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    data = json.dumps(payload).encode("utf-8")
    attempts = TUTU_MCP_INCOMPLETE_READ_RETRIES + 1
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read()
                content_type = response.headers.get("Content-Type")
                next_session_id = (
                    response.headers.get("Mcp-Session-Id")
                    or response.headers.get("mcp-session-id")
                    or session_id
                )
                return decode_mcp_response(raw, content_type), next_session_id
        except http.client.IncompleteRead as exc:
            details = _incomplete_read_details(exc, payload=payload, attempts=attempt)
            if attempt < attempts:
                sleep(0.2 * attempt)
                continue
            read = details.get("bytes_read", "unknown")
            expected = details.get("bytes_expected", "unknown")
            tool = details.get("tool") or details.get("method") or "request"
            raise CliError(
                f"Tutu MCP incomplete HTTP response while calling {tool}: read {read} of {expected} bytes",
                error_type="upstream_incomplete_read",
                details=details,
            ) from exc
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")[:1000]
            raise CliError(
                f"Tutu MCP HTTP {exc.code}: {body_text}",
                error_type="upstream_error",
                details={
                    "http_status": exc.code,
                    "retry_after": exc.headers.get("Retry-After"),
                },
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise CliError(
                f"Tutu MCP request failed: {type(exc).__name__}: {exc}",
                error_type="upstream_error",
            ) from exc
    raise CliError("Tutu MCP request failed", error_type="upstream_error")


def _mcp_payload_context(payload: dict[str, Any]) -> dict[str, Any]:
    method = str(payload.get("method") or "")
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    tool = params.get("name") if isinstance(params, dict) else None
    return {
        "provider": "tutu",
        "method": method or None,
        "tool": str(tool) if tool else method or None,
    }


def _incomplete_read_details(
    exc: http.client.IncompleteRead,
    *,
    payload: dict[str, Any],
    attempts: int,
) -> dict[str, Any]:
    partial = exc.partial
    bytes_read = len(partial) if isinstance(partial, bytes) else None
    bytes_missing = exc.expected if isinstance(exc.expected, int) else None
    bytes_expected = (
        bytes_read + bytes_missing
        if bytes_read is not None and bytes_missing is not None
        else None
    )
    details = {
        **_mcp_payload_context(payload),
        "failure_reason": "incomplete_read",
        "bytes_read": bytes_read,
        "bytes_missing": bytes_missing,
        "bytes_expected": bytes_expected,
        "attempts": attempts,
    }
    return {key: value for key, value in details.items() if value is not None}


__all__ = [
    "MCP_PROTOCOL_VERSION",
    "TUTU_MCP_INCOMPLETE_READ_RETRIES",
    "decode_mcp_response",
    "default_tutu_mcp_url",
    "normalize_tutu_mcp_url",
    "tutu_mcp_http_post",
]
