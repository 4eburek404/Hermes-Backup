"""Shared curl_cffi HTTP transport for carrier adapters.

Booking URLs carry private credentials, so transport errors mention only the
caller-provided label, status/content type, and exception class.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import time
from typing import Any, Callable, Iterator
from urllib.parse import urlencode, urljoin

from curl_cffi import requests as _requests


MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (0.5, 2.0)
IMPERSONATE_TARGET = "chrome"
_NETWORK_ERRORS: tuple[type[BaseException], ...] = (
    getattr(_requests, "RequestsError", OSError),
    OSError,
)


class TransportError(ValueError):
    """Carrier HTTP failure with a redaction-safe message."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class TransportResponse:
    """Redaction-safe response data exposed to carrier adapters."""

    status_code: int
    content_type: str
    text: str
    url: str
    headers: dict[str, str]


def browser_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    }
    if extra:
        headers.update(extra)
    return headers


@contextmanager
def open_session() -> Iterator[Any]:
    """Open a browser-impersonating session without exposing the HTTP engine."""
    session = _requests.Session(impersonate=IMPERSONATE_TARGET)
    try:
        yield session
    finally:
        close = getattr(session, "close", None)
        if callable(close):
            close()


def _response_from_engine(response: Any, fallback_url: str) -> TransportResponse:
    response_headers = dict(getattr(response, "headers", {}) or {})
    return TransportResponse(
        status_code=int(getattr(response, "status_code", 0) or 0),
        content_type=response_headers.get("Content-Type", ""),
        text=str(getattr(response, "text", "") or ""),
        url=str(getattr(response, "url", fallback_url) or fallback_url),
        headers=response_headers,
    )


def request_session_raw(
    session: Any,
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: Any = None,
    timeout: int = 45,
    allow_redirects: bool = True,
    max_redirects: int | None = None,
    label: str = "HTTP request",
    sleep: Callable[[float], None] = time.sleep,
) -> TransportResponse:
    """Use a shared session with the same retries and safe errors as request_raw."""
    request_headers = browser_headers(headers)
    last_result: TransportResponse | None = None
    last_failure = f"{label} failed"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            request_kwargs: dict[str, Any] = {
                "headers": request_headers,
                "data": body,
                "timeout": timeout,
                "allow_redirects": allow_redirects,
            }
            if max_redirects is not None:
                request_kwargs["max_redirects"] = max_redirects
            response = session.request(method, url, **request_kwargs)
            last_result = _response_from_engine(response, url)
        except _NETWORK_ERRORS as exc:
            last_result = None
            last_failure = f"{label} failed: network error ({type(exc).__name__})"
        else:
            if last_result.status_code < 500:
                return last_result
            last_failure = f"{label} returned HTTP {last_result.status_code} ({last_result.content_type})"
        if attempt < MAX_ATTEMPTS:
            sleep(BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)])
    if last_result is not None:
        return last_result
    raise TransportError(f"{last_failure}; giving up after {MAX_ATTEMPTS} attempts")


def response_text(response: TransportResponse, *, label: str) -> str:
    """Return successful response text or a redaction-safe HTTP failure."""
    if response.status_code >= 400:
        raise TransportError(
            f"{label} returned HTTP {response.status_code} ({response.content_type})",
            status_code=response.status_code,
        )
    return response.text


def _fetch_once(
    url: str, *, method: str, headers: dict[str, str], body: bytes | None, timeout: int
) -> tuple[int, str, str]:
    response = _requests.request(
        method,
        url,
        headers=headers,
        data=body,
        timeout=timeout,
        impersonate=IMPERSONATE_TARGET,
    )
    return response.status_code, response.headers.get("Content-Type", ""), response.text


def resolve_redirect_url(
    url: str,
    *,
    timeout: int = 30,
    label: str = "redirect resolution",
) -> str:
    """Read a single redirect Location with curl_cffi and return its URL.

    The input URL may contain credentials; failures intentionally mention only
    the caller-provided label and exception/status class, never the URL.

    This resolver must not follow redirects automatically; it always requests
    the wrapper URL with ``allow_redirects=False`` and ``max_redirects=0``.
    """
    request_headers = browser_headers(
        {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
    )
    try:
        response = _requests.request(
            "GET",
            url,
            headers=request_headers,
            timeout=timeout,
            impersonate=IMPERSONATE_TARGET,
            allow_redirects=False,
            max_redirects=0,
        )
    except _NETWORK_ERRORS as exc:
        raise TransportError(
            f"{label} failed: network error ({type(exc).__name__})"
        ) from exc

    status_code = int(getattr(response, "status_code", 0) or 0)
    if status_code not in {301, 302, 303, 307, 308}:
        raise TransportError(
            f"{label} failed: non-redirect HTTP {status_code}",
            status_code=status_code,
        )

    headers = getattr(response, "headers", {}) or {}
    location = headers.get("Location") or headers.get("location")
    if not isinstance(location, str) or not location.strip():
        raise TransportError(f"{label} failed: missing redirect Location")
    return urljoin(url, location.strip())


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
            status, content_type, text = _fetch_once(
                url, method=method, headers=request_headers, body=body, timeout=timeout
            )
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
        url,
        method=method,
        headers=headers,
        body=body,
        timeout=timeout,
        label=label,
        sleep=sleep,
    )
    if status >= 400:
        raise TransportError(
            f"{label} returned HTTP {status} ({content_type})",
            status_code=status,
        )
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
    text = request_text(
        url,
        method=method,
        headers=request_headers,
        body=body,
        timeout=timeout,
        label=label,
        sleep=sleep,
    )
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise TransportError(f"{label} returned a non-JSON response") from exc
