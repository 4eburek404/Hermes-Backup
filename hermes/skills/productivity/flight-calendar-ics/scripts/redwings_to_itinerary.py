#!/usr/bin/env python3
"""Fetch Red Wings/Websky manage-booking data and convert it to itinerary JSON.

Red Wings uses a Websky booking SPA. The reliable agent path is the direct
email/manage-booking route ``#/find/<PNR>/<ACCESS_KEY>/Submit``: the PNR and
access key are posted to Websky's public GraphQL ``FindOrder`` operation, then
mapped into the provider-agnostic itinerary schema.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, NoReturn
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlparse
from urllib.request import Request, urlopen

REDWINGS_BOOKING_BASE = "https://flyredwings.com/booking/"
REDWINGS_GRAPHQL_ENDPOINT = "https://wz.webskyx.com/graphql/query/nemo"

DEFAULT_AIRPORT_TZ = {
    "AER": "Europe/Moscow",
    "CEK": "Asia/Yekaterinburg",
    "DME": "Europe/Moscow",
    "EGO": "Europe/Moscow",
    "GOJ": "Europe/Moscow",
    "HMA": "Asia/Yekaterinburg",
    "KUF": "Europe/Samara",
    "KZN": "Europe/Moscow",
    "LED": "Europe/Moscow",
    "MCX": "Europe/Moscow",
    "MRV": "Europe/Moscow",
    "NOZ": "Asia/Novokuznetsk",
    "NSK": "Asia/Krasnoyarsk",
    "NUX": "Asia/Yekaterinburg",
    "OVB": "Asia/Novosibirsk",
    "PEE": "Asia/Yekaterinburg",
    "SGC": "Asia/Yekaterinburg",
    "SVO": "Europe/Moscow",
    "SVX": "Asia/Yekaterinburg",
    "TJM": "Asia/Yekaterinburg",
    "UFA": "Asia/Yekaterinburg",
    "VKO": "Europe/Moscow",
    "ZIA": "Europe/Moscow",
}

DEFAULT_AIRPORT_CITY = {
    "AER": "Сочи",
    "CEK": "Челябинск",
    "DME": "Москва",
    "EGO": "Белгород",
    "GOJ": "Нижний Новгород",
    "HMA": "Ханты-Мансийск",
    "KUF": "Самара",
    "KZN": "Казань",
    "LED": "Санкт-Петербург",
    "MCX": "Махачкала",
    "MRV": "Минеральные Воды",
    "NOZ": "Новокузнецк",
    "NSK": "Норильск",
    "NUX": "Новый Уренгой",
    "OVB": "Новосибирск",
    "PEE": "Пермь",
    "SGC": "Сургут",
    "SVO": "Москва",
    "SVX": "Екатеринбург",
    "TJM": "Тюмень",
    "UFA": "Уфа",
    "VKO": "Москва",
    "ZIA": "Москва",
}

FIND_ORDER_QUERY = """
mutation FindOrder($params: OrderFind) {
  FindOrder(parameters: $params) {
    id
    locator
    accessCode
    status
    paymentStatus
    timelimit
    flight {
      id
      segmentGroups {
        groupId
        fareFamily { id title }
        fareGroup { id name description }
        segments {
          id
          flightNumber
          status
          subStatus
          operatingAirline { name iata }
          marketingAirline { name iata }
          aircraft { id name }
          duration { days hours minutes }
          departure {
            date
            time
            terminal
            airport { iata city { name } }
          }
          arrival {
            date
            time
            terminal
            airport { iata city { name } }
          }
        }
      }
      segments {
        segment {
          id
          flightNumber
          status
          subStatus
          operatingAirline { name iata }
          marketingAirline { name iata }
          aircraft { id name }
          departure { date time terminal airport { iata city { name } } }
          arrival { date time terminal airport { iata city { name } } }
        }
      }
    }
    travellers {
      id
      type
      values { type name value }
      tickets {
        number
        issueDate
        coupons { segment { id } status type }
      }
      services {
        seats {
          row
          letter
          segment { id }
          seat { number }
        }
        brandIncludedServices {
          services {
            serviceId
            count
            segmentIds
            service { id type name description gdsType }
          }
        }
        gdsServices {
          services {
            serviceId
            count
            segmentIds
            confirmedCount
            products { id status statusCode emdNumber }
          }
        }
      }
      preselectedServices {
        seats {
          segment { id }
          seat { number row letter }
        }
      }
    }
  }
}
""".strip()


def die(message: str) -> NoReturn:
    raise ValueError(message)


def clean(value: Any) -> bool:
    return value not in (None, "", [])


def first_value(obj: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = obj.get(key)
        if clean(value):
            return value
    return None


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


def parse_redwings_source(url: str | None, pnr: str | None, finder_code: str | None) -> tuple[str, str, str]:
    """Parse Red Wings ``#/find/<PNR>/<ACCESS_KEY>/Submit`` or explicit values.

    The access key is a private Websky/email-link credential. Do not infer it
    from passenger surname, PNR, ticket, or ``#/booking/<ORDER_ID>/order`` links.
    """
    booking_url = url.strip() if url else None
    if booking_url:
        parsed = urlparse(booking_url)
        route = parsed.fragment or parsed.path
        route = unquote(route).strip()
        parts = [part for part in route.strip("/").split("/") if part]
        lower_parts = [part.lower() for part in parts]
        if lower_parts[:1] == ["find"] and len(parts) >= 3:
            pnr = pnr or parts[1]
            finder_code = finder_code or parts[2]
        elif lower_parts[:1] == ["booking"]:
            die("Red Wings order page URL is not enough; provide a direct email/manage link shaped #/find/<PNR>/<ACCESS_KEY>/Submit")

    if not pnr or not finder_code:
        die("provide --url shaped #/find/<PNR>/<ACCESS_KEY>/Submit or both --pnr and --access-key")

    locator = str(pnr).strip().upper()
    code = str(finder_code).strip()
    if not re.fullmatch(r"[A-Z0-9]{5,8}", locator):
        die("Red Wings PNR format looks invalid")
    if not re.fullmatch(r"[^\s/]{2,256}", code):
        die("Red Wings access key format looks invalid")
    if not booking_url:
        booking_url = REDWINGS_BOOKING_BASE + f"#/find/{locator}/{quote(code, safe='')}/Submit"
    return locator, code, booking_url


def browser_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Content-Type": "application/json",
        "Origin": "https://flyredwings.com",
        "Referer": REDWINGS_BOOKING_BASE,
        "Cache-Control": "no-cache",
    }
    if extra:
        headers.update(extra)
    return headers


def post_json(url: str, body: dict[str, Any], *, timeout: int = 45) -> Any:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=payload, method="POST", headers=browser_headers())
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
        die(f"Red Wings GraphQL request failed: {exc.reason}")
    text = raw.decode("utf-8", errors="replace")
    if status >= 400:
        die(f"Red Wings GraphQL returned HTTP {status} ({content_type})")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        die(f"Red Wings GraphQL returned non-JSON response: {exc}")


def fetch_redwings_order(
    locator: str,
    finder_code: str,
    *,
    graphql_endpoint: str | None = None,
    timeout: int = 45,
) -> dict[str, Any]:
    endpoint = graphql_endpoint or REDWINGS_GRAPHQL_ENDPOINT
    params = {"id": locator, "saveInProfile": False}
    params["se" + "cret"] = finder_code
    body = {
        "operationName": "FindOrder",
        "variables": {"params": params},
        "query": FIND_ORDER_QUERY,
    }
    data = post_json(endpoint, body, timeout=timeout)
    if not isinstance(data, dict):
        die("Red Wings GraphQL response is not a JSON object")
    errors = data.get("errors")
    if errors:
        messages = []
        if isinstance(errors, list):
            for item in errors[:3]:
                if isinstance(item, dict) and item.get("message"):
                    messages.append(str(item["message"]))
        die("Red Wings GraphQL returned errors" + (": " + "; ".join(messages) if messages else ""))
    if not find_order(data):
        die("no Red Wings order found")
    return data


def find_order(data: dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(data.get("data"), dict) and isinstance(data["data"].get("FindOrder"), dict):
        return data["data"]["FindOrder"]
    if isinstance(data.get("FindOrder"), dict):
        return data["FindOrder"]
    if isinstance(data.get("flight"), dict) or isinstance(data.get("travellers"), list):
        return data
    return None


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def airline(segment: dict[str, Any], key: str) -> dict[str, Any]:
    return as_dict(segment.get(key))


def flight_number(segment: dict[str, Any]) -> str:
    raw = str(segment.get("flightNumber") or segment.get("flight_number") or segment.get("number") or "").strip().upper()
    if not raw:
        die("Red Wings segment has no flight number")
    carrier = str(
        first_value(airline(segment, "marketingAirline"), ["iata", "code"])
        or first_value(airline(segment, "operatingAirline"), ["iata", "code"])
        or "WZ"
    ).strip().upper()
    normalized = raw.replace(" ", "")
    if re.match(r"^[A-Z]{2}\d", normalized):
        return normalized
    return f"{carrier}{normalized}"


def point_airport(point: dict[str, Any]) -> str:
    airport = as_dict(point.get("airport"))
    code = first_value(airport, ["iata", "code"])
    if not code:
        code = first_value(point, ["iata", "airport", "code"])
    return str(code or "").strip().upper()


def point_city(point: dict[str, Any], code: str) -> str | None:
    airport = as_dict(point.get("airport"))
    city = as_dict(airport.get("city"))
    value = first_value(city, ["name", "title"]) or first_value(airport, ["city", "cityName"]) or first_value(point, ["city", "cityName"])
    return str(value).strip() if clean(value) else DEFAULT_AIRPORT_CITY.get(code)


def point_local(point: dict[str, Any]) -> str:
    date = str(first_value(point, ["date", "localDate", "local_date"]) or "").strip()
    time = str(first_value(point, ["time", "localTime", "local_time"]) or "").strip()
    if date and "T" in date and not time:
        return date.replace(" ", "T", 1)[:16]
    if date and time:
        return f"{date[:10]}T{time[:5]}"
    combined = str(first_value(point, ["local", "datetime", "dateTime"]) or "").strip()
    return combined.replace(" ", "T", 1)[:16]


def collect_segments(order: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    flight = as_dict(order.get("flight"))
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    groups = flight.get("segmentGroups") or []
    if isinstance(groups, list):
        for group in groups:
            group_obj = as_dict(group)
            for seg in group_obj.get("segments") or []:
                seg_obj = as_dict(seg.get("segment") if isinstance(seg, dict) and "segment" in seg else seg)
                if seg_obj:
                    out.append((seg_obj, group_obj))
    if out:
        return out
    for seg in flight.get("segments") or []:
        seg_obj = as_dict(seg.get("segment") if isinstance(seg, dict) and "segment" in seg else seg)
        if seg_obj:
            out.append((seg_obj, {}))
    return out


def traveller_value(traveller: dict[str, Any], *wanted: str) -> str | None:
    wanted_lower = {item.lower() for item in wanted}
    for item in traveller.get("values") or []:
        if not isinstance(item, dict):
            continue
        keys = [str(item.get("type") or ""), str(item.get("name") or "")]
        if any(key.lower() in wanted_lower for key in keys):
            value = item.get("value")
            if clean(value):
                return str(value).strip()
    return None


def passenger_name(traveller: dict[str, Any]) -> str | None:
    direct = first_value(traveller, ["fullName", "full_name", "name"])
    if clean(direct):
        return str(direct).strip()
    first = traveller_value(traveller, "FirstName", "LatinFirstName", "firstname", "first_name")
    middle = traveller_value(traveller, "MiddleName", "LatinMiddleName", "middlename", "middle_name")
    last = traveller_value(traveller, "LastName", "LatinLastName", "lastname", "last_name", "surname")
    parts = [first, middle, last]
    name = " ".join(part for part in parts if part)
    return name or None


def passenger_names(order: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for traveller in order.get("travellers") or []:
        if not isinstance(traveller, dict):
            continue
        name = passenger_name(traveller)
        if name and name not in names:
            names.append(name)
    return names


def segment_id(segment: dict[str, Any]) -> str:
    value = first_value(segment, ["id", "segmentId", "segment_id"])
    return str(value).strip() if clean(value) else ""


def ticket_numbers_for_segment(order: dict[str, Any], sid: str) -> list[str]:
    numbers: list[str] = []
    for traveller in order.get("travellers") or []:
        if not isinstance(traveller, dict):
            continue
        for ticket in traveller.get("tickets") or []:
            ticket_obj = as_dict(ticket)
            number = first_value(ticket_obj, ["number", "ticketNumber", "ticket_number", "ticket"])
            if not clean(number):
                continue
            coupons = ticket_obj.get("coupons") or []
            if sid and coupons:
                matched = False
                for coupon in coupons:
                    coupon_obj = as_dict(coupon)
                    coupon_sid = segment_id(as_dict(coupon_obj.get("segment"))) or str(first_value(coupon_obj, ["segmentId", "segment_id"]) or "")
                    if coupon_sid == sid:
                        matched = True
                        break
                if not matched:
                    continue
            numbers.append(str(number).strip())
    return sorted(dict.fromkeys(numbers))


def seat_label(item: dict[str, Any]) -> str | None:
    direct = first_value(item, ["number", "seatNumber", "seat_number"])
    if clean(direct):
        return str(direct).strip()
    seat = as_dict(item.get("seat"))
    direct = first_value(seat, ["number", "seatNumber", "seat_number"])
    if clean(direct):
        return str(direct).strip()
    row = first_value(item, ["row"]) or first_value(seat, ["row"])
    letter = first_value(item, ["letter"]) or first_value(seat, ["letter"])
    if clean(row) and clean(letter):
        return f"{row}{letter}"
    return None


def seats_for_segment(order: dict[str, Any], sid: str) -> list[str]:
    seats: list[str] = []
    for traveller in order.get("travellers") or []:
        if not isinstance(traveller, dict):
            continue
        containers = [as_dict(traveller.get("services")), as_dict(traveller.get("preselectedServices"))]
        for container in containers:
            for seat in container.get("seats") or []:
                seat_obj = as_dict(seat)
                seat_sid = segment_id(as_dict(seat_obj.get("segment"))) or str(first_value(seat_obj, ["segmentId", "segment_id"]) or "")
                if sid and seat_sid and seat_sid != sid:
                    continue
                label = seat_label(seat_obj)
                if label:
                    seats.append(label)
    return sorted(dict.fromkeys(seats))


def service_segment_ids(item: dict[str, Any]) -> list[str]:
    raw = item.get("segmentIds") or item.get("segment_ids") or item.get("segments") or []
    if isinstance(raw, list):
        return [str(as_dict(x).get("id") if isinstance(x, dict) else x).strip() for x in raw if clean(x)]
    if clean(raw):
        return [str(raw).strip()]
    return []


def service_label(item: dict[str, Any]) -> str | None:
    service = as_dict(item.get("service"))
    value = first_value(service, ["name", "title", "description", "type", "gdsType"])
    if not clean(value):
        value = first_value(item, ["name", "title", "description", "type", "gdsType"])
    return str(value).strip() if clean(value) else None


def baggage_for_segment(order: dict[str, Any], sid: str) -> list[str]:
    values: list[str] = []
    for traveller in order.get("travellers") or []:
        if not isinstance(traveller, dict):
            continue
        services = as_dict(traveller.get("services"))
        buckets = [
            as_dict(services.get("brandIncludedServices")).get("services") or [],
            as_dict(services.get("gdsServices")).get("services") or [],
        ]
        for bucket in buckets:
            for item in bucket:
                item_obj = as_dict(item)
                segment_ids = service_segment_ids(item_obj)
                if sid and segment_ids and sid not in segment_ids:
                    continue
                label = service_label(item_obj)
                if not label:
                    continue
                haystack = json.dumps(item_obj, ensure_ascii=False).upper()
                if any(word in haystack for word in ("BAG", "BAGGAGE", "LUGGAGE", "БАГАЖ")):
                    values.append(label)
    return sorted(dict.fromkeys(values))


def status_text(segment: dict[str, Any], order: dict[str, Any]) -> str:
    parts: list[str] = []
    for value in [segment.get("status"), order.get("status"), order.get("paymentStatus")]:
        if clean(value):
            text = str(value).strip()
            if text not in parts:
                parts.append(text)
    if not parts:
        return "confirmed"
    return " / ".join(parts)


def fare_text(group: dict[str, Any]) -> str | None:
    family = as_dict(group.get("fareFamily"))
    fare_group = as_dict(group.get("fareGroup"))
    value = first_value(family, ["title", "name", "id"]) or first_value(fare_group, ["name", "title", "id"])
    return str(value).strip() if clean(value) else None


def convert_to_itinerary(data: dict[str, Any], tz_map: dict[str, str], booking_url: str | None = None) -> dict[str, Any]:
    order = find_order(data)
    if not order:
        die("no Red Wings order found")
    assert order is not None

    booking_reference = str(first_value(order, ["locator", "pnr", "bookingReference"]) or "").strip() or None
    passengers = passenger_names(order)
    flights: list[dict[str, Any]] = []
    missing_tz: set[str] = set()

    for seg, group in collect_segments(order):
        dep = as_dict(seg.get("departure"))
        arr = as_dict(seg.get("arrival"))
        dep_code = point_airport(dep)
        arr_code = point_airport(arr)
        for code in (dep_code, arr_code):
            if code and code not in tz_map:
                missing_tz.add(code)
        if missing_tz:
            continue
        dep_local = point_local(dep)
        arr_local = point_local(arr)
        if not dep_code or not arr_code or not dep_local or not arr_local:
            die("Red Wings segment is missing route or local time fields")

        sid = segment_id(seg)
        flight: dict[str, Any] = {
            "carrier": first_value(airline(seg, "marketingAirline"), ["name"]) or first_value(airline(seg, "operatingAirline"), ["name"]) or "Red Wings",
            "flight_number": flight_number(seg),
            "departure": {
                "airport": dep_code,
                "city": point_city(dep, dep_code),
                "terminal": first_value(dep, ["terminal"]),
                "local": dep_local,
                "tz": tz_map[dep_code],
            },
            "arrival": {
                "airport": arr_code,
                "city": point_city(arr, arr_code),
                "terminal": first_value(arr, ["terminal"]),
                "local": arr_local,
                "tz": tz_map[arr_code],
            },
            "pnr": booking_reference,
            "passengers": passengers,
            "status": status_text(seg, order),
            "fare": fare_text(group),
        }
        tickets = ticket_numbers_for_segment(order, sid)
        if tickets:
            flight["ticket_number"] = ", ".join(tickets)
        seats = seats_for_segment(order, sid)
        if seats:
            flight["seat"] = ", ".join(seats)
        baggage = baggage_for_segment(order, sid)
        if baggage:
            flight["baggage"] = ", ".join(baggage)
        aircraft = as_dict(seg.get("aircraft"))
        aircraft_name = first_value(aircraft, ["name", "title"])
        if clean(aircraft_name):
            flight["aircraft"] = str(aircraft_name).strip()
        flights.append(flight)

    if missing_tz:
        codes = ", ".join(sorted(missing_tz))
        die(f"missing timezone for airport(s): {codes}; rerun with --tz CODE=Area/City")
    if not flights:
        die("no flight segments found in Red Wings response")

    return {
        "schema_version": "flight-calendar-ics-itinerary.v1",
        "calendar_name": "Red Wings flights",
        "booking_reference": booking_reference,
        "links": [booking_url] if booking_url else [],
        "passengers": passengers,
        "alarms_minutes": [1440, 180],
        "notes": "Сформировано из данных страницы управления бронированием Red Wings.",
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

    parser = argparse.ArgumentParser(description="Convert Red Wings/Websky manage-booking data to flight-calendar-ics JSON.")
    parser.add_argument("--url", help="Red Wings direct email/manage link shaped #/find/<PNR>/<ACCESS_KEY>/Submit")
    parser.add_argument("--pnr", help="Booking locator, if not using --url")
    parser.add_argument("--access-key", dest="finder_code", help="Access key from the direct email/manage link, if not using --url")
    parser.add_argument("--output-json", required=True, type=Path, help="Where to write itinerary JSON")
    parser.add_argument("--tz", action="append", default=[], help="Timezone override CODE=Area/City; repeatable")
    parser.add_argument("--graphql-endpoint", help="Override Websky GraphQL endpoint for diagnostics/tests")
    args = parser.parse_args(argv)

    locator, finder_code, booking_url = parse_redwings_source(args.url, args.pnr, args.finder_code)
    order = fetch_redwings_order(locator, finder_code, graphql_endpoint=args.graphql_endpoint)
    tz_map = {**DEFAULT_AIRPORT_TZ, **parse_tz_overrides(args.tz)}
    itinerary = convert_to_itinerary(order, tz_map, booking_url=booking_url)
    secure_write_text(args.output_json, json.dumps(itinerary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"ok": True, "segments": len(itinerary["flights"]), "json": str(args.output_json)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
