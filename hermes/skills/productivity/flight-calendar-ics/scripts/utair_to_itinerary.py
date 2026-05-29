#!/usr/bin/env python3
"""Fetch Utair manage-booking data and convert it to itinerary JSON.

Utair's order-manage page is a JavaScript SPA. The itinerary is obtained via
Utair's public API: client-credentials OAuth token, then an orders lookup by
booking locator and passenger surname. This helper keeps stdout-free functions
for the agent-facing orchestrator in ``flight_calendar_ics.py``.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

UTAIR_WEB_BASE = "https://www.utair.ru/"
UTAIR_API_BASE = "https://b.utair.ru/"

DEFAULT_AIRPORT_TZ = {
    "SVX": "Asia/Yekaterinburg",
    "KUF": "Europe/Samara",
    "DME": "Europe/Moscow",
    "SVO": "Europe/Moscow",
    "VKO": "Europe/Moscow",
    "ZIA": "Europe/Moscow",
    "LED": "Europe/Moscow",
    "TJM": "Asia/Yekaterinburg",
    "SGC": "Asia/Yekaterinburg",
    "HMA": "Asia/Yekaterinburg",
    "UFA": "Asia/Yekaterinburg",
    "KZN": "Europe/Moscow",
    "OVB": "Asia/Novosibirsk",
    "AER": "Europe/Moscow",
}

DEFAULT_AIRPORT_CITY = {
    "SVX": "Екатеринбург",
    "KUF": "Самара",
    "DME": "Москва",
    "SVO": "Москва",
    "VKO": "Москва",
    "ZIA": "Москва",
    "LED": "Санкт-Петербург",
    "TJM": "Тюмень",
    "SGC": "Сургут",
    "HMA": "Ханты-Мансийск",
    "UFA": "Уфа",
    "KZN": "Казань",
    "OVB": "Новосибирск",
    "AER": "Сочи",
}


def die(message: str) -> None:
    raise ValueError(message)


def clean(value: Any) -> Any:
    return None if value in (None, "", []) else value


def browser_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Origin": "https://www.utair.ru",
        "Referer": "https://www.utair.ru/order-manage",
        "Cache-Control": "no-cache",
    }
    if extra:
        headers.update(extra)
    return headers


def parse_utair_source(url: str | None, rloc: str | None, last_name: str | None) -> tuple[str, str, str]:
    """Parse a Utair order-manage URL or explicit locator/surname values.

    The returned booking URL may contain private parameters; callers must keep it
    inside private artifacts and never echo it to chat/log summaries.
    """
    booking_url = url.strip() if url else None
    if booking_url:
        parsed = urlparse(booking_url)
        qs = parse_qs(parsed.query, keep_blank_values=False)
        rloc = rloc or (qs.get("rloc") or qs.get("RLOC") or qs.get("pnr") or [None])[0]
        last_name = last_name or (
            qs.get("last_name")
            or qs.get("lastName")
            or qs.get("lastname")
            or qs.get("surname")
            or [None]
        )[0]
    if not rloc or not last_name:
        die("provide --url containing rloc/last_name or both --rloc and --last-name")

    locator = rloc.strip().upper()
    surname = last_name.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{5,8}", locator):
        die("Utair booking locator format looks invalid")
    if not re.fullmatch(r"[A-ZА-ЯЁ' -]{2,80}", surname, flags=re.IGNORECASE):
        die("Utair last name format looks invalid")
    if not booking_url:
        booking_url = UTAIR_WEB_BASE.rstrip("/") + "/order-manage?" + urlencode({"rloc": locator, "last_name": surname})
    return locator, surname, booking_url


def parse_tz_overrides(items: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            die(f"bad --tz value {item!r}; use CODE=Area/City")
        code, tzid = item.split("=", 1)
        code = code.strip().upper()
        tzid = tzid.strip()
        if not code or not tzid:
            die(f"bad --tz value {item!r}; use CODE=Area/City")
        out[code] = tzid
    return out


def read_json(req: Request, *, timeout: int = 45, label: str = "Utair API") -> Any:
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = getattr(resp, "status", 200)
            content_type = resp.headers.get("Content-Type", "")
    except HTTPError as exc:
        raw = exc.read()
        status = exc.code
        content_type = exc.headers.get("Content-Type", "")
    except URLError as exc:
        die(f"{label} request failed: {exc.reason}")

    text = raw.decode("utf-8", errors="replace")
    if status >= 400:
        die(f"{label} returned HTTP {status} ({content_type})")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        die(f"{label} returned non-JSON response: {exc}")


def fetch_utair_token(timeout: int = 45) -> str:
    payload = urlencode({"client_id": "website_client", "grant_type": "client_credentials"}).encode("utf-8")
    req = Request(
        UTAIR_API_BASE.rstrip("/") + "/oauth/token",
        data=payload,
        method="POST",
        headers=browser_headers({"Content-Type": "application/x-www-form-urlencoded"}),
    )
    data = read_json(req, timeout=timeout, label="Utair OAuth")
    if not isinstance(data, dict):
        die("Utair OAuth response is not a JSON object")
    token = data.get("access_token")
    if not isinstance(token, str) or not token.strip():
        die("Utair OAuth response has no access_token")
    return token.strip()


def fetch_utair_orders(locator: str, last_name: str, *, token: str | None = None, timeout: int = 45) -> dict[str, Any]:
    bearer = token or fetch_utair_token(timeout=timeout)
    query = urlencode({"filters[locator]": locator, "filters[passenger_lastname]": last_name})
    req = Request(
        UTAIR_API_BASE.rstrip("/") + "/api/v3/orders?" + query,
        headers=browser_headers({"Authorization": f"Bearer {bearer}"}),
    )
    data = read_json(req, timeout=timeout, label="Utair orders API")
    if not isinstance(data, dict):
        die("Utair orders API response is not a JSON object")
    if not collect_orders(data):
        die("no Utair orders found")
    return data


def collect_orders(data: dict[str, Any]) -> list[dict[str, Any]]:
    orders: list[dict[str, Any]] = []
    for key in ("future", "past", "objects", "orders"):
        value = data.get(key)
        if isinstance(value, list):
            orders.extend(item for item in value if isinstance(item, dict))
    if not orders and any(key in data for key in ("segments", "passengers", "tickets")):
        orders.append(data)
    return orders


def local_datetime(value: Any) -> str:
    text = str(value or "").strip().replace(" ", "T", 1)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?", text):
        return text[:16]
    return text


def first_value(obj: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = obj.get(key)
        if clean(value):
            return value
    return None


def airport_code(seg: dict[str, Any], prefix: str) -> str:
    if prefix == "departure":
        keys = ["departure_airport_code", "departure_airport", "origin", "origin_code", "from", "from_code"]
    else:
        keys = ["arrival_airport_code", "arrival_airport", "destination", "destination_code", "to", "to_code"]
    return str(first_value(seg, keys) or "").strip().upper()


def city_name(seg: dict[str, Any], prefix: str, code: str) -> str | None:
    keys = [f"{prefix}_city", f"{prefix}_city_name"]
    value = first_value(seg, keys)
    return str(value).strip() if clean(value) else DEFAULT_AIRPORT_CITY.get(code)


def terminal_name(seg: dict[str, Any], prefix: str) -> str | None:
    value = first_value(seg, [f"{prefix}_terminal", f"{prefix}_terminal_code"])
    return str(value).strip() if clean(value) else None


def segment_local(seg: dict[str, Any], prefix: str) -> str:
    keys = [
        f"{prefix}_local_iso",
        f"{prefix}_datetime",
        f"{prefix}_date_time",
        f"{prefix}_time",
        f"{prefix}_date",
        prefix,
    ]
    return local_datetime(first_value(seg, keys))


def flight_number(seg: dict[str, Any]) -> str:
    carrier = str(first_value(seg, ["ak", "airline_code", "carrier_code", "marketing_carrier"]) or "UT").strip().upper()
    number = str(first_value(seg, ["flight_number", "flight", "number"]) or "").strip().upper().replace(" ", "")
    if not number:
        die("Utair segment has no flight number")
    if number.startswith(carrier):
        return number
    return f"{carrier}{number}"


def passenger_names(order: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for pax in order.get("passengers") or []:
        if not isinstance(pax, dict):
            continue
        direct = first_value(pax, ["full_name", "fullName", "name"])
        if clean(direct):
            name = str(direct).strip()
        else:
            parts = [
                pax.get("first_name") or pax.get("firstName"),
                pax.get("second_name") or pax.get("middle_name") or pax.get("middleName"),
                pax.get("last_name") or pax.get("lastName") or pax.get("surname"),
            ]
            name = " ".join(str(item).strip() for item in parts if clean(item))
        if name:
            names.append(name)
    return names


def ticket_numbers(order: dict[str, Any]) -> list[str]:
    numbers: list[str] = []
    for ticket in order.get("tickets") or []:
        if isinstance(ticket, dict):
            number = first_value(ticket, ["ticket", "number", "ticket_number", "ticketNumber"])
        else:
            number = ticket
        if clean(number):
            numbers.append(str(number).strip())
    return sorted(dict.fromkeys(numbers))


def offer_by_segment(order: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for offer in order.get("offers") or []:
        if not isinstance(offer, dict):
            continue
        segment_id = clean(first_value(offer, ["segment_id", "segmentId", "segment_number", "segmentNumber"]))
        if not segment_id:
            continue
        brand = clean(first_value(offer, ["brand_name", "brandName", "name", "title", "fare_name", "fareName"]))
        code = clean(first_value(offer, ["brand_code", "brandCode", "code", "fare_code", "fareCode"]))
        if brand and code:
            text = f"{brand} ({code})"
        elif brand:
            text = str(brand)
        elif code:
            text = str(code)
        else:
            continue
        out[str(segment_id)] = text
    return out


def status_text(seg: dict[str, Any], order: dict[str, Any]) -> str:
    raw = first_value(seg, ["status", "status_code", "statusCode", "status_visual", "statusVisual"]) or order.get("status")
    if not clean(raw):
        return "confirmed"
    text = str(raw).strip()
    if text.upper() in {"HK", "T", "CONFIRMED", "ACTIVE"}:
        return f"confirmed ({text})"
    return text


def explicit_baggage(order: dict[str, Any], seg: dict[str, Any]) -> str | None:
    direct = first_value(seg, ["baggage", "baggage_info", "baggageInfo", "luggage", "luggage_info"])
    if clean(direct):
        return str(direct).strip()
    segment_id = str(first_value(seg, ["segment_id", "segmentId"]) or "")
    values: list[str] = []
    for service in order.get("services") or []:
        if not isinstance(service, dict):
            continue
        service_segment_id = str(first_value(service, ["segment_id", "segmentId"]) or "")
        if service_segment_id and segment_id and service_segment_id != segment_id:
            continue
        haystack = " ".join(str(v) for v in service.values() if isinstance(v, (str, int, float))).upper()
        if any(word in haystack for word in ("BAG", "BAGGAGE", "LUGGAGE", "БАГАЖ")):
            label = first_value(service, ["name", "title", "service_name", "serviceName", "code"])
            values.append(str(label or "baggage").strip())
    if values:
        return ", ".join(sorted(dict.fromkeys(values)))
    return None


def segment_id(seg: dict[str, Any]) -> str:
    value = first_value(seg, ["segment_id", "segmentId", "id", "number"])
    return str(value) if clean(value) else ""


def convert_to_itinerary(data: dict[str, Any], tz_map: dict[str, str], booking_url: str | None = None) -> dict[str, Any]:
    if not isinstance(data, dict):
        die("Utair orders API response is not a JSON object")

    flights: list[dict[str, Any]] = []
    passengers: list[str] = []
    booking_reference: str | None = None
    missing_tz: set[str] = set()

    orders = collect_orders(data)
    if not orders:
        die("no Utair orders found")

    for order in orders:
        if booking_reference is None:
            ref = first_value(order, ["rloc", "locator", "pnr", "booking_reference", "bookingReference"])
            booking_reference = str(ref).strip() if clean(ref) else None
        for name in passenger_names(order):
            if name not in passengers:
                passengers.append(name)
        tickets = ticket_numbers(order)
        fare_map = offer_by_segment(order)
        segments = order.get("segments") or order.get("flights") or []
        if not isinstance(segments, list):
            continue
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            dep_code = airport_code(seg, "departure")
            arr_code = airport_code(seg, "arrival")
            for code in [dep_code, arr_code]:
                if code and code not in tz_map:
                    missing_tz.add(code)
            if missing_tz:
                continue
            dep_local = segment_local(seg, "departure")
            arr_local = segment_local(seg, "arrival")
            if not dep_code or not arr_code or not dep_local or not arr_local:
                die("Utair segment is missing route or local time fields")

            sid = segment_id(seg)
            notes: list[str] = []
            baggage = explicit_baggage(order, seg)
            if not baggage:
                notes.append("Багаж в данных бронирования не указан")

            flight: dict[str, Any] = {
                "carrier": "Utair",
                "flight_number": flight_number(seg),
                "departure": {
                    "airport": dep_code,
                    "city": city_name(seg, "departure", dep_code),
                    "terminal": terminal_name(seg, "departure"),
                    "local": dep_local,
                    "tz": tz_map[dep_code],
                },
                "arrival": {
                    "airport": arr_code,
                    "city": city_name(seg, "arrival", arr_code),
                    "terminal": terminal_name(seg, "arrival"),
                    "local": arr_local,
                    "tz": tz_map[arr_code],
                },
                "pnr": booking_reference,
                "ticket_number": ", ".join(tickets) if tickets else None,
                "status": status_text(seg, order),
                "fare": fare_map.get(sid),
                "notes": "; ".join(notes),
            }
            if baggage:
                flight["baggage"] = baggage
            aircraft = first_value(seg, ["aircraft", "aircraft_name", "aircraftName"])
            if clean(aircraft):
                flight["aircraft"] = str(aircraft).strip()
            cabin = first_value(seg, ["cabin", "class", "class_of_service", "classOfService"])
            if clean(cabin):
                flight["cabin"] = str(cabin).strip()
            flights.append(flight)

    if missing_tz:
        codes = ", ".join(sorted(missing_tz))
        die(f"missing timezone for airport(s): {codes}; rerun with --tz CODE=Area/City")
    if not flights:
        die("no flight segments found in Utair response")

    return {
        "schema_version": "flight-calendar-ics-itinerary.v1",
        "calendar_name": "Utair flights",
        "booking_reference": booking_reference,
        "links": [booking_url] if booking_url else [],
        "passengers": passengers,
        "alarms_minutes": [1440, 180],
        "notes": "Сформировано из данных страницы управления бронированием Utair.",
        "flights": flights,
    }


def secure_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    finally:
        try:
            os.chmod(path, 0o600)
        except FileNotFoundError:
            pass


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Convert Utair manage-booking URL/API data to flight-calendar-ics JSON.")
    parser.add_argument("--url", help="Utair order-manage URL containing rloc and last_name")
    parser.add_argument("--rloc", help="Booking locator, if not using --url")
    parser.add_argument("--last-name", help="Passenger surname, if not using --url")
    parser.add_argument("--output-json", required=True, type=Path, help="Where to write itinerary JSON")
    parser.add_argument("--tz", action="append", default=[], help="Timezone override CODE=Area/City; repeatable")
    args = parser.parse_args(argv)

    locator, last_name, booking_url = parse_utair_source(args.url, args.rloc, args.last_name)
    token = fetch_utair_token()
    orders = fetch_utair_orders(locator, last_name, token=token)
    tz_map = {**DEFAULT_AIRPORT_TZ, **parse_tz_overrides(args.tz)}
    itinerary = convert_to_itinerary(orders, tz_map, booking_url=booking_url)
    secure_write_text(args.output_json, json.dumps(itinerary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"ok": True, "segments": len(itinerary["flights"]), "json": str(args.output_json)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
