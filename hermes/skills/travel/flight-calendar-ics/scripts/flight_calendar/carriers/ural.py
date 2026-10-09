#!/usr/bin/env python3
"""Fetch Ural Airlines manage-booking data and convert it to itinerary JSON."""

from __future__ import annotations

import base64
import json
import math
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlparse

from flight_calendar import carrier_http
from flight_calendar.errors import CliFailure


URAL_SERVICE_BASE = "https://service.uralairlines.ru/"
URAL_MAIL_WRAPPER_HOST = "tn-hgl.mckx.ru"
URAL_CONFIG_FILENAME = "ural-deployment.json"
URAL_CONFIG_CACHE_DIR = Path.home() / ".hermes" / "cache" / "flight-calendar-ics"
TIME_BUCKET_MS = 60_000
TIME_SEED_PREFIX = "dkhm83gfnm"


@dataclass(frozen=True)
class DeploymentConfig:
    version: str
    api_url: str
    api_key: str
    from_cache: bool = False


def http_text(
    url: str, *, timeout: int = 45, headers: dict[str, str] | None = None
) -> str:
    return carrier_http.request_text(
        url,
        headers={"Accept": "*/*", **(headers or {})},
        timeout=timeout,
        label="Ural Airlines frontend/API",
    )


def http_json(
    url: str,
    *,
    method: str = "GET",
    timeout: int = 45,
    headers: dict[str, str] | None = None,
) -> Any:
    return carrier_http.request_json(
        url,
        method=method,
        headers={"Accept": "application/json", **(headers or {})},
        timeout=timeout,
        label="Ural Airlines API",
    )


def _unwrap_ural_source(raw_url: str) -> str:
    """Unwrap the supported Ural mail source; leave direct URLs unchanged."""
    source = raw_url.strip()
    wrapper = urlparse(source)
    if (wrapper.hostname or "").lower() != URAL_MAIL_WRAPPER_HOST:
        return source

    if (
        wrapper.scheme.lower() != "https"
        or wrapper.netloc.lower() != URAL_MAIL_WRAPPER_HOST
        or re.search(r"%(?![0-9a-fA-F]{2})", wrapper.query)
    ):
        raise CliFailure(
            "Ural Airlines mail source is invalid",
            code="route_input_insufficient",
        )

    try:
        parameters = parse_qsl(
            wrapper.query,
            keep_blank_values=True,
            strict_parsing=True,
            encoding="utf-8",
            errors="strict",
        )
    except (UnicodeDecodeError, ValueError):
        raise CliFailure(
            "Ural Airlines mail source is invalid",
            code="route_input_insufficient",
        ) from None

    if len(parameters) != 1 or parameters[0][0] != "u" or not parameters[0][1]:
        raise CliFailure(
            "Ural Airlines mail source is invalid",
            code="route_input_insufficient",
        )

    target = parameters[0][1].strip()
    parsed_target = urlparse(target)
    if (
        parsed_target.scheme.lower() != "https"
        or parsed_target.netloc.lower() != "service.uralairlines.ru"
        or parsed_target.path not in {"", "/", "/services"}
    ):
        raise CliFailure(
            "Ural Airlines mail source has an unsupported destination",
            code="route_input_insufficient",
        )
    return target


def parse_ural_source(url: str) -> tuple[str, str, str]:
    booking_url = _unwrap_ural_source(url)
    parsed = urlparse(booking_url)
    qs = parse_qs(parsed.query)
    pnr = (qs.get("pnr") or qs.get("pnrNumber") or qs.get("pnrnumber") or [None])[0]
    last_name = (
        qs.get("lastName") or qs.get("lastname") or qs.get("surname") or [None]
    )[0]
    if not pnr or not last_name:
        raise CliFailure(
            "Ural Airlines booking URL is missing required credentials",
            code="route_input_insufficient",
        )
    locator = pnr.strip().upper()
    surname = last_name.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{5,8}", locator):
        raise ValueError("Ural Airlines PNR format looks invalid")
    if not re.fullmatch(r"[A-ZА-ЯЁ' -]{2,80}", surname, flags=re.IGNORECASE):
        raise ValueError("Ural Airlines last name format looks invalid")
    canonical_url = (
        URAL_SERVICE_BASE.rstrip("/")
        + "/services?"
        + urlencode({"pnr": locator, "lastName": surname})
    )
    return locator, surname, canonical_url


def _config_cache_path() -> Path:
    override = os.environ.get("FLIGHT_CALENDAR_CACHE_DIR")
    cache_dir = Path(override).expanduser() if override and override.strip() else URAL_CONFIG_CACHE_DIR
    return cache_dir / URAL_CONFIG_FILENAME


def _valid_config(version: Any, api_url: Any, api_key: Any) -> DeploymentConfig:
    if (
        not isinstance(version, str)
        or not re.fullmatch(r"\d+", version)
        or not isinstance(api_url, str)
        or not isinstance(api_key, str)
        or not api_key
    ):
        raise ValueError("Ural Airlines deployment configuration is invalid")
    parsed = urlparse(api_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Ural Airlines deployment configuration is invalid")
    return DeploymentConfig(version, api_url.rstrip("/") + "/", api_key)


def _load_cached_config() -> DeploymentConfig | None:
    try:
        path = _config_cache_path()
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            return None
        config = _valid_config(
            document.get("version"), document.get("API_URL"), document.get("API_KEY")
        )
        _secure_cache_permissions(path)
        return DeploymentConfig(config.version, config.api_url, config.api_key, from_cache=True)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return None


def _secure_cache_permissions(path: Path) -> None:
    try:
        os.chmod(path.parent, 0o700)
        os.chmod(path, 0o600)
    except OSError as exc:
        raise ValueError("Ural Airlines deployment configuration is unavailable") from exc


def _save_config(config: DeploymentConfig) -> None:
    path = _config_cache_path()
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(path.parent, 0o700)
        temporary.write_text(
            json.dumps(
                {
                    "version": config.version,
                    "API_URL": config.api_url,
                    "API_KEY": config.api_key,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        _secure_cache_permissions(path)
    except OSError as exc:
        raise ValueError("Ural Airlines deployment configuration is unavailable") from exc


def _deployment_version(html: str) -> str:
    asset_paths = re.findall(r"(?:src|href)=[\"']?([^\"'\s>]+)", html)
    for path in asset_paths:
        match = re.search(r"/(\d+)/(?:js/|css/|env/|[^/]+)", path)
        if match:
            return match.group(1)
    raise ValueError("Ural Airlines deployment configuration is invalid")


def _discover_config(frontend_base: str, *, timeout: int) -> DeploymentConfig:
    base = frontend_base.rstrip("/") + "/"
    version = _deployment_version(http_text(base, timeout=timeout, headers={"Accept": "text/html"}))
    env = http_json(
        urljoin(base, f"/{version}/env/env.json"),
        timeout=timeout,
    )
    if not isinstance(env, dict):
        raise ValueError("Ural Airlines deployment configuration is invalid")
    return _valid_config(version, env.get("API_URL"), env.get("API_KEY"))


def load_deployment_config(
    frontend_base: str | None = None,
    *,
    timeout: int = 45,
    refresh: bool = False,
) -> DeploymentConfig:
    """Return cached deployment config, refreshing only on miss or explicit request."""
    if not refresh:
        cached = _load_cached_config()
        if cached is not None:
            return cached
    base = frontend_base or URAL_SERVICE_BASE
    config = _discover_config(base, timeout=timeout)
    _save_config(config)
    return config


def compute_timestamp_diff(api_url: str, *, timeout: int = 45) -> int:
    """Synchronize the local clock against the carrier server in milliseconds."""
    try:
        server_seconds = http_json(
            urljoin(api_url.rstrip("/") + "/", "settings/CurrentDateUtc"),
            timeout=timeout,
        )
        return int(float(server_seconds) * 1000 - time.time() * 1000)
    except Exception:
        return 0


def _base64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def generate_api_key_header(
    api_key: str, timestamp_ms: int, timestamp_diff_ms: int = 0
) -> str:
    """Generate the deterministic public Ural X-Api-Key value locally."""
    try:
        key = api_key.encode("latin-1")
    except UnicodeEncodeError as exc:
        raise ValueError("Ural Airlines deployment configuration is invalid") from exc
    if not key:
        raise ValueError("Ural Airlines deployment configuration is invalid")

    corrected_ms = int(timestamp_ms) + int(timestamp_diff_ms)
    minute_index = math.floor(corrected_ms / TIME_BUCKET_MS)
    time_unit = f"{TIME_SEED_PREFIX}{minute_index}".encode("ascii")
    repeat_count = 5 + (minute_index % 5)
    time_b64 = _base64(time_unit * repeat_count)

    output_len = len(_base64(key))
    if len(time_b64) < output_len:
        time_b64 += "Z" * (output_len - len(time_b64))
    mask = time_b64[: len(key)].encode("ascii")
    transformed = bytes(value ^ mask[index] for index, value in enumerate(key))
    key_b64 = _base64(transformed)
    return "".join(key_b64[index] + time_b64[index] for index in range(output_len))


def api_headers(api_key_header: str) -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Content-Type": "application/json",
        "Origin": URAL_SERVICE_BASE.rstrip("/"),
        "Referer": URAL_SERVICE_BASE,
        "Cache-Control": "no-cache",
        "X-Api-Key": api_key_header,
    }


def fetch_ural_reservation(
    locator: str,
    last_name: str,
    *,
    booking_url: str | None = None,
    frontend_base: str | None = None,
    timeout: int = 45,
) -> dict[str, Any]:
    if not frontend_base and booking_url:
        parsed = urlparse(booking_url)
        if parsed.scheme and parsed.netloc:
            frontend_base = f"{parsed.scheme}://{parsed.netloc}/"
    config = load_deployment_config(frontend_base, timeout=timeout)
    query = urlencode({"pnrNumber": locator, "lastName": last_name})

    def request_reservation(current_config: DeploymentConfig) -> Any:
        timestamp_diff = compute_timestamp_diff(current_config.api_url, timeout=timeout)
        api_key_header = generate_api_key_header(
            current_config.api_key, int(time.time() * 1000), timestamp_diff
        )
        return http_json(
            current_config.api_url + "Reservation?" + query,
            method="GET",
            timeout=timeout,
            headers=api_headers(api_key_header),
        )

    try:
        reservation = request_reservation(config)
    except carrier_http.TransportError as exc:
        if not config.from_cache or exc.status_code != 401:
            raise
        config = load_deployment_config(frontend_base, timeout=timeout, refresh=True)
        reservation = request_reservation(config)
    return _accept_reservation(reservation)


def _accept_reservation(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict) or response.get("success") is not True:
        raise ValueError("Ural Airlines Reservation response was not successful")

    data = response.get("data")
    if not isinstance(data, dict):
        raise ValueError("Ural Airlines Reservation response is invalid")

    journey = data.get("journey")
    if not isinstance(journey, dict):
        raise ValueError("Ural Airlines Reservation response is invalid")

    groups = ("outboundFlights", "returnFlights", "separateFlights")
    segments: list[dict[str, Any]] = []
    for group in groups:
        if group not in journey:
            continue
        group_segments = journey[group]
        if not isinstance(group_segments, list):
            raise ValueError("Ural Airlines Reservation response is invalid")
        for segment in group_segments:
            if not isinstance(segment, dict):
                raise ValueError("Ural Airlines Reservation response is invalid")
            segments.append(segment)

    required_fields = ("origin", "destination", "departureDate", "arrivalDate", "flightNumber")
    for segment in segments:
        if any(
            not isinstance(segment.get(field), str) or not segment[field].strip()
            for field in required_fields
        ):
            raise ValueError("Ural Airlines Reservation response is invalid")
        if not any(
            isinstance(segment.get(field), str) and segment[field].strip()
            for field in ("marketingCarrier", "operatingCarrier")
        ):
            raise ValueError("Ural Airlines Reservation response is invalid")

    if not segments:
        raise ValueError("Ural Airlines Reservation response is invalid")

    for field in ("passengers", "tickets"):
        if field not in data:
            continue
        collection = data[field]
        if not isinstance(collection, list) or any(
            not isinstance(item, dict) for item in collection
        ):
            raise ValueError("Ural Airlines Reservation response is invalid")

    return response


def build_itinerary(booking_url: str) -> dict[str, Any]:
    locator, last_name, canonical_url = parse_ural_source(booking_url)
    reservation = fetch_ural_reservation(locator, last_name, booking_url=canonical_url)
    return convert_to_itinerary(reservation["data"], booking_url=canonical_url)


def clean(value: Any) -> Any:
    return None if value in (None, "", []) else value


def local_datetime(value: Any) -> str:
    text = str(value or "").replace(" ", "T")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00", text):
        return text[:-3]
    return text


def passenger_names(data: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for pax in data.get("passengers") or []:
        parts = [pax.get("surname"), pax.get("firstName")]
        name = " ".join(str(item).strip() for item in parts if clean(item))
        if name:
            names.append(name)
    return names


def ticket_numbers(data: dict[str, Any]) -> list[str]:
    numbers: list[str] = []
    for ticket in data.get("tickets") or []:
        number = (
            clean(ticket.get("number")) if isinstance(ticket, dict) else clean(ticket)
        )
        if number:
            numbers.append(str(number))
    return sorted(dict.fromkeys(numbers))


def convert_to_itinerary(
    data: dict[str, Any],
    booking_url: str | None = None,
) -> dict[str, Any]:
    flights: list[dict[str, Any]] = []
    journey = data["journey"]
    flight_groups = [
        ("outbound", journey.get("outboundFlights") or []),
        ("return", journey.get("returnFlights") or []),
        ("separate", journey.get("separateFlights") or []),
    ]

    for _group_name, group_flights in flight_groups:
        for seg in group_flights:
            dep_code = str(seg.get("origin") or "").upper()
            arr_code = str(seg.get("destination") or "").upper()

            marketing = str(
                seg.get("marketingCarrier") or seg.get("operatingCarrier") or "U6"
            ).upper()
            raw_flight_number = str(seg.get("flightNumber") or "").strip()
            flight_number = f"{marketing} {raw_flight_number}".strip()
            flight: dict[str, Any] = {
                "flight_number": flight_number,
                "departure": {
                    "airport": dep_code,
                    "local": local_datetime(seg.get("departureDate")),
                },
                "arrival": {
                    "airport": arr_code,
                    "local": local_datetime(seg.get("arrivalDate")),
                },
            }
            aircraft = clean(seg.get("aircraft"))
            if aircraft:
                flight["aircraft"] = str(aircraft)
            flights.append(flight)

    if not flights:
        raise ValueError("no flight segments found in Ural Airlines response")

    itinerary: dict[str, Any] = {
        "flights": flights,
    }
    pnr = clean(data.get("number"))
    passengers = passenger_names(data)
    tickets = ticket_numbers(data)
    if pnr:
        itinerary["pnr"] = str(pnr)
    if passengers:
        itinerary["passenger"] = passengers[0]
    if tickets:
        itinerary["ticket_number"] = ", ".join(tickets)
    if booking_url:
        itinerary["booking_url"] = booking_url
    return itinerary
