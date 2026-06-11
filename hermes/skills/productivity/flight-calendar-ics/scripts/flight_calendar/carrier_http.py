"""Shared HTTP transport for flight-calendar-ics carrier adapters.

Privacy contract: messages raised from this module never contain URLs, hosts,
query parameters, or request/response bodies — booking URLs carry credentials
(PNR keys, locators, surnames). Errors carry only the caller-supplied label,
the HTTP status, the content type, and the exception class name.

Transport: stdlib urllib by default. If the optional ``curl_cffi`` package is
installed, requests are sent with a Chrome TLS/HTTP2 fingerprint
(``impersonate``), which some carrier anti-bot gates (e.g. Ngenix in front of
Aeroflot) require. Detection is automatic; ``active_transport()`` reports the
selected backend and doctor surfaces it as ``data.http_transport``.

Reliability: transient failures (network errors, timeouts) and HTTP >= 500 are
retried up to ``MAX_ATTEMPTS`` with growing backoff. HTTP 4xx is never
retried. ``request_raw`` never raises on HTTP status so callers can sniff
anti-bot interstitial bodies (they arrive as HTML with 403/503).
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:  # optional browser-fingerprint transport
    from curl_cffi import requests as _impersonate
except ImportError:  # pragma: no cover - depends on environment
    _impersonate = None

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (0.5, 2.0)
IMPERSONATE_TARGET = "chrome"
_NETWORK_ERRORS: tuple[type[BaseException], ...] = (URLError, TimeoutError, OSError)
if _impersonate is not None:  # pragma: no cover - depends on environment
    _NETWORK_ERRORS = (*_NETWORK_ERRORS, getattr(_impersonate, "RequestsError", OSError))


class TransportError(ValueError):
    """Carrier HTTP failure with a redaction-safe message."""


def active_transport() -> str:
    return "curl_cffi" if _impersonate is not None else "urllib"


def browser_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    }
    if extra:
        headers.update(extra)
    return headers


def _fetch_once(url: str, *, method: str, headers: dict[str, str], body: bytes | None, timeout: int) -> tuple[int, str, str]:
    """Single attempt -> (status, content_type, text). HTTP errors are data, not exceptions."""
    if _impersonate is not None:  # pragma: no cover - depends on environment
        response = _impersonate.request(
            method,
            url,
            headers=headers,
            data=body,
            timeout=timeout,
            impersonate=IMPERSONATE_TARGET,
        )
        return response.status_code, response.headers.get("Content-Type", ""), response.text
    request = Request(url, data=body, method=method, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return getattr(response, "status", 200), response.headers.get("Content-Type", ""), raw.decode("utf-8", errors="replace")
    except HTTPError as exc:
        raw = exc.read()
        content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
        return exc.code, content_type, raw.decode("utf-8", errors="replace")


def request_raw(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: int = 45,
    label: str = "HTTP request",
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[int, str, str]:
    """Fetch with network-error and 5xx retries; never raises on HTTP status.

    Returns the final ``(status, content_type, text)`` so callers can inspect
    error bodies (anti-bot interstitials, carrier error JSON).
    """
    request_headers = browser_headers(headers) if headers is not None else browser_headers()
    last_result: tuple[int, str, str] | None = None
    last_failure = f"{label} failed"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            status, content_type, text = _fetch_once(url, method=method, headers=request_headers, body=body, timeout=timeout)
        except _NETWORK_ERRORS as exc:
            last_failure = f"{label} failed: network error ({type(exc).__name__})"
            last_result = None
        else:
            last_result = (status, content_type, text)
            if status < 500:
                return last_result
            last_failure = f"{label} returned HTTP {status} ({content_type})"
        if attempt < MAX_ATTEMPTS:
            sleep(BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)])
    if last_result is not None:
        return last_result
    raise TransportError(f"{last_failure}; giving up after {MAX_ATTEMPTS} attempts")


def request_text(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: int = 45,
    label: str = "HTTP request",
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    status, content_type, text = request_raw(
        url, method=method, headers=headers, body=body, timeout=timeout, label=label, sleep=sleep
    )
    if status >= 400:
        raise TransportError(f"{label} returned HTTP {status} ({content_type})")
    return text


def request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | list[Any] | None = None,
    form_body: dict[str, str] | None = None,
    timeout: int = 45,
    label: str = "HTTP request",
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    request_headers = dict(headers or {})
    body: bytes | None = None
    if json_body is not None:
        request_headers.setdefault("Content-Type", "application/json")
        body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        method = "POST" if method == "GET" else method
    elif form_body is not None:
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        body = urlencode(form_body).encode("utf-8")
        method = "POST" if method == "GET" else method
    text = request_text(url, method=method, headers=request_headers, body=body, timeout=timeout, label=label, sleep=sleep)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise TransportError(f"{label} returned a non-JSON response")
