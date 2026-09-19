"""Safe redirect resolution for Utair booking-link wrappers."""

from __future__ import annotations

from urllib.parse import urlparse

from flight_calendar import carrier_http
from flight_calendar.errors import CliFailure
from flight_calendar.route_detection import trusted_route

UTAIR_REDIRECT_HOSTS = {"click.mail.utair.io"}


def _hostname(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _is_utair_carrier_url(url: str) -> bool:
    return trusted_route(url) == "utair"


def resolve_utair_booking_redirect(raw_url: str) -> str:
    """Resolve the allowlisted Utair redirect and validate the carrier host.

    Unknown hosts are not fetched: they remain ordinary carrier URLs for route
    detection. Known Utair mail-click links must resolve to ``utair.ru`` or a
    subdomain before the URL is trusted for route detection or adapter parsing.
    """
    host = _hostname(raw_url)
    if host not in UTAIR_REDIRECT_HOSTS:
        return raw_url
    if urlparse(raw_url).scheme.lower() != "https":
        raise CliFailure(
            "known booking redirect must use HTTPS; provide the direct carrier booking URL",
            code="redirect_resolution_failed",
        )

    try:
        final_url = carrier_http.resolve_redirect_url(
            raw_url, label="known booking redirect"
        )
    except carrier_http.TransportError as exc:
        raise CliFailure(
            "known booking redirect could not be resolved; provide the direct carrier booking URL",
            code="redirect_resolution_failed",
        ) from exc

    if not _is_utair_carrier_url(final_url):
        raise CliFailure(
            "known booking redirect resolved to an unsupported carrier host; provide the direct carrier booking URL",
            code="redirect_resolution_failed",
        )
    return final_url
