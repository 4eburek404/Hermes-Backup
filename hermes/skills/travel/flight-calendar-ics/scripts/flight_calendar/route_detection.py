"""Internal route inference helpers for booking URLs."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from flight_calendar.errors import CliFailure


def read_private_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise CliFailure("input file not found", code="usage_error") from exc


def first_url_from_args(args: argparse.Namespace) -> str | None:
    url = getattr(args, "url", None)
    url_file = getattr(args, "url_file", None)
    if url:
        return url
    if url_file:
        text = read_private_text(url_file)
        if not text:
            raise CliFailure("url file is empty", code="usage_error")
        return text.splitlines()[0].strip()
    return url


def trusted_route(url: str) -> str | None:
    """Return the carrier for a trusted scheme/host/path fingerprint only."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path
    if parsed.scheme.lower() != "https":
        return None
    if host == "www.aeroflot.ru" and path == "/sb/pnr/app/ru-ru":
        return "aeroflot"
    if (
        host == "service.uralairlines.ru"
        and parsed.netloc.lower() == "service.uralairlines.ru"
        and path in {"", "/", "/services"}
    ):
        return "ural"
    if host == "www.utair.ru" and path == "/order-manage":
        return "utair"

    if host == "flyredwings.com" and path == "/booking/":
        return "redwings"
    if host == "myb.s7.ru" and path == "/myb/manage-order":
        return "s7"
    return None


def infer_build_route(
    args: argparse.Namespace, *, url_override: str | None = None
) -> dict[str, str]:
    url = url_override if url_override is not None else first_url_from_args(args)
    if not url:
        raise CliFailure(
            "could not infer carrier route from safe source fingerprint",
            code="route_unknown",
        )
    route = trusted_route(url)
    if route is None:
        raise CliFailure(
            "could not infer carrier route from safe source fingerprint",
            code="route_unknown",
        )
    return {"route": route}
