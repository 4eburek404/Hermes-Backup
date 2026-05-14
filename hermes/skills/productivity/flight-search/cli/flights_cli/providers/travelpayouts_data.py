from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .. import __version__
from ..config import CACHE_NOTE, DEFAULT_CURRENCY, SUPPORTED_CURRENCIES
from ..domain.normalize import normalize_iata, price_value
from ..errors import CliError

DATA_API_BASE_URL = "https://api.travelpayouts.com/aviasales/v3"
PRICES_FOR_DATES_URL = f"{DATA_API_BASE_URL}/prices_for_dates"
GROUPED_PRICES_URL = f"{DATA_API_BASE_URL}/grouped_prices"
YEAR_MONTH_OR_DATE_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")


def normalize_period(value: str, name: str) -> str:
    raw = value.strip()
    if not YEAR_MONTH_OR_DATE_RE.match(raw):
        raise CliError(f"{name} must be YYYY-MM or YYYY-MM-DD", error_type="validation_error")
    return raw


def normalize_currency(value: str | None) -> str:
    currency = (value or DEFAULT_CURRENCY).upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise CliError(f"currency must be one of {', '.join(sorted(SUPPORTED_CURRENCIES))}", error_type="validation_error")
    return currency


def bool_param(value: bool) -> str:
    return "true" if value else "false"


SENSITIVE_QUERY_KEYS = frozenset({"api_key", "access_token", "authorization", "cookie", "password", "secret", "token"})


def clean_params(params: dict[str, Any]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            cleaned[key] = bool_param(value)
        else:
            cleaned[key] = str(value)
    return cleaned


def validate_public_query_params(params: dict[str, str]) -> None:
    blocked = sorted(key for key in params if key.strip().lower() in SENSITIVE_QUERY_KEYS)
    if blocked:
        names = ", ".join(blocked)
        raise CliError(
            f"Travelpayouts Data API query params must not include credential fields ({names}); use TRAVELPAYOUTS_TOKEN",
            error_type="validation_error",
        )


def request_payload(endpoint: str, params: dict[str, str]) -> dict[str, Any]:
    validate_public_query_params(params)
    auth_status = "present" if os.getenv("TRAVELPAYOUTS_TOKEN") else "missing"
    return {
        "method": "GET",
        "endpoint": endpoint,
        "params": params,
        "auth": {"status": auth_status, "transport": "header"},
    }


def normalize_data_api_item(item: dict[str, Any]) -> dict[str, Any]:
    link = item.get("link")
    if isinstance(link, str) and link.startswith("/"):
        link = f"https://www.aviasales.com{link}"
    return {
        "origin": item.get("origin"),
        "destination": item.get("destination"),
        "origin_airport": item.get("origin_airport"),
        "destination_airport": item.get("destination_airport"),
        "departure_at": item.get("departure_at"),
        "return_at": item.get("return_at"),
        "price": price_value(item),
        "currency": item.get("currency"),
        "airline": item.get("airline"),
        "flight_number": item.get("flight_number"),
        "transfers": item.get("transfers"),
        "return_transfers": item.get("return_transfers"),
        "duration": item.get("duration"),
        "duration_to": item.get("duration_to"),
        "duration_back": item.get("duration_back"),
        "link": link,
    }


def data_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return [item for item in payload["data"] if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def call_data_api(endpoint: str, params: dict[str, str], *, timeout: int) -> tuple[int, Any]:
    validate_public_query_params(params)
    token = os.getenv("TRAVELPAYOUTS_TOKEN")
    if not token:
        raise CliError("TRAVELPAYOUTS_TOKEN is required for --fetch", error_type="missing_credentials")
    url = f"{endpoint}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "X-Access-Token": token,
            "User-Agent": f"flights-cli/{__version__}",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:1000]
        raise CliError(f"Travelpayouts Data API HTTP {exc.code}: {body}", error_type="upstream_error") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise CliError(f"Travelpayouts Data API request failed: {type(exc).__name__}", error_type="upstream_error") from exc


def build_prices_for_dates_params(args: argparse.Namespace) -> dict[str, str]:
    origin = normalize_iata(args.origin, "origin")
    destination = normalize_iata(args.destination, "destination")
    currency = normalize_currency(args.currency)
    params = clean_params(
        {
            "origin": origin,
            "destination": destination,
            "departure_at": normalize_period(args.departure_at, "departure-at"),
            "return_at": normalize_period(args.return_at, "return-at") if args.return_at else None,
            "one_way": bool(getattr(args, "one_way", False) or not args.return_at),
            "direct": bool(args.direct),
            "market": args.market,
            "limit": max(1, int(args.limit)),
            "page": max(1, int(args.page)),
            "sorting": args.sorting,
            "unique": bool(args.unique),
            "currency": currency,
        }
    )
    return params


def run_prices_for_dates(args: argparse.Namespace) -> dict[str, Any]:
    params = build_prices_for_dates_params(args)
    result: dict[str, Any] = {
        "dry_run": not args.fetch,
        "advisory_only": True,
        "cache_note": CACHE_NOTE,
        "request": request_payload(PRICES_FOR_DATES_URL, params),
    }
    if not args.fetch:
        return result

    status, payload = call_data_api(PRICES_FOR_DATES_URL, params, timeout=args.timeout)
    items = data_items(payload)
    result["fetched"] = {
        "status": status,
        "success": payload.get("success") if isinstance(payload, dict) else None,
        "raw_count": len(items),
        "tickets": [normalize_data_api_item(item) for item in items[: args.limit]],
        "response": payload,
    }
    return result


def build_grouped_prices_params(args: argparse.Namespace) -> dict[str, str]:
    origin = normalize_iata(args.origin, "origin")
    destination = normalize_iata(args.destination, "destination")
    currency = normalize_currency(args.currency)
    params = clean_params(
        {
            "origin": origin,
            "destination": destination,
            "group_by": args.group_by,
            "departure_at": normalize_period(args.departure_at, "departure-at"),
            "return_at": normalize_period(args.return_at, "return-at") if args.return_at else None,
            "direct": bool(args.direct),
            "market": args.market,
            "min_trip_duration": args.min_trip_duration,
            "max_trip_duration": args.max_trip_duration,
            "currency": currency,
        }
    )
    return params


def run_grouped_prices(args: argparse.Namespace) -> dict[str, Any]:
    params = build_grouped_prices_params(args)
    result: dict[str, Any] = {
        "dry_run": not args.fetch,
        "advisory_only": True,
        "cache_note": CACHE_NOTE,
        "request": request_payload(GROUPED_PRICES_URL, params),
    }
    if not args.fetch:
        return result

    status, payload = call_data_api(GROUPED_PRICES_URL, params, timeout=args.timeout)
    items = data_items(payload)
    result["fetched"] = {
        "status": status,
        "success": payload.get("success") if isinstance(payload, dict) else None,
        "raw_count": len(items),
        "groups": items,
        "response": payload,
    }
    return result
