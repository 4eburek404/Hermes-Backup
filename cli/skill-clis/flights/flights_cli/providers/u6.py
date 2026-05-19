from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any

from ..config import U6_CALENDAR_HEADERS, U6_CALENDAR_URL
from ..domain.normalize import normalize_iata, parse_iso_date, price_value
from ..errors import CliError

def run_u6_prices(args: argparse.Namespace) -> dict[str, Any]:
    """Fetch Ural Airlines (U6) price calendar and return structured data.

    Uses the public mobile_calendar endpoint (no auth required).
    Empty responses are NOT treated as errors — they indicate the calendar
    lacks coverage for this route.
    """
    origin = normalize_iata(args.origin, "origin")
    destination = normalize_iata(args.destination, "destination")
    from_date = parse_iso_date(args.from_date, "from-date")
    lang = getattr(args, "lang", "ru")
    selected_date = getattr(args, "selected_date", None)
    sort_by = getattr(args, "sort", "price")
    limit = getattr(args, "limit", 20)
    min_price = getattr(args, "min_price", None)
    max_price = getattr(args, "max_price", None)

    url_parts = [
        ("component", "schedule"),
        ("action", "mobile_calendar"),
        ("departureCityIata", origin),
        ("arrivalCityIata", destination),
        ("fromDate", from_date.isoformat()),
        ("lang", lang),
        ("updated", "true"),
        ("_", str(int(datetime.now().timestamp() * 1000))),
    ]
    url = U6_CALENDAR_URL + "?" + urllib.parse.urlencode(url_parts)

    request = urllib.request.Request(url, headers=U6_CALENDAR_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read()
            data = json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")[:500]
        raise CliError(f"U6 API HTTP {exc.code}: {body_text}", error_type="upstream_error") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise CliError(f"U6 API request failed: {type(exc).__name__}: {exc}", error_type="upstream_error") from exc

    return parse_u6_calendar(
        data,
        origin=origin,
        destination=destination,
        selected_date=selected_date,
        sort_by=sort_by,
        min_price=min_price,
        max_price=max_price,
        limit=limit,
    )


def parse_u6_calendar(
    raw_data: Any,
    origin: str,
    destination: str,
    *,
    selected_date: str | None = None,
    sort_by: str = "price",
    min_price: int | None = None,
    max_price: int | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Parse Ural Airlines mobile_calendar response into structured data.

    Returns daily minimum fares from the U6 price calendar. No flight numbers
    or times — those require a booking flow.

    Empty/absent data is NOT an error — just a signal that the calendar
    endpoint lacks coverage for this route (not "no flights exist").
    """
    empty_reason = None
    if not raw_data:
        empty_reason = "empty_body"
    elif not isinstance(raw_data, dict):
        empty_reason = "bad_body"
    elif not isinstance(raw_data.get("dates"), list) or not raw_data.get("dates"):
        empty_reason = "no_dates_key"

    if empty_reason:
        return {
            "ok": False,
            "empty": True,
            "empty_reason": empty_reason,
            "origin": origin,
            "destination": destination,
            "total_dates": 0,
            "priced_dates": 0,
            "unpriced_dates": 0,
            "stats": {"min": None, "max": None, "avg": None},
            "results": [],
            "cross_check_commands": [
                f"flights fli-search {origin} {destination} --depart-date {selected_date or 'YYYY-MM-DD'}",
                f"flights kb-search {origin} {destination} --depart-date {selected_date or 'YYYY-MM-DD'} --only-carrier U6",
            ],
            "note": "U6 price calendar returned no data for this route. Cross-check with aggregators.",
        }

    dates = raw_data.get("dates", [])
    final_date = raw_data.get("finalDate", "")

    priced: list[dict[str, Any]] = []
    for entry in dates:
        if not isinstance(entry, dict):
            continue
        d = str(entry.get("date") or "")
        p = entry.get("price")
        if not d or not isinstance(p, dict):
            continue
        amount = price_value({"price": p.get("price")})
        if amount is None:
            continue
        currency = p.get("code") if isinstance(p.get("code"), str) else "RUB"
        priced.append({
            "date": d,
            "price": amount,
            "currency": currency,
        })

    if selected_date:
        priced = [item for item in priced if item["date"] == selected_date]
    if min_price is not None:
        priced = [item for item in priced if item["price"] >= min_price]
    if max_price is not None:
        priced = [item for item in priced if item["price"] <= max_price]

    if sort_by == "price":
        priced.sort(key=lambda item: item["price"])
    elif sort_by == "date":
        priced.sort(key=lambda item: item["date"])

    results = priced[:limit]
    prices = [item["price"] for item in priced]

    return {
        "ok": True,
        "empty": False,
        "origin": origin,
        "destination": destination,
        "from_date": min((r["date"] for r in priced), default="") if not selected_date else selected_date,
        "final_date": final_date,
        "total_dates": len(dates),
        "priced_dates": len(priced),
        "unpriced_dates": len(dates) - len(priced),
        "stats": {
            "min": min(prices) if prices else None,
            "max": max(prices) if prices else None,
            "avg": round(sum(prices) / len(prices)) if prices else None,
        },
        "results": results,
        "cross_check_commands": [
            f"flights fli-search {origin} {destination} --depart-date {selected_date or 'YYYY-MM-DD'}",
            f"flights kb-search {origin} {destination} --depart-date {selected_date or 'YYYY-MM-DD'} --only-carrier U6",
        ],
        "note": "Minimum one-way fares from Ural Airlines (U6) official calendar. For flight details use aggregators.",
    }
