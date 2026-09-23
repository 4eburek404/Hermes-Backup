"""Normalize trusted URL wrappers before carrier route detection."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlparse

from flight_calendar.errors import CliFailure


MAIL_WRAPPER_HOST = "tn-hgl.mckx.ru"


def normalize_url_source(raw_url: str) -> str:
    """Return the embedded HTTPS URL for a known mail wrapper, otherwise input."""
    source = raw_url.strip()
    wrapper = urlparse(source)
    if (wrapper.hostname or "").lower() != MAIL_WRAPPER_HOST:
        return source

    if (
        wrapper.scheme.lower() != "https"
        or wrapper.netloc.lower() != MAIL_WRAPPER_HOST
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
