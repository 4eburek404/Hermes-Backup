from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import date
from typing import Any

from .. import __version__
from ..config import CACHE_NOTE, GRAPHQL_ONE_WAY_QUERY, GRAPHQL_ROUND_TRIP_QUERY, GRAPHQL_URL, SUPPORTED_CURRENCIES
from ..domain.carriers import carrier_from_leg
from ..domain.normalize import normalize_iata, normalize_transfers, parse_iso_date, price_value
from ..errors import CliError

def aviasales_url(origin: str, destination: str, depart: date, ret: date | None = None) -> str:
    dep = depart.strftime("%d%m")
    if ret:
        return f"https://www.aviasales.ru/search/{origin}{dep}{destination}{ret.strftime('%d%m')}"
    return f"https://www.aviasales.ru/search/{origin}{dep}{destination}1"


def build_request_payload(
    origin: str,
    destination: str,
    depart: date,
    ret: date | None,
    currency: str,
    direct_only: bool,
) -> dict[str, Any]:
    variables: dict[str, Any] = {
        "origin": origin,
        "destination": destination,
        "depart_dates": [depart.isoformat()],
        "direct": direct_only,
        "currency": currency,
    }
    if ret:
        variables["return_dates"] = [ret.isoformat()]
        query = GRAPHQL_ROUND_TRIP_QUERY
        query_name = "prices_round_trip"
    else:
        query = GRAPHQL_ONE_WAY_QUERY
        query_name = "prices_one_way"
    return {
        "method": "POST",
        "endpoint": GRAPHQL_URL,
        "query_name": query_name,
        "variables": variables,
        "body": {"query": query, "variables": variables},
        "headers": {
            "X-Access-Token": "<redacted>" if os.getenv("TRAVELPAYOUTS_TOKEN") else "<missing>",
            "Content-Type": "application/json",
        },
    }


def compact_request_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": payload["method"],
        "endpoint": payload["endpoint"],
        "query_name": payload["query_name"],
        "variables": payload["variables"],
        "headers": payload["headers"],
    }


def segment_request_command(
    origin: str,
    destination: str,
    depart: date,
    *,
    currency: str,
    direct_only: bool,
) -> str:
    parts = [
        "flights",
        "--json",
        "request",
        "search",
        origin,
        destination,
        "--depart-date",
        depart.isoformat(),
        "--currency",
        currency,
        "--dry-run",
    ]
    if direct_only:
        parts.append("--direct-only")
    return " ".join(parts)


def unwrap_travelpayouts_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return raw Travelpayouts JSON and request variables from supported envelopes."""
    variables: dict[str, Any] = {}
    current = payload
    if payload.get("ok") is True and isinstance(payload.get("data"), dict):
        data = payload["data"]
        request = data.get("request")
        if isinstance(request, dict) and isinstance(request.get("variables"), dict):
            variables = dict(request["variables"])
        fetched = data.get("fetched")
        if isinstance(fetched, dict) and isinstance(fetched.get("data"), dict):
            current = fetched["data"]
        elif isinstance(data.get("response"), dict):
            current = data["response"]
        else:
            current = data
    if isinstance(current.get("request"), dict) and isinstance(current["request"].get("variables"), dict):
        variables = dict(current["request"]["variables"])
    return current, variables


def raw_price_items(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    raw = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    for key in ("prices_one_way", "prices_round_trip"):
        value = raw.get(key) if isinstance(raw, dict) else None
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)], key
    if isinstance(payload.get("offers"), list):
        return [item for item in payload["offers"] if isinstance(item, dict)], "offers"
    return [], "unknown"


def selected_trip_segment_index(source_key: str, direction: str, count: int) -> int | None:
    if count <= 0:
        return None
    if source_key == "prices_round_trip" and direction == "return":
        return 1 if count > 1 else None
    return 0


def normalize_offer(
    item: dict[str, Any],
    *,
    source_key: str,
    query_origin: str | None,
    query_destination: str | None,
    query_date: str | None,
    currency: str | None,
    direction: str,
    leg_name: str,
    index: int,
) -> dict[str, Any] | None:
    trip_segments = item.get("segments")
    if not isinstance(trip_segments, list) or not trip_segments:
        return None
    trip_segment_index = selected_trip_segment_index(source_key, direction, len(trip_segments))
    if trip_segment_index is None:
        return None
    trip_segment = trip_segments[trip_segment_index]
    if not isinstance(trip_segment, dict):
        return None
    raw_legs = trip_segment.get("flight_legs")
    if not isinstance(raw_legs, list) or not raw_legs:
        return None

    transfers = normalize_transfers(trip_segment.get("transfers"))
    legs: list[dict[str, Any]] = []
    for leg_index, raw_leg in enumerate(raw_legs):
        if not isinstance(raw_leg, dict):
            continue
        origin = str(raw_leg.get("origin") or "").upper()
        destination = str(raw_leg.get("destination") or "").upper()
        if not origin or not destination:
            continue
        leg = {
            "origin": origin,
            "destination": destination,
            "departure_at": str(raw_leg.get("departure_at") or ""),
            "arrival_at": str(raw_leg.get("arrival_at") or ""),
            "carrier": carrier_from_leg(raw_leg),
            "flight_number": raw_leg.get("flight_number"),
            "aircraft_code": raw_leg.get("aircraft_code"),
        }
        if leg_index < len(transfers):
            leg["transfer_after"] = transfers[leg_index]
        legs.append(leg)
    if not legs:
        return None

    price = price_value({"price": item.get("value") if item.get("value") is not None else item.get("price")})
    departure_at = str(trip_segment.get("departure_at") or legs[0].get("departure_at") or item.get("departure_at") or "")
    arrival_at = str(trip_segment.get("arrival_at") or legs[-1].get("arrival_at") or "")
    origin = legs[0]["origin"]
    destination = legs[-1]["destination"]
    flight_bits = "-".join(str(leg.get("flight_number") or leg.get("carrier") or "XX") for leg in legs)
    offer_id = f"{direction}:{leg_name}:{origin}-{destination}:{departure_at}:{flight_bits}:{price or 0}:{index}"
    return {
        "id": offer_id,
        "direction": direction,
        "leg": leg_name,
        "query_origin": query_origin,
        "query_destination": query_destination,
        "query_date": query_date,
        "origin": origin,
        "destination": destination,
        "departure_airport": origin,
        "arrival_airport": destination,
        "departure_at": departure_at,
        "arrival_at": arrival_at,
        "price": price,
        "currency": currency,
        "carrier": carrier_from_leg(legs[0]) if legs else item.get("main_airline"),
        "main_airline": item.get("main_airline"),
        "changes": item.get("number_of_changes"),
        "duration_min": item.get("duration"),
        "trip_duration_days": item.get("trip_duration"),
        "ticket_link": item.get("ticket_link"),
        "segments": legs,
        "transfers": transfers,
        "selected_trip_segment_index": trip_segment_index,
        "internal_connection_count": max(0, len(legs) - 1),
    }


def parse_travelpayouts_results(args: argparse.Namespace, payload: dict[str, Any]) -> dict[str, Any]:
    raw, variables = unwrap_travelpayouts_payload(payload)
    items, source_key = raw_price_items(raw)
    origin_value = args.origin or str(variables.get("origin") or "")
    destination_value = args.destination or str(variables.get("destination") or "")
    if source_key == "prices_round_trip" and args.direction == "return" and not args.origin and not args.destination:
        origin_value, destination_value = destination_value, origin_value
    origin = normalize_iata(origin_value, "origin") if origin_value else None
    destination = normalize_iata(destination_value, "destination") if destination_value else None
    query_date = args.date
    if not query_date:
        date_key = "return_dates" if args.direction == "return" else "depart_dates"
        date_values = variables.get(date_key)
        if not date_values and date_key == "return_dates":
            date_values = variables.get("depart_dates")
        if isinstance(date_values, list) and date_values:
            query_date = str(date_values[0])
    if query_date:
        parse_iso_date(query_date, "date")
    currency = (args.currency or str(variables.get("currency") or "") or None)
    if currency:
        currency = currency.upper()

    offers = []
    parse_errors = 0
    for index, item in enumerate(items):
        offer = normalize_offer(
            item,
            source_key=source_key,
            query_origin=origin,
            query_destination=destination,
            query_date=query_date,
            currency=currency,
            direction=args.direction,
            leg_name=args.leg,
            index=index,
        )
        if offer is None:
            parse_errors += 1
            continue
        offers.append(offer)
    offers.sort(key=lambda offer: (offer["price"] if offer["price"] is not None else 10**12, offer["departure_at"]))
    if args.limit:
        offers = offers[: args.limit]
    return {
        "segment_result": {
            "direction": args.direction,
            "leg": args.leg,
            "query": {
                "origin": origin,
                "destination": destination,
                "date": query_date,
                "currency": currency,
            },
            "source_key": source_key,
            "raw_count": len(items),
            "parse_errors": parse_errors,
            "offers": offers,
        }
    }


def run_request_search(args: argparse.Namespace) -> dict[str, Any]:
    origin = normalize_iata(args.origin, "origin")
    destination = normalize_iata(args.destination, "destination")
    depart = parse_iso_date(args.depart_date, "depart-date")
    ret = parse_iso_date(args.return_date, "return-date") if args.return_date else None
    currency = args.currency.upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise CliError(f"currency must be one of {', '.join(sorted(SUPPORTED_CURRENCIES))}", error_type="validation_error")

    payload = build_request_payload(origin, destination, depart, ret, currency, args.direct_only)
    result = {
        "dry_run": not args.fetch,
        "advisory_only": True,
        "cache_note": CACHE_NOTE,
        "request": payload,
        "manual_link": aviasales_url(origin, destination, depart, ret),
    }
    if not args.fetch:
        return result

    token = os.getenv("TRAVELPAYOUTS_TOKEN")
    if not token:
        raise CliError("TRAVELPAYOUTS_TOKEN is required for --fetch", error_type="missing_credentials")
    body = json.dumps(payload["body"]).encode("utf-8")
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={
            "X-Access-Token": token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"flights-cli/{__version__}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            raw = response.read()
            fetched_data = json.loads(raw.decode("utf-8"))
            status = response.status
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")[:1000]
        raise CliError(f"Travelpayouts HTTP {exc.code}: {body_text}", error_type="upstream_error") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise CliError(f"Travelpayouts request failed: {type(exc).__name__}", error_type="upstream_error") from exc

    result["fetched"] = {
        "status": status,
        "data": fetched_data,
    }
    return result
