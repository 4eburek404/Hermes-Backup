"""Recorded HTTP boundary for the minimal flight-calendar agent eval.

This file replaces carrier_http.py only inside the isolated materialized skill
used by the eval. It never modifies the production branch.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


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
    del url, method, headers, body, timeout, label, sleep
    return 200, "application/json; charset=utf-8", _fixture_text()


def _unexpected(name: str) -> TransportError:
    return TransportError(f"recorded eval does not provide transport path: {name}")


def request_text(*args: Any, **kwargs: Any) -> str:
    del args, kwargs
    raise _unexpected("request_text")


def request_json(*args: Any, **kwargs: Any) -> Any:
    del args, kwargs
    raise _unexpected("request_json")


def resolve_redirect_url(*args: Any, **kwargs: Any) -> str:
    del args, kwargs
    raise _unexpected("resolve_redirect_url")


@contextmanager
def open_session() -> Iterator[Any]:
    raise _unexpected("open_session")
    yield None


def request_session_raw(*args: Any, **kwargs: Any) -> TransportResponse:
    del args, kwargs
    raise _unexpected("request_session_raw")
