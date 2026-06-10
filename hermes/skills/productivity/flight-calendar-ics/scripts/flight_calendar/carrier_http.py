"""Shared HTTP transport helpers for flight-calendar-ics carriers."""
from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _build_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers: dict[str, str] = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    }
    if extra:
        headers.update(extra)
    return headers


def http_text(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: str | bytes | bytearray | None = None,
    timeout: int = 45,
    label: str | None = None,
) -> str:
    req = Request(
        url,
        data=(body.encode("utf-8") if isinstance(body, str) else body),
        method=method,
        headers=_build_headers(headers),
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = getattr(resp, "status", 200)
            content_type = resp.headers.get("Content-Type", "")
            text = raw.decode("utf-8", errors="replace")
    except HTTPError as exc:
        raw = exc.read()
        status = exc.code
        content_type = exc.headers.get("Content-Type", "")
        text = raw.decode("utf-8", errors="replace")
    except URLError as exc:
        raise ValueError(f"{label or 'HTTP request'} failed: {exc.reason}") from exc

    if status >= 400:
        raise ValueError(
            f"{label or 'HTTP request'} returned HTTP {status} ({content_type}) while calling {url}"
        )
    return text


def http_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | list[Any] | None = None,
    timeout: int = 45,
    label: str | None = None,
) -> Any:
    request_body: bytes | None = None
    request_headers = _build_headers(headers)
    if json_body is not None:
        request_headers["Content-Type"] = "application/json"
        request_body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        method = "POST"

    text = http_text(
        url,
        method=method,
        headers=request_headers,
        body=request_body,
        timeout=timeout,
        label=label,
    )
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label or 'HTTP request'} returned non-JSON response: {exc}") from exc
