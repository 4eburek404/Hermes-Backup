"""Hermes tool handlers for Travelpayouts flights."""
from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import date
from typing import Any

import aiohttp

from .cache import get_airlines_cache, get_airports_cache, get_cities_cache, get_planes_cache
from .client import RateLimitError, TravelpayoutsAPIError, TravelpayoutsClient, build_booking_url
from .enrichment import flight_to_out
from .formatters import format_flight_results, format_date_full
from .schemas import SUPPORTED_CURRENCIES

_IATA_RE = re.compile(r"^[A-ZА-Я]{3}$")
MAX_LIMIT = 20
DEFAULT_LIMIT = 10
CACHE_NOTE = (
    "Travelpayouts/Aviasales Data API can return cached data; prices and seats are not guaranteed. "
    "Before purchase, recheck the final price and fare rules on the aggregator/airline site."
)


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)


def check_travelpayouts_available() -> bool:
    return bool(os.getenv("TRAVELPAYOUTS_TOKEN"))


def _normalize_iata(value: Any, field: str, errors: list[str]) -> str:
    code = str(value or "").strip().upper()
    if not _IATA_RE.match(code):
        errors.append(f"{field} must be a 3-letter IATA code, got {value!r}")
    return code


async def _resolve_location(value: Any, field: str, errors: list[str]) -> tuple[str | None, list[dict] | None]:
    """Resolve a location (origin/destination) to IATA code.

    If value is a 3-letter IATA code, use it directly.
    If value is a city name (Russian or English), search CitiesCache.
    Returns (iata_code, suggestions_or_None).
    """
    raw = str(value or "").strip()
    if not raw:
        errors.append(f"{field} is required")
        return None, None

    upper = raw.upper()

    # Fast path: looks like an IATA code
    if _IATA_RE.match(upper):
        return upper, None

    # City name search
    cities_cache = get_cities_cache()
    try:
        await cities_cache.ensure_loaded()
    except Exception as exc:
        errors.append(f"Could not load cities cache to resolve {field}={raw!r}: {exc}")
        return None, None

    results = cities_cache.search(raw, limit=5)
    if not results:
        errors.append(
            f"{field}: city not found for '{raw}'. "
            f"Use a 3-letter IATA code (e.g. SVX, MOW) or a city name (e.g. Екатеринбург, Moscow)."
        )
        return None, None

    if len(results) == 1:
        return results[0].code, None

    # Multiple matches — return suggestions for disambiguation
    suggestions = [
        {"code": c.code, "name": c.name, "country": c.country_code}
        for c in results
    ]
    return None, suggestions


def _parse_date(value: Any, field: str, errors: list[str]) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        if field == "return_date":
            return None
        errors.append(f"{field} is required in YYYY-MM-DD format")
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        errors.append(f"{field} must be YYYY-MM-DD, got {raw!r}")
        return None


def _parse_limit(value: Any) -> tuple[int, list[str]]:
    warnings: list[str] = []
    if value is None or value == "":
        return DEFAULT_LIMIT, warnings
    try:
        limit = int(value)
    except (TypeError, ValueError):
        warnings.append(f"Invalid limit {value!r}; using {DEFAULT_LIMIT}")
        return DEFAULT_LIMIT, warnings
    if limit < 1:
        warnings.append("limit was below 1; clamped to 1")
        return 1, warnings
    if limit > MAX_LIMIT:
        warnings.append(f"limit was above {MAX_LIMIT}; clamped to {MAX_LIMIT}")
        return MAX_LIMIT, warnings
    return limit, warnings


async def _normalize_args(args: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    # Resolve origin and destination (IATA or city name)
    origin, origin_suggestions = await _resolve_location(args.get("origin"), "origin", errors)
    destination, dest_suggestions = await _resolve_location(args.get("destination"), "destination", errors)

    # If we have disambiguation suggestions, return immediately with a helpful error
    if origin_suggestions or dest_suggestions:
        suggestion_data = {}
        if origin_suggestions:
            suggestion_data["origin_suggestions"] = origin_suggestions
        if dest_suggestions:
            suggestion_data["destination_suggestions"] = dest_suggestions
        return None, errors, warnings, suggestion_data  # type: ignore[return-value]

    if errors:
        return None, errors, warnings, {}  # type: ignore[return-value]

    assert origin is not None and destination is not None

    if origin == destination:
        errors.append("origin and destination must differ")
        return None, errors, warnings, {}  # type: ignore[return-value]

    depart_date = _parse_date(args.get("departure_date"), "departure_date", errors)
    return_date = _parse_date(args.get("return_date"), "return_date", errors) if args.get("return_date") else None
    if depart_date and return_date and return_date < depart_date:
        errors.append("return_date must be the same as or after departure_date")

    currency = str(args.get("currency") or "RUB").strip().upper()
    if currency not in SUPPORTED_CURRENCIES:
        errors.append(f"currency must be one of {', '.join(SUPPORTED_CURRENCIES)}, got {currency!r}")

    limit, limit_warnings = _parse_limit(args.get("limit"))
    warnings.extend(limit_warnings)
    direct_only = bool(args.get("direct_only", False))

    if errors:
        return None, errors, warnings, {}  # type: ignore[return-value]

    resolved_origin_name = None
    resolved_dest_name = None
    if origin and origin != str(args.get("origin", "")).strip().upper():
        # Name was resolved — note it
        resolved_origin_name = str(args.get("origin", "")).strip()
    if destination and destination != str(args.get("destination", "")).strip().upper():
        resolved_dest_name = str(args.get("destination", "")).strip()

    if resolved_origin_name:
        warnings.append(f"origin '{resolved_origin_name}' resolved to {origin}")
    if resolved_dest_name:
        warnings.append(f"destination '{resolved_dest_name}' resolved to {destination}")

    return {
        "origin": origin,
        "destination": destination,
        "departure_date": depart_date,
        "return_date": return_date,
        "currency": currency,
        "direct_only": direct_only,
        "limit": limit,
    }, errors, warnings, {}


async def travelpayouts_flight_search(args: dict[str, Any], **kwargs) -> str:
    """Search Travelpayouts flight prices and return enriched JSON with human-readable names."""
    normalized, errors, warnings, disambiguation = await _normalize_args(args or {})

    # Disambiguation: multiple cities matched
    if disambiguation:
        return _json({
            "success": False,
            "error_type": "disambiguation_needed",
            "message": "Multiple cities matched your query. Please specify the IATA code.",
            **disambiguation,
            "cached_data_note": CACHE_NOTE,
        })

    if errors:
        return _json({
            "success": False,
            "error_type": "validation_error",
            "errors": errors,
            "warnings": warnings,
            "cached_data_note": CACHE_NOTE,
        })

    if not check_travelpayouts_available():
        return _json({
            "success": False,
            "error_type": "missing_credentials",
            "error": "TRAVELPAYOUTS_TOKEN is not configured in Hermes environment.",
            "cached_data_note": CACHE_NOTE,
        })

    assert normalized is not None
    client = TravelpayoutsClient()
    marker = os.getenv("TRAVELPAYOUTS_MARKER") or None

    # Pre-load reference caches concurrently
    airlines = get_airlines_cache()
    airports = get_airports_cache()
    cities = get_cities_cache()
    planes = get_planes_cache()

    try:
        await asyncio.gather(
            airlines.ensure_loaded(),
            airports.ensure_loaded(),
            cities.ensure_loaded(),
            planes.ensure_loaded(),
        )
    except Exception as exc:
        warnings.append(f"Reference data load warning: {type(exc).__name__} — names may be incomplete")

    try:
        flights, meta = await client.get_prices(
            origin=normalized["origin"],
            destination=normalized["destination"],
            depart_date=normalized["departure_date"],
            return_date=normalized["return_date"],
            currency=normalized["currency"],
            direct_only=normalized["direct_only"],
        )
    except RateLimitError as exc:
        return _json({
            "success": False,
            "error_type": "rate_limited",
            "retry_after_seconds": exc.retry_after,
            "query": _query_for_output(normalized),
            "warnings": warnings + [CACHE_NOTE],
            "source": "travelpayouts_graphql",
        })
    except (TravelpayoutsAPIError, aiohttp.ClientError, TimeoutError) as exc:
        return _json({
            "success": False,
            "error_type": "upstream_error",
            "error": str(exc)[:1000],
            "query": _query_for_output(normalized),
            "warnings": warnings + [CACHE_NOTE],
            "source": "travelpayouts_graphql",
        })
    except Exception as exc:
        return _json({
            "success": False,
            "error_type": "internal_error",
            "error": type(exc).__name__,
            "query": _query_for_output(normalized),
            "warnings": warnings + [CACHE_NOTE],
            "source": "travelpayouts_graphql",
        })

    # Enrich flights with human-readable names
    selected = flights[: normalized["limit"]]
    output_flights = [
        flight_to_out(
            flight,
            currency=normalized["currency"],
            airlines_cache=airlines,
            airports_cache=airports,
            cities_cache=cities,
            planes_cache=planes,
            marker=marker,
        ).model_dump()
        for flight in selected
    ]

    if meta.get("parse_errors"):
        warnings.append(f"Skipped {meta['parse_errors']} malformed upstream result(s)")
    if not output_flights:
        warnings.append("No matching flights returned by upstream for this exact query")

    # Detect direct_not_available: user asked for direct_only but all results have transfers
    direct_not_available = False
    if normalized["direct_only"] and output_flights and all(f.get("transfers", 0) > 0 for f in output_flights):
        direct_not_available = True
        warnings.append("No direct flights available for this route/date; showing flights with transfers")

    # Build human-readable city names for header
    origin_city = cities.get_by_code(normalized["origin"])
    dest_city = cities.get_by_code(normalized["destination"])
    origin_name = f"{origin_city.name} ({normalized['origin']})" if origin_city else normalized["origin"]
    destination_name = f"{dest_city.name} ({normalized['destination']})" if dest_city else normalized["destination"]

    # Build top-level formatted HTML — this IS the reply the user sees
    formatted_html = format_flight_results(
        output_flights,
        origin=normalized["origin"],
        origin_name=origin_name,
        destination=normalized["destination"],
        destination_name=destination_name,
        departure_date=normalized["departure_date"].isoformat(),
        return_date=normalized["return_date"].isoformat() if normalized["return_date"] else None,
        currency=normalized["currency"],
        direct_not_available=direct_not_available,
        warnings=warnings,
    )

    # Compact summary for the model: enough to answer follow-up questions
    # without re-calling the tool, but not the full verbose JSON
    summary_flights = []
    for f in output_flights:
        entry = {
            "price": f.get("price"),
            "currency": f.get("currency", "RUB"),
            "transfers": f.get("transfers"),
            "duration_min": f.get("duration_min"),
            "airline": f.get("airline"),
            "booking_url": f.get("booking_url"),
        }
        ob = f.get("outbound")
        if ob:
            entry["outbound_depart"] = ob.get("departure_at")
            entry["outbound_arrive"] = ob.get("arrival_at")
        ib = f.get("inbound")
        if ib:
            entry["inbound_depart"] = ib.get("departure_at")
            entry["inbound_arrive"] = ib.get("arrival_at")
        summary_flights.append(entry)

    # Return HTML as primary + compact JSON summary appended
    summary_json = _json({
        "success": True,
        "count": len(output_flights),
        "direct_not_available": direct_not_available,
        "flights": summary_flights,
        "cached_data_note": CACHE_NOTE,
        "advisory_only": True,
    })

    return formatted_html + "\n\n---\n" + summary_json


def _query_for_output(normalized: dict[str, Any]) -> dict[str, Any]:
    return {
        "origin": normalized["origin"],
        "destination": normalized["destination"],
        "departure_date": normalized["departure_date"].isoformat(),
        "return_date": normalized["return_date"].isoformat() if normalized["return_date"] else None,
        "currency": normalized["currency"],
        "direct_only": normalized["direct_only"],
        "limit": normalized["limit"],
    }