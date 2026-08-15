from __future__ import annotations

import json
from typing import Any

import httpx2

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


def post_kupibilet_search(
    payload: dict[str, Any], *, timeout: int
) -> tuple[dict[str, Any], int]:
    """Perform only the Kupibilet HTTP protocol exchange."""

    try:
        with httpx2.Client(timeout=timeout, follow_redirects=False) as client:
            response = client.post(
                KUPIBILET_FRONTEND_SEARCH_URL,
                content=json.dumps(payload).encode("utf-8"),
                headers=KUPIBILET_HEADERS,
            )
            if response.status_code in {301, 302, 303}:
                redirect_request = response.next_request
                if redirect_request is not None:
                    redirect_request.headers.pop("Content-Type", None)
                    redirect_request.headers.pop("Content-Length", None)
                    response = client.send(redirect_request, follow_redirects=True)

            if not response.is_success:
                body_text = response.content.decode("utf-8", errors="replace")[:1000]
                raise CliError(
                    f"Kupibilet HTTP {response.status_code}: {body_text}",
                    error_type="upstream_error",
                    details={
                        "http_status": response.status_code,
                        "retry_after": response.headers.get("Retry-After"),
                    },
                )

            data = json.loads(response.content.decode("utf-8"))
            if not isinstance(data, dict):
                raise CliError(
                    "Kupibilet response must be a JSON object",
                    error_type="upstream_error",
                )
            return data, int(response.status_code)
    except (httpx2.RequestError, TimeoutError, json.JSONDecodeError) as exc:
        raise CliError(
            f"Kupibilet request failed: {type(exc).__name__}: {exc}",
            error_type="upstream_error",
        ) from exc


__all__ = [
    "build_kupibilet_payload",
    "post_kupibilet_search",
]
