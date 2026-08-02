from __future__ import annotations

import gzip
import json
import urllib.error
import urllib.request
from typing import Any

from ..config import KUPIBILET_FRONTEND_SEARCH_URL, KUPIBILET_HEADERS
from ..errors import CliError


def build_kupibilet_payload(
    origin: str, destination: str, depart_date: str, currency: str
) -> dict[str, Any]:
    return {
        "trips": [{"departure": origin, "arrival": destination, "date": depart_date}],
        "travelers": {"adult": 1, "child": 0, "infant": 0},
        "cabin": "economy",
        "agent": "kupibilet",
        "lang": "ru",
        "currency": currency,
        "client_platform": "web",
        "filters": {},
        "sort_by": "price",
        "short_response": False,
    }


def decode_http_body(raw: bytes, content_encoding: str | None) -> bytes:
    encoding = (content_encoding or "").split(";", 1)[0].strip().lower()
    if encoding == "gzip":
        return gzip.decompress(raw)
    return raw


def post_kupibilet_search(
    payload: dict[str, Any], *, timeout: int
) -> tuple[dict[str, Any], int]:
    """Perform only the Kupibilet HTTP protocol exchange."""

    request = urllib.request.Request(
        KUPIBILET_FRONTEND_SEARCH_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=KUPIBILET_HEADERS,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            decoded = decode_http_body(raw, response.headers.get("Content-Encoding"))
            data = json.loads(decoded.decode("utf-8"))
            if not isinstance(data, dict):
                raise CliError(
                    "Kupibilet response must be a JSON object",
                    error_type="upstream_error",
                )
            return data, int(response.status)
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")[:1000]
        raise CliError(
            f"Kupibilet HTTP {exc.code}: {body_text}",
            error_type="upstream_error",
            details={
                "http_status": exc.code,
                "retry_after": exc.headers.get("Retry-After"),
            },
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise CliError(
            f"Kupibilet request failed: {type(exc).__name__}: {exc}",
            error_type="upstream_error",
        ) from exc


__all__ = [
    "build_kupibilet_payload",
    "decode_http_body",
    "post_kupibilet_search",
]
