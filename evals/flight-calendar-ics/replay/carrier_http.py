"""Offline HTTP replay used only inside the isolated flight-calendar eval skill."""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qs, urlparse


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


def _record_request(url: str, method: str, *, valid: bool, contract: str) -> None:
    path = os.environ.get("FLIGHT_CALENDAR_EVAL_HTTP_LOG")
    if not path:
        return
    parsed = urlparse(url)
    record = {
        "host": parsed.netloc.lower(),
        "path": parsed.path or "/",
        "method": method.upper(),
        "query_fields": sorted(parse_qs(parsed.query, keep_blank_values=True)),
        "contract": contract,
        "valid": valid,
    }
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _header_map(headers: dict[str, str] | None) -> dict[str, str]:
    return {str(key).lower(): str(value).strip() for key, value in (headers or {}).items()}


def _require_headers(headers: dict[str, str] | None, expected: dict[str, str]) -> bool:
    actual = _header_map(headers)
    return all(actual.get(name.lower()) == value for name, value in expected.items())


def _ural_response(
    url: str,
    *,
    method: str,
    headers: dict[str, str] | None,
    body: bytes | None,
) -> tuple[int, str, str]:
    parsed = urlparse(url)
    request_headers = _header_map(headers)
    query = parse_qs(parsed.query, keep_blank_values=True)
    valid = method.upper() == "GET" and body is None
    contract = "ural-frontend"
    if parsed.path in {"", "/"} and parsed.netloc == "service.uralairlines.ru":
        valid = valid and not query and request_headers.get("accept") == "text/html"
        _record_request(url, method, valid=valid, contract=contract)
        if not valid:
            raise TransportError("recorded Ural frontend request did not match")
        return (
            200,
            "text/html",
            '<html><head><script src="/12345/js/app.synthetic.js"></script>'
            '<link href="/12345/css/app.synthetic.css"></head><body></body></html>',
        )
    if parsed.path == "/12345/env/env.json" and parsed.netloc == "service.uralairlines.ru":
        contract = "ural-deployment-config"
        valid = valid and not query and "application/json" in request_headers.get("accept", "")
        _record_request(url, method, valid=valid, contract=contract)
        if not valid:
            raise TransportError("recorded Ural deployment request did not match")
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
        contract = "ural-clock"
        valid = valid and not query and "application/json" in request_headers.get("accept", "")
        _record_request(url, method, valid=valid, contract=contract)
        if not valid:
            raise TransportError("recorded Ural clock request did not match")
        return 200, "text/plain", "1700000000"
    if parsed.netloc == "ural-api.test" and parsed.path == "/api/Reservation":
        contract = "ural-reservation"
        valid = (
            valid
            and query == {"pnrNumber": ["ABC123"], "lastName": ["IVANOV"]}
            and request_headers.get("origin") == "https://service.uralairlines.ru"
            and request_headers.get("referer") == "https://service.uralairlines.ru/"
            and request_headers.get("user-agent") == "Mozilla/5.0"
            and "undefined" not in request_headers.get("x-api-key", "")
            and request_headers.get("content-type") == "application/json"
            and "application/json" in request_headers.get("accept", "")
        )
        _record_request(url, method, valid=valid, contract=contract)
        if not valid:
            raise TransportError("recorded Ural reservation request did not match")
        return 200, "application/json", _fixture_text()
    _record_request(url, method, valid=False, contract="unmatched")
    raise TransportError(f"recorded Ural replay does not provide endpoint: {parsed.path}")


def _aeroflot_response(
    url: str, *, method: str, headers: dict[str, str] | None, body: bytes | None
) -> tuple[int, str, str]:
    parsed = urlparse(url)
    document = json.loads(_fixture_text())
    data = document.get("data") if isinstance(document, dict) else {}
    expected = {
        "pnr_locator": str((data or {}).get("pnr_locator") or ""),
        "pnr_key": str((data or {}).get("pnr_key") or ""),
        "lang": "ru",
        "country": "ru",
    }
    try:
        submitted = json.loads((body or b"").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        submitted = None
    valid = (
        parsed.netloc == "www.aeroflot.ru"
        and parsed.path == "/se/api/app/pnr/view/v3"
        and method.upper() == "POST"
        and submitted == expected
        and _require_headers(
            headers,
            {
                "content-type": "application/json",
                "x-app-identity": "0",
                "origin": "https://www.aeroflot.ru",
                "referer": "https://www.aeroflot.ru/sb/pnr/app/ru-ru",
            },
        )
    )
    _record_request(url, method, valid=valid, contract="aeroflot-pnr-view-v3")
    if not valid:
        raise TransportError("recorded Aeroflot request did not match")
    return 200, "application/json; charset=utf-8", _fixture_text()


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
    del timeout, label, sleep
    if _scenario() == "ural-url-success":
        return _ural_response(url, method=method, headers=headers, body=body)
    if _scenario() == "url-success":
        return _aeroflot_response(url, method=method, headers=headers, body=body)
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
