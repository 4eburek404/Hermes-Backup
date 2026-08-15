#!/usr/bin/env python3
"""Fetch Red Wings/Websky manage-booking data and convert it to itinerary JSON.

Red Wings uses a Websky booking SPA. The reliable agent path is the direct
email/manage-booking route ``#/find/<PNR>/<ACCESS_KEY>/Submit``: the PNR and
access key are posted to Websky's public GraphQL ``FindOrder`` operation, then
mapped into the provider-agnostic itinerary schema.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, unquote, urlparse

from flight_calendar import carrier_http
from flight_calendar.common import die


REDWINGS_BOOKING_BASE = "https://flyredwings.com/booking/"
REDWINGS_GRAPHQL_ENDPOINT = "https://wz.webskyx.com/graphql/query/nemo"


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
            airport { iata city { name } }
          }
          arrival {
            date
            time
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
          departure { date time airport { iata city { name } } }
          arrival { date time airport { iata city { name } } }
        }
      }
    }
    travellers {
      id
      type
      values { type name value }
      tickets { number }
    }
  }
}
""".strip()


def clean(value: Any) -> bool:
    return value not in (None, "", [])


def first_value(obj: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = obj.get(key)
        if clean(value):
            return value
    return None


def parse_redwings_source(
    url: str | None, pnr: str | None, finder_code: str | None
) -> tuple[str, str, str]:
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
            die(
                "Red Wings order page URL is not enough; provide a direct email/manage link shaped #/find/<PNR>/<ACCESS_KEY>/Submit"
            )

    if not pnr or not finder_code:
        die(
            "provide --url shaped #/find/<PNR>/<ACCESS_KEY>/Submit or both --pnr and --access-key"
        )

    locator = str(pnr).strip().upper()
    code = str(finder_code).strip()
    if not re.fullmatch(r"[A-Z0-9]{5,8}", locator):
        die("Red Wings PNR format looks invalid")
    if not re.fullmatch(r"[^\s/]{2,256}", code):
        die("Red Wings access key format looks invalid")
    if not booking_url:
        booking_url = (
            REDWINGS_BOOKING_BASE + f"#/find/{locator}/{quote(code, safe='')}/Submit"
        )
    return locator, code, booking_url


def browser_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    return carrier_http.browser_headers(
        {
            "Origin": "https://flyredwings.com",
            "Referer": REDWINGS_BOOKING_BASE,
            "Cache-Control": "no-cache",
            **(extra or {}),
        }
    )


def post_json(url: str, body: dict[str, Any], *, timeout: int = 45) -> Any:
    return carrier_http.request_json(
        url,
        json_body=body,
        headers=browser_headers(),
        timeout=timeout,
        label="Red Wings GraphQL",
    )


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
        die(
            "Red Wings GraphQL returned errors"
            + (": " + "; ".join(messages) if messages else "")
        )
    if not find_order(data):
        die("no Red Wings order found")
    return data


def find_order(data: dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(data.get("data"), dict) and isinstance(
        data["data"].get("FindOrder"), dict
    ):
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
    raw = (
        str(
            segment.get("flightNumber")
            or segment.get("flight_number")
            or segment.get("number")
            or ""
        )
        .strip()
        .upper()
    )
    if not raw:
        die("Red Wings segment has no flight number")
    carrier = (
        str(
            first_value(airline(segment, "marketingAirline"), ["iata", "code"])
            or first_value(airline(segment, "operatingAirline"), ["iata", "code"])
            or "WZ"
        )
        .strip()
        .upper()
    )
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


def point_city(point: dict[str, Any]) -> str | None:
    airport = as_dict(point.get("airport"))
    city = as_dict(airport.get("city"))
    value = (
        first_value(city, ["name", "title"])
        or first_value(airport, ["city", "cityName"])
        or first_value(point, ["city", "cityName"])
    )
    return str(value).strip() if clean(value) else None


def point_local(point: dict[str, Any]) -> str:
    date = str(first_value(point, ["date", "localDate", "local_date"]) or "").strip()
    time = str(first_value(point, ["time", "localTime", "local_time"]) or "").strip()
    if date and "T" in date and not time:
        return date.replace(" ", "T", 1)[:16]
    if date and time:
        return f"{date[:10]}T{time[:5]}"
    combined = str(first_value(point, ["local", "datetime", "dateTime"]) or "").strip()
    return combined.replace(" ", "T", 1)[:16]


def collect_segments(
    order: dict[str, Any],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    flight = as_dict(order.get("flight"))
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    groups = flight.get("segmentGroups") or []
    if isinstance(groups, list):
        for group in groups:
            group_obj = as_dict(group)
            for seg in group_obj.get("segments") or []:
                seg_obj = as_dict(
                    seg.get("segment")
                    if isinstance(seg, dict) and "segment" in seg
                    else seg
                )
                if seg_obj:
                    out.append((seg_obj, group_obj))
    if out:
        return out
    for seg in flight.get("segments") or []:
        seg_obj = as_dict(
            seg.get("segment") if isinstance(seg, dict) and "segment" in seg else seg
        )
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
    first = traveller_value(
        traveller, "FirstName", "LatinFirstName", "firstname", "first_name"
    )
    last = traveller_value(
        traveller, "LastName", "LatinLastName", "lastname", "last_name", "surname"
    )
    parts = [last, first]
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


def ticket_numbers(order: dict[str, Any]) -> list[str]:
    numbers: list[str] = []
    for traveller in order.get("travellers") or []:
        if not isinstance(traveller, dict):
            continue
        for ticket in traveller.get("tickets") or []:
            ticket_obj = as_dict(ticket)
            number = first_value(
                ticket_obj, ["number", "ticketNumber", "ticket_number", "ticket"]
            )
            if clean(number):
                numbers.append(str(number).strip())
    return sorted(dict.fromkeys(numbers))


def status_text(segment: dict[str, Any], order: dict[str, Any]) -> str:
    parts: list[str] = []
    for value in [
        segment.get("status"),
        order.get("status"),
        order.get("paymentStatus"),
    ]:
        if clean(value):
            text = str(value).strip()
            if text not in parts:
                parts.append(text)
    if not parts:
        return "confirmed"
    return " / ".join(parts)


def convert_to_itinerary(
    data: dict[str, Any], tz_map: dict[str, str], booking_url: str | None = None
) -> dict[str, Any]:
    order = find_order(data)
    if not order:
        die("no Red Wings order found")
    assert order is not None

    pnr = (
        str(first_value(order, ["locator", "pnr", "bookingReference"]) or "").strip()
        or None
    )
    passengers = passenger_names(order)
    flights: list[dict[str, Any]] = []
    missing_tz: set[str] = set()

    for seg, _group in collect_segments(order):
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

        departure: dict[str, Any] = {
            "airport": dep_code,
            "local": dep_local,
            "tz": tz_map[dep_code],
        }
        dep_city = point_city(dep)
        if dep_city:
            departure["city"] = dep_city
        arrival: dict[str, Any] = {
            "airport": arr_code,
            "local": arr_local,
            "tz": tz_map[arr_code],
        }
        arr_city = point_city(arr)
        if arr_city:
            arrival["city"] = arr_city
        flight: dict[str, Any] = {
            "flight_number": flight_number(seg),
            "departure": departure,
            "arrival": arrival,
            "status": status_text(seg, order),
        }
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

    itinerary: dict[str, Any] = {
        "schema_version": "flight-calendar-ics-itinerary.v1",
        "flights": flights,
    }
    tickets = ticket_numbers(order)
    if pnr:
        itinerary["pnr"] = pnr
    if passengers:
        itinerary["passengers"] = passengers
    if tickets:
        itinerary["ticket_number"] = ", ".join(tickets)
    if booking_url:
        itinerary["booking_url"] = booking_url
    return itinerary
