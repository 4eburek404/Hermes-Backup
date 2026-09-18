"""Internal route inference helpers for booking URLs."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from flight_calendar.errors import CliFailure


def read_private_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise CliFailure(f"input file not found: {path}", code="usage_error") from exc


def first_url_from_args(args: argparse.Namespace) -> str | None:
    url = getattr(args, "url", None)
    url_file = getattr(args, "url_file", None)
    if url:
        return url
    if url_file:
        text = read_private_text(url_file)
        if not text:
            raise CliFailure(f"url file is empty: {url_file}", code="usage_error")
        return text.splitlines()[0].strip()
    return url


def _query_field_names(parsed: Any) -> list[str]:
    names = list(parse_qs(parsed.query, keep_blank_values=True).keys())
    fragment = parsed.fragment or ""
    if "?" in fragment:
        names.extend(parse_qs(fragment.split("?", 1)[1], keep_blank_values=True).keys())
    return list(dict.fromkeys(names))


def _field_present(field_names: list[str], aliases: set[str]) -> bool:
    lower_names = {name.lower() for name in field_names}
    return any(alias.lower() in lower_names for alias in aliases)


def _trusted_route(parsed: Any) -> str | None:
    if parsed.scheme.lower() != "https":
        return None

    host = (parsed.hostname or "").lower()
    path = parsed.path
    if host == "www.aeroflot.ru" and path == "/sb/pnr/app/ru-ru":
        return "aeroflot"
    if host == "service.uralairlines.ru":
        return "ural"
    if host == "www.utair.ru" and path == "/order-manage":
        return "utair"
    if host == "flyredwings.com" and path == "/booking/":
        return "redwings"
    if host == "myb.s7.ru" and path == "/myb/manage-order":
        return "s7"
    return None


def _redwings_find_fragment(fragment: str) -> bool:
    return bool(
        re.match(r"^/?find/[^/]+/[^/]+/Submit/?$", fragment, flags=re.IGNORECASE)
    )


def _redwings_order_fragment(fragment: str) -> bool:
    return bool(re.match(r"^/?booking/[^/]+/order/?$", fragment, flags=re.IGNORECASE))


def _aeroflot_has_required_credentials(field_names: list[str]) -> bool:
    return (
        _field_present(field_names, {"pnrKey"})
        and _field_present(field_names, {"pnrLocator"})
    ) or (
        _field_present(field_names, {"pnr_key"})
        and _field_present(field_names, {"pnr_locator"})
    )


def _ural_has_required_credentials(field_names: list[str]) -> bool:
    return _field_present(
        field_names, {"pnr", "pnrNumber", "pnrnumber"}
    ) and _field_present(field_names, {"lastName", "lastname", "surname"})


def _utair_has_required_credentials(field_names: list[str]) -> bool:
    locator_aliases = {"rloc", "pnr"}
    surname_aliases = {"last_name", "lastName", "lastname", "surname"}
    return _field_present(field_names, locator_aliases) and _field_present(
        field_names, surname_aliases
    )


def _s7_has_required_credentials(field_names: list[str]) -> bool:
    return _field_present(
        field_names, {"bookingId", "booking_id"}
    ) and _field_present(field_names, {"passengerId", "passenger_id"})


def _route_has_required_credentials(
    route: str, field_names: list[str], fragment: str
) -> bool:
    if route == "aeroflot":
        return _aeroflot_has_required_credentials(field_names)
    if route == "ural":
        return _ural_has_required_credentials(field_names)
    if route == "utair":
        return _utair_has_required_credentials(field_names)
    if route == "redwings":
        return _redwings_find_fragment(fragment)
    if route == "s7":
        return _s7_has_required_credentials(field_names)
    return False


def _route_input_insufficient(route: str, message: str | None = None) -> CliFailure:
    default_message = f"{route} source fingerprint is known, but required route-specific credentials are missing"
    return CliFailure(
        message or default_message,
        code="route_input_insufficient",
    )


def infer_build_route(
    args: argparse.Namespace, *, url_override: str | None = None
) -> dict[str, str]:
    url = url_override if url_override is not None else first_url_from_args(args)
    if not url:
        raise CliFailure(
            "could not infer carrier route from safe source fingerprint",
            code="route_unknown",
        )

    parsed = urlparse(url)
    route = _trusted_route(parsed)
    if route is None:
        raise CliFailure(
            "could not infer carrier route from safe source fingerprint",
            code="route_unknown",
        )

    field_names = _query_field_names(parsed)
    fragment = parsed.fragment or ""
    if _route_has_required_credentials(route, field_names, fragment):
        return {"route": route}

    if route == "redwings" and _redwings_order_fragment(fragment):
        raise _route_input_insufficient(
            route,
            "Red Wings order page URL is not enough; provide the direct find link shaped #/find/<PNR>/<ACCESS_KEY>/Submit.",
        )
    raise _route_input_insufficient(route)
