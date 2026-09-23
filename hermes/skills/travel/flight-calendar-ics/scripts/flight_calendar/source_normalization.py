"""Normalize trusted URL wrappers before carrier route detection."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlparse

from flight_calendar import carrier_http
from flight_calendar.errors import CliFailure


EMBEDDED_URL_WRAPPER_HOST = "tn-hgl.mckx.ru"
REDIRECT_URL_WRAPPER_HOST = "click.mail.utair.io"


def normalize_url_source(raw_url: str) -> str:
    """Reveal one HTTPS destination from a known wrapper, otherwise input."""
    source = raw_url.strip()
    wrapper = urlparse(source)
    host = (wrapper.hostname or "").lower()

    if host == REDIRECT_URL_WRAPPER_HOST:
        if (
            wrapper.scheme.lower() != "https"
            or wrapper.netloc.lower() != REDIRECT_URL_WRAPPER_HOST
        ):
            raise CliFailure(
                "known booking redirect must use HTTPS",
                code="redirect_resolution_failed",
            )
        try:
            target = carrier_http.resolve_redirect_url(
                source,
                label="known booking redirect",
            )
        except carrier_http.TransportError as exc:
            raise CliFailure(
                "known booking redirect could not be resolved",
                code="redirect_resolution_failed",
            ) from exc

        parsed_target = urlparse(target)
        if (
            parsed_target.scheme.lower() != "https"
            or not parsed_target.hostname
            or parsed_target.username is not None
            or parsed_target.password is not None
        ):
            raise CliFailure(
                "known booking redirect has an invalid destination",
                code="redirect_resolution_failed",
            )
        return target

    if host != EMBEDDED_URL_WRAPPER_HOST:
        return source

    if (
        wrapper.scheme.lower() != "https"
        or wrapper.netloc.lower() != EMBEDDED_URL_WRAPPER_HOST
        or re.search(r"%(?![0-9a-fA-F]{2})", wrapper.query)
    ):
        raise CliFailure("booking URL wrapper is invalid", code="route_unknown")

    try:
        parameters = parse_qsl(
            wrapper.query,
            keep_blank_values=True,
            strict_parsing=True,
            encoding="utf-8",
            errors="strict",
        )
    except (UnicodeDecodeError, ValueError):
        raise CliFailure("booking URL wrapper is invalid", code="route_unknown") from None

    if (
        len(parameters) != 1
        or parameters[0][0] != "u"
        or not parameters[0][1]
    ):
        raise CliFailure("booking URL wrapper is invalid", code="route_unknown")

    target = parameters[0][1].strip()
    parsed_target = urlparse(target)
    if (
        parsed_target.scheme.lower() != "https"
        or not parsed_target.hostname
        or parsed_target.username is not None
        or parsed_target.password is not None
    ):
        raise CliFailure("booking URL wrapper target is invalid", code="route_unknown")

    return target
