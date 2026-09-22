"""Offline HTTP replay used only inside the isolated flight-calendar eval skill."""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse


class TransportError(ValueError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class TransportResponse:
    status_code: int
    content_type: str
    text: str
    url: str
    headers: dict[str, str]


def _fixture_text() -> str:
    path = Path(os.environ["FLIGHT_CALENDAR_EVAL_HTTP_FIXTURE"])
    return path.read_text(encoding="utf-8")


def _scenario() -> str:
    return os.environ.get("FLIGHT_CALENDAR_EVAL_SCENARIO", "")


def _ural_response(url: str, *, method: str) -> tuple[int, str, str]:
    if method != "GET":
        raise TransportError("recorded Ural replay supports GET only")
    parsed = urlparse(url)
    if parsed.path in {"", "/"} and parsed.netloc == "service.uralairlines.ru":
        return (
            200,
            "text/html",
            '<html><head><script src="/12345/js/app.synthetic.js"></script>'
            '<link href="/12345/css/app.synthetic.css"></head><body></body></html>',
        )
    if parsed.path == "/12345/env/env.json" and parsed.netloc == "service.uralairlines.ru":
        return (
            200,
            "application/json",
            json.dumps(
                {
                    "API_URL": "https://ural-api.test/api/",
                    "API_KEY": "synthetic-api-key-001",
                }
            ),
        )
    if parsed.netloc == "ural-api.test" and parsed.path == "/api/settings/CurrentDateUtc":
        return 200, "text/plain", "1700000000"
    if parsed.netloc == "ural-api.test" and parsed.path == "/api/Reservation":
        return 200, "application/json", _fixture_text()
    raise TransportError(f"recorded Ural replay does not provide endpoint: {parsed.path}")


def browser_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": "Hermes-Eval-Replay",
        "Accept": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


def request_raw(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: int = 45,
    label: str = "HTTP request",
    sleep: object = None,
) -> tuple[int, str, str]:
    del headers, body, timeout, label, sleep
    if _scenario() == "ural-url-success":
        return _ural_response(url, method=method)
    if _scenario() == "url-success":
        return 200, "application/json; charset=utf-8", _fixture_text()
    raise TransportError("recorded eval does not provide live HTTP")


def request_text(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: int = 45,
    label: str = "HTTP request",
    sleep: object = None,
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
            f"{label} returned HTTP {status} ({content_type})", status_code=status
        )
    return text


def request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | list[Any] | None = None,
    form_body: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: int = 45,
    label: str = "HTTP request",
    sleep: object = None,
) -> Any:
    del json_body, form_body
    text = request_text(
        url,
        method=method,
        headers=headers,
        body=body,
        timeout=timeout,
        label=label,
        sleep=sleep,
    )
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise TransportError(f"{label} returned a non-JSON response") from exc


def resolve_redirect_url(*args: Any, **kwargs: Any) -> str:
    del args, kwargs
    raise TransportError("recorded eval does not provide redirect replay")


@contextmanager
def open_session() -> Iterator[Any]:
    raise TransportError("recorded eval does not provide session replay")
    yield None


def request_session_raw(*args: Any, **kwargs: Any) -> TransportResponse:
    del args, kwargs
    raise TransportError("recorded eval does not provide session replay")
