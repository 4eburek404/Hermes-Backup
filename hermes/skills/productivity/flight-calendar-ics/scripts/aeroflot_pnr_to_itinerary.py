#!/usr/bin/env python3
"""Fetch Aeroflot manage-booking data and convert it to flight-calendar-ics JSON.

Input can be a share URL containing pnrKey/pnrLocator or the two values passed
explicitly. The script does not print PNR, passenger names, ticket numbers, or
full source URLs. It always writes the Aeroflot booking URL into the requested
JSON/ICS output so imported calendar events retain a direct booking link on any
device.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

AEROFLOT_BASE = "https://www.aeroflot.ru"
AEROFLOT_PNR_API = AEROFLOT_BASE + "/se/api/app/pnr/view/v3"

# Small safe default set. Add per trip with --tz CODE=Area/City when missing.
DEFAULT_AIRPORT_TZ = {
    "SVO": "Europe/Moscow",
    "DME": "Europe/Moscow",
    "VKO": "Europe/Moscow",
    "ZIA": "Europe/Moscow",
    "LED": "Europe/Moscow",
    "SVX": "Asia/Yekaterinburg",
}


def secure_write_text(path: Path, text: str) -> None:
    """Write private Aeroflot booking artifacts as owner-only files."""
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


def die(message: str, code: int = 2) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def parse_pnr_source(url: str | None, locator: str | None, key: str | None) -> tuple[str, str, str]:
    booking_url = url.strip() if url else None
    if booking_url:
        qs = parse_qs(urlparse(booking_url).query)
        locator = locator or (qs.get("pnrLocator") or qs.get("pnr_locator") or [None])[0]
        key = key or (qs.get("pnrKey") or qs.get("pnr_key") or [None])[0]
    if not locator or not key:
        die("provide --url containing pnrKey/pnrLocator or both --pnr-locator and --pnr-key")
    locator = locator.strip().upper()
    key = key.strip()
    if not re.fullmatch(r"[A-Z0-9]{5,8}", locator):
        die("PNR locator format looks invalid")
    if not re.fullmatch(r"[0-9a-fA-F]{64,256}", key):
        die("PNR key format looks invalid")
    if not booking_url:
        booking_url = AEROFLOT_BASE + "/ru-ru/pnr?" + urlencode({"pnrKey": key, "pnrLocator": locator})
    return locator, key, booking_url


def fetch_aeroflot_pnr(locator: str, key: str, *, timeout: int = 45) -> dict[str, Any]:
    body = json.dumps(
        {"pnr_locator": locator, "pnr_key": key, "lang": "ru", "country": "ru"},
        ensure_ascii=False,
    ).encode("utf-8")
    req = Request(
        AEROFLOT_PNR_API,
        data=body,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
            "Content-Type": "application/json",
            "X-App-Identity": "0",
            "Origin": AEROFLOT_BASE,
            "Referer": AEROFLOT_BASE + "/sb/pnr/app/ru-ru",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            content_type = resp.headers.get("Content-Type", "")
            status = getattr(resp, "status", 200)
    except HTTPError as exc:
        raw = exc.read()
        content_type = exc.headers.get("Content-Type", "")
        status = exc.code
    text = raw.decode("utf-8", errors="replace")
    if "text/html" in content_type or text.lstrip().startswith("<!"):
        if "ngenix" in text.lower() or "проверка вашего веб-браузера" in text.lower():
            die("Aeroflot returned an Ngenix browser-check page; retry later or fetch via a browser session")
        die(f"Aeroflot returned HTML instead of JSON (HTTP {status})")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        die(f"Aeroflot returned non-JSON response (HTTP {status}): {exc}")
    if not obj.get("success"):
        err = obj.get("error") or {}
        die(f"Aeroflot PNR API returned success=false: {err.get('type') or err.get('value') or 'unknown error'}")
    data = obj.get("data")
    if not isinstance(data, dict):
        die("Aeroflot PNR API response has no data object")
    return data


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


def first_ticket_number(data: dict[str, Any]) -> str | None:
    for pax in data.get("passengers") or []:
        for ticket in ((pax.get("ticketing_documents") or {}).get("tickets") or []):
            number = ticket.get("number")
            if number:
                return str(number)
    return None


def passenger_names(data: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for pax in data.get("passengers") or []:
        name = " ".join(str(x) for x in [pax.get("first_name"), pax.get("last_name")] if x)
        if name:
            names.append(name)
    return names


def clean(value: Any) -> Any:
    return None if value in (None, "", []) else value


def terminal_name(location: dict[str, Any]) -> str | None:
    return clean(location.get("terminal_code")) or clean(location.get("terminal_name"))


def convert_to_itinerary(data: dict[str, Any], tz_map: dict[str, str], booking_url: str | None = None) -> dict[str, Any]:
    ticket_number = first_ticket_number(data)
    flights: list[dict[str, Any]] = []
    missing_tz: set[str] = set()

    for leg in data.get("legs") or []:
        for seg in leg.get("segments") or []:
            dep = seg.get("origin") or {}
            arr = seg.get("destination") or {}
            dep_code = str(dep.get("airport_code") or "").upper()
            arr_code = str(arr.get("airport_code") or "").upper()
            for code in [dep_code, arr_code]:
                if code and code not in tz_map:
                    missing_tz.add(code)
            if missing_tz:
                continue

            notes: list[str] = []
            for label, value in [
                ("Время в пути", seg.get("flight_time_name")),
                ("Самолёт", seg.get("aircraft_type_name")),
                ("Тариф", seg.get("fare_group_name")),
                ("Питание", seg.get("meal_names")),
            ]:
                if clean(value):
                    notes.append(f"{label}: {value}")
            for warning in data.get("warnings") or []:
                if isinstance(warning, dict) and warning.get("description"):
                    notes.append(str(warning["description"]))

            franchise = seg.get("franchise_info")
            baggage = "; ".join(str(x) for x in franchise if x) if isinstance(franchise, list) and franchise else None
            airline_code = seg.get("airline_code") or "SU"
            flight_number = f"{airline_code}{seg.get('flight_number')}"
            flight = {
                "carrier": seg.get("airline_name") or "Аэрофлот",
                "flight_number": flight_number,
                "departure": {
                    "airport": dep_code,
                    "city": dep.get("city_name"),
                    "terminal": terminal_name(dep),
                    "local": str(seg.get("departure") or "").replace(" ", "T"),
                    "tz": tz_map[dep_code],
                },
                "arrival": {
                    "airport": arr_code,
                    "city": arr.get("city_name"),
                    "terminal": terminal_name(arr),
                    "local": str(seg.get("arrival") or "").replace(" ", "T"),
                    "tz": tz_map[arr_code],
                },
                "baggage": baggage,
                "ticket_number": ticket_number,
                "pnr": data.get("pnr_locator"),
                "status": "confirmed" if seg.get("status_code") == "HK" else (seg.get("status_name") or "confirmed"),
                "cabin": seg.get("cabin_name"),
                "fare": seg.get("fare_group_name"),
                "aircraft": seg.get("aircraft_type_name"),
            }
            notes_text = "\n".join(notes)
            if notes_text:
                flight["notes"] = notes_text
            flights.append(flight)

    if missing_tz:
        codes = ", ".join(sorted(missing_tz))
        die(f"missing timezone for airport(s): {codes}; rerun with --tz CODE=Area/City")
    if not flights:
        die("no flight segments found in Aeroflot response")

    return {
        "schema_version": "flight-calendar-ics-itinerary.v1",
        "calendar_name": "Aeroflot flight",
        "booking_reference": data.get("pnr_locator"),
        "passengers": passenger_names(data),
        "alarms_minutes": [1440, 180],
        "links": [booking_url] if booking_url else [],
        "notes": "Сформировано из данных страницы управления бронированием Аэрофлота.",
        "flights": flights,
    }


def maybe_generate_ics(input_json: Path, output_ics: Path) -> None:
    script = Path(__file__).resolve().with_name("make_flight_ics.py")
    cmd = [sys.executable, str(script), "--input", str(input_json), "--output", str(output_ics)]
    result = subprocess.run(cmd, text=True, capture_output=True, timeout=30)
    if result.returncode != 0:
        die("ICS generation failed:\n" + (result.stderr or result.stdout))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert Aeroflot PNR URL/API data to flight-calendar-ics JSON/ICS.")
    parser.add_argument("--url", help="Aeroflot PNR share URL containing pnrKey and pnrLocator")
    parser.add_argument("--pnr-locator", help="Booking locator, if not using --url")
    parser.add_argument("--pnr-key", help="PNR key, if not using --url")
    parser.add_argument("--output-json", required=True, type=Path, help="Where to write itinerary JSON")
    parser.add_argument("--output-ics", type=Path, help="Optional .ics path to generate immediately")
    parser.add_argument("--tz", action="append", default=[], help="Timezone override CODE=Area/City; repeatable")
    args = parser.parse_args(argv)

    locator, key, booking_url = parse_pnr_source(args.url, args.pnr_locator, args.pnr_key)
    tz_map = {**DEFAULT_AIRPORT_TZ, **parse_tz_overrides(args.tz)}
    data = fetch_aeroflot_pnr(locator, key)
    itinerary = convert_to_itinerary(data, tz_map, booking_url=booking_url)
    secure_write_text(args.output_json, json.dumps(itinerary, ensure_ascii=False, indent=2) + "\n")

    if args.output_ics:
        args.output_ics.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        maybe_generate_ics(args.output_json, args.output_ics)

    segments = [
        {
            "flight_number": f["flight_number"],
            "route": f"{f['departure']['airport']}->{f['arrival']['airport']}",
            "departure_local": f["departure"]["local"],
            "arrival_local": f["arrival"]["local"],
        }
        for f in itinerary["flights"]
    ]
    print(json.dumps({"ok": True, "segments": segments, "json": str(args.output_json), "ics": str(args.output_ics) if args.output_ics else None}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
