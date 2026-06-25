"""Shared curl_cffi HTTP transport for carrier adapters.

Booking URLs carry private credentials, so transport errors mention only the
caller-provided label, status/content type, and exception class.
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable
from urllib.parse import urlencode

from curl_cffi import requests as _requests


MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (0.5, 2.0)
IMPERSONATE_TARGET = "chrome"
_NETWORK_ERRORS: tuple[type[BaseException], ...] = (
    getattr(_requests, "RequestsError", OSError),
    TimeoutError,
    OSError,
)


class TransportError(ValueError):
    """Carrier HTTP failure with a redaction-safe message."""


def active_transport() -> str:
    return "curl_cffi"


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
    response = _requests.request(
        method,
        url,
        headers=headers,
        data=body,
        timeout=timeout,
        impersonate=IMPERSONATE_TARGET,
    )
    return response.status_code, response.headers.get("Content-Type", ""), response.text


def _response_final_url(response: Any) -> str:
    for attr in ("url", "redirect_url"):
        value = getattr(response, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def resolve_redirect_url(
    url: str,
    *,
    timeout: int = 30,
    label: str = "redirect resolution",
    max_redirects: int = 6,
) -> str:
    """Resolve HTTP redirects with curl_cffi and return the final URL.

    The input URL may contain credentials; failures intentionally mention only
    the caller-provided label and exception/status class, never the URL.
    """
    request_headers = browser_headers({"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
    try:
        response = _requests.request(
            "GET",
            url,
            headers=request_headers,
            timeout=timeout,
            impersonate=IMPERSONATE_TARGET,
            allow_redirects=True,
            max_redirects=max_redirects,
        )
    except _NETWORK_ERRORS as exc:
        raise TransportError(f"{label} failed: network error ({type(exc).__name__})") from exc

    final_url = _response_final_url(response)
    if not final_url:
        raise TransportError(f"{label} failed: no final URL")
    return final_url


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
    """Fetch with network-error and 5xx retries; never raises on HTTP status."""
    request_headers = browser_headers(headers)
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
    except json.JSONDecodeError as exc:
        raise TransportError(f"{label} returned a non-JSON response") from exc
