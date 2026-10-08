"""Replay only Tutu's MCP HTTP boundary for isolated agent evaluations."""
from __future__ import annotations

import hashlib
import json
import os
import socket
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

try:
    import httpx2
except ImportError:  # Other Python tools may not install the MCP SDK.
    httpx2 = None  # type: ignore[assignment]


_HOST = "mcp.tutu.ru"
_PATH = "/mcp"
_LOCK = threading.Lock()
_ORIGINAL_GETADDRINFO = socket.getaddrinfo


def _write_record(record: dict[str, Any]) -> None:
    path = os.environ.get("TUTU_EVAL_BOUNDARY_LOG")
    if not path:
        return
    with _LOCK:
        with Path(path).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _recorded_response(request: Any) -> Any:
    fixture_path = os.environ.get("TUTU_EVAL_FIXTURE")
    body = json.loads(request.content.decode("utf-8"))
    method = str(body.get("method", ""))
    request_id = body.get("id")
    parsed = urlsplit(str(request.url))
    record: dict[str, Any] = {
        "host": parsed.hostname,
        "path": parsed.path,
        "http_method": request.method,
        "jsonrpc_method": method,
    }
    status = 200
    headers = {"content-type": "application/json"}

    if parsed.path != _PATH:
        status = 404
        payload = _rpc_error(request_id, -32601, "MCP endpoint not found")
    elif method == "server/discover":
        status = 404
        payload = _rpc_error(request_id, -32601, "Method not found; use initialize")
    elif method == "initialize":
        params = body.get("params") or {}
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "tutu-recorded-replay", "version": "0.57.0"},
            },
        }
    elif method == "notifications/initialized":
        status = 202
        payload = None
    elif method == "tools/list":
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": [{"name": "search_avia", "inputSchema": {"type": "object"}}]},
        }
    elif method == "tools/call":
        params = body.get("params") or {}
        fixture_sha = None
        fixture: dict[str, Any] = {}
        if fixture_path and Path(fixture_path).is_file():
            fixture_bytes = Path(fixture_path).read_bytes()
            fixture_sha = hashlib.sha256(fixture_bytes).hexdigest()
            fixture = json.loads(fixture_bytes)
        arguments = params.get("arguments")
        record.update(
            {
                "tool_name": params.get("name"),
                "arguments": arguments if isinstance(arguments, dict) else {},
                "fixture_id": os.environ.get("TUTU_EVAL_FIXTURE_ID"),
                "fixture_sha256": fixture_sha,
            }
        )
        if not fixture:
            status = 503
            payload = _rpc_error(request_id, -32603, "recorded Tutu fixture unavailable")
        elif params.get("name") != fixture.get("tool") or arguments != fixture.get("arguments"):
            record["replay_status"] = "request-mismatch"
            payload = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": "Recorded Tutu request does not match."}],
                    "isError": True,
                },
            }
        else:
            envelope = json.loads(json.dumps(fixture["response"]["envelope"]))
            envelope["id"] = request_id
            payload = envelope
            record["replay_status"] = "fixture-served"
    else:
        status = 404
        payload = _rpc_error(request_id, -32601, "Method not found")

    if method != "tools/call":
        record["replay_status"] = "protocol-handshake" if status < 400 else "protocol-fallback"
    _write_record(record)
    content = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return httpx2.Response(status_code=status, headers=headers, content=content, request=request)


if httpx2 is not None:
    _original_send = httpx2.AsyncClient.send

    async def _send_with_tutu_replay(self: Any, request: Any, *args: Any, **kwargs: Any) -> Any:
        host = (request.url.host or "").lower().rstrip(".")
        if host == _HOST:
            if request.method.upper() != "POST":
                _write_record(
                    {"host": host, "path": request.url.path, "http_method": request.method, "replay_status": "blocked"}
                )
                return httpx2.Response(
                    status_code=405,
                    headers={"content-type": "text/plain"},
                    content=b"Recorded Tutu replay accepts MCP POST only.",
                    request=request,
                )
            await request.aread()
            return _recorded_response(request)
        return await _original_send(self, request, *args, **kwargs)

    httpx2.AsyncClient.send = _send_with_tutu_replay


def _deny_direct_tutu_dns(host: Any, *args: Any, **kwargs: Any) -> Any:
    if str(host).lower().rstrip(".") == _HOST:
        raise socket.gaierror("live Tutu access is disabled in recorded evaluation")
    return _ORIGINAL_GETADDRINFO(host, *args, **kwargs)


socket.getaddrinfo = _deny_direct_tutu_dns
