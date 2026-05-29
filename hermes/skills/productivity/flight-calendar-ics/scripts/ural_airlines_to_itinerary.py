#!/usr/bin/env python3
"""Fetch Ural Airlines manage-booking data and convert it to itinerary JSON.

The Ural Airlines manage-booking frontend is a JavaScript SPA. The public
configuration needed for Reservation lookup is loaded from the current frontend
(`/<version>/env/env.json`) at runtime; no local `.env` or cached private config
file is required for the normal flow.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, NamedTuple
from urllib.error import HTTPError
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

URAL_SERVICE_BASE = "https://service.uralairlines.ru/"
DEFAULT_ENV_PATH = "/<version>/env/env.json"

DEFAULT_AIRPORT_TZ = {
    "DME": "Europe/Moscow",
    "SVO": "Europe/Moscow",
    "VKO": "Europe/Moscow",
    "ZIA": "Europe/Moscow",
    "LED": "Europe/Moscow",
    "SVX": "Asia/Yekaterinburg",
    "AER": "Europe/Moscow",
    "KUF": "Europe/Samara",
    "KZN": "Europe/Moscow",
    "OVB": "Asia/Novosibirsk",
    "TJM": "Asia/Yekaterinburg",
    "UFA": "Asia/Yekaterinburg",
}

DEFAULT_AIRPORT_CITY = {
    "DME": "Москва",
    "SVO": "Москва",
    "VKO": "Москва",
    "ZIA": "Москва",
    "LED": "Санкт-Петербург",
    "SVX": "Екатеринбург",
    "AER": "Сочи",
    "KUF": "Самара",
    "KZN": "Казань",
    "OVB": "Новосибирск",
    "TJM": "Тюмень",
    "UFA": "Уфа",
}


class FrontendAssets(NamedTuple):
    base_url: str
    env_url: str
    helper_js_url: str
    app_js_url: str


def die(message: str) -> None:
    raise ValueError(message)


def http_text(url: str, *, timeout: int = 45, headers: dict[str, str] | None = None) -> str:
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        **(headers or {}),
    })
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
    if status >= 400:
        die(f"Ural Airlines frontend/API returned HTTP {status} ({content_type})")
    return text


def http_json(url: str, *, timeout: int = 45, headers: dict[str, str] | None = None) -> Any:
    text = http_text(url, timeout=timeout, headers={"Accept": "application/json", **(headers or {})})
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        die(f"Ural Airlines returned non-JSON response from {urlparse(url).path}: {exc}")


def post_json(url: str, body: dict[str, Any], *, timeout: int = 45, headers: dict[str, str] | None = None) -> Any:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = Request(
        url,
        data=payload,
        method="POST",
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
            "Content-Type": "application/json",
            **(headers or {}),
        },
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = getattr(resp, "status", 200)
            content_type = resp.headers.get("Content-Type", "")
    except HTTPError as exc:
        raw = exc.read()
        status = exc.code
        content_type = exc.headers.get("Content-Type", "")
    text = raw.decode("utf-8", errors="replace")
    if status >= 400:
        die(f"Ural Airlines API returned HTTP {status} ({content_type})")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        die(f"Ural Airlines API returned non-JSON response from {urlparse(url).path}: {exc}")


def parse_ural_source(url: str | None, pnr: str | None, last_name: str | None) -> tuple[str, str, str]:
    booking_url = url.strip() if url else None
    if booking_url:
        parsed = urlparse(booking_url)
        qs = parse_qs(parsed.query)
        redirect_target = (qs.get("u") or qs.get("url") or [None])[0]
        if redirect_target and "service.uralairlines.ru" in redirect_target:
            booking_url = redirect_target
            parsed = urlparse(booking_url)
            qs = parse_qs(parsed.query)
        pnr = pnr or (qs.get("pnr") or qs.get("pnrNumber") or qs.get("pnrnumber") or [None])[0]
        last_name = last_name or (qs.get("lastName") or qs.get("lastname") or qs.get("surname") or [None])[0]
    if not pnr or not last_name:
        die("provide --url containing pnr/lastName or both --pnr and --last-name")
    locator = pnr.strip().upper()
    surname = last_name.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{5,8}", locator):
        die("Ural Airlines PNR format looks invalid")
    if not re.fullmatch(r"[A-ZА-ЯЁ' -]{2,80}", surname, flags=re.IGNORECASE):
        die("Ural Airlines last name format looks invalid")
    if not booking_url:
        booking_url = URAL_SERVICE_BASE + "?" + urlencode({"pnr": locator, "lastName": surname})
    return locator, surname, booking_url


def discover_frontend_assets(frontend_base: str | None = None, *, timeout: int = 45) -> FrontendAssets:
    base = (frontend_base or URAL_SERVICE_BASE).rstrip("/") + "/"
    html = http_text(base, timeout=timeout, headers={"Accept": "text/html"})
    asset_paths = re.findall(r"(?:src|href)=[\"']?([^\"'\s>]+)", html)

    app_path = next((p for p in asset_paths if re.search(r"/js/app\.[^/]+\.js(?:\?.*)?$", p)), None)
    helper_path = next((p for p in asset_paths if re.search(r"/\d+/[0-9a-f]{32}\.js(?:\?.*)?$", p)), None)

    version = None
    for path in asset_paths:
        match = re.search(r"/(\d+)/(?:js/|css/|env/|[0-9a-f]{32}\.js)", path)
        if match:
            version = match.group(1)
            break
    if not version:
        version = "37898"
    if not app_path:
        app_path = f"/{version}/js/app.js"
    if not helper_path:
        die("could not find Ural Airlines frontend API-key helper script in shell HTML")

    return FrontendAssets(
        base_url=base,
        env_url=urljoin(base, f"/{version}/env/env.json"),
        helper_js_url=urljoin(base, helper_path.split("?", 1)[0]),
        app_js_url=urljoin(base, app_path.split("?", 1)[0]),
    )


def parse_api_key_methods(app_js: str) -> list[str]:
    methods = re.findall(r'window\["([0-9a-f]{32})"\]\(t,e\.getters,u\.default\)', app_js)
    if not methods:
        die("could not find Ural Airlines API-key helper calls in frontend bundle")
    # Keep order from the axios interceptor: the first helper may be a no-op, the second sets X-Api-Key.
    deduped: list[str] = []
    for name in methods:
        if name not in deduped:
            deduped.append(name)
    return deduped


def compute_timestamp_diff(api_url: str, *, timeout: int = 45) -> int:
    try:
        server_seconds = http_json(urljoin(api_url.rstrip("/") + "/", "settings/CurrentDateUtc"), timeout=timeout)
        return int(float(server_seconds) * 1000 - time.time() * 1000)
    except Exception:
        # The header generator only needs a numeric timestampDiff. Zero is safer than letting
        # the obfuscated helper produce an "undefined"-interleaved header.
        return 0


def generate_api_key_header(helper_js: str, env: dict[str, Any], methods: list[str]) -> str:
    fd, helper_path = tempfile.mkstemp(prefix="ural-api-helper-", suffix=".js")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(helper_js)
        os.chmod(helper_path, 0o600)
        node_program = r'''
const fs = require('fs');
const vm = require('vm');
const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
const code = fs.readFileSync(payload.helperPath, 'utf8');
const env = payload.env || {};
if (typeof env.timestampDiff === 'undefined') env.timestampDiff = 0;
const sandbox = {
  window: {},
  console: {log: () => {}, error: () => {}},
  Date: Date,
  Math: Math,
  setTimeout: setTimeout,
  clearTimeout: clearTimeout,
  btoa: (s) => Buffer.from(String(s), 'binary').toString('base64')
};
sandbox.global = sandbox;
sandbox.globalThis = sandbox;
vm.runInNewContext(code, sandbox, {timeout: 5000});
const cfg = {headers: {common: {}}, apiKeyType: 'default'};
const getters = {
  'API_MODULE/GET_API_KEY': (type) => (type === 'checkIn' && env.API_KEY_CHECK_IN) ? env.API_KEY_CHECK_IN : env.API_KEY
};
for (const name of payload.methods || []) {
  const fn = sandbox.window[name] || sandbox[name];
  if (typeof fn === 'function') fn(cfg, getters, env);
}
const value = cfg.headers.common['X-Api-Key'];
if (!value) throw new Error('X-Api-Key was not generated');
if (String(value).includes('undefined')) throw new Error('X-Api-Key contains undefined');
process.stdout.write(String(value));
'''
        payload = json.dumps({"helperPath": helper_path, "env": env, "methods": methods}, ensure_ascii=False)
        try:
            result = subprocess.run(
                ["node", "-e", node_program],
                input=payload,
                text=True,
                capture_output=True,
                timeout=15,
            )
        except FileNotFoundError:
            die("Node.js is required to execute the current Ural Airlines frontend API-key helper")
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "unknown Node.js error").strip().splitlines()[-1]
            die(f"Ural Airlines API-key helper failed: {message}")
        value = result.stdout.strip()
        if not value or "undefined" in value:
            die("Ural Airlines API-key helper produced an invalid header")
        return value
    finally:
        try:
            os.unlink(helper_path)
        except FileNotFoundError:
            pass


def api_headers(api_key_header: str, *, session_key: str | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Content-Type": "application/json",
        "Origin": URAL_SERVICE_BASE.rstrip("/"),
        "Referer": URAL_SERVICE_BASE,
        "Cache-Control": "no-cache",
        "X-Api-Key": api_key_header,
    }
    if session_key:
        headers["X-Session"] = session_key
    return headers


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
    assets = discover_frontend_assets(frontend_base, timeout=timeout)
    env = http_json(assets.env_url, timeout=timeout)
    if not isinstance(env, dict):
        die("Ural Airlines env.json is not a JSON object")
    api_url = str(env.get("API_URL") or "").rstrip("/") + "/"
    if not api_url.startswith("http"):
        die("Ural Airlines env.json has no usable API_URL")
    if not env.get("API_KEY"):
        die("Ural Airlines env.json has no API_KEY")
    env = dict(env)
    env["timestampDiff"] = compute_timestamp_diff(api_url, timeout=timeout)
    app_js = http_text(assets.app_js_url, timeout=timeout)
    methods = parse_api_key_methods(app_js)
    helper_js = http_text(assets.helper_js_url, timeout=timeout)
    api_key_header = generate_api_key_header(helper_js, env, methods)

    session = post_json(api_url + "Session", {}, timeout=timeout, headers=api_headers(api_key_header))
    session_key = None
    if isinstance(session, dict):
        session_key = session.get("sessionKey") or ((session.get("data") or {}).get("sessionKey") if isinstance(session.get("data"), dict) else None)
    if not session_key:
        die("Ural Airlines Session response has no sessionKey")

    query = urlencode({"pnrNumber": locator, "lastName": last_name})
    reservation = http_json(api_url + "Reservation?" + query, timeout=timeout, headers=api_headers(api_key_header, session_key=session_key))
    if not isinstance(reservation, dict):
        die("Ural Airlines Reservation response is not a JSON object")
    if reservation.get("success") is False:
        die("Ural Airlines Reservation API returned success=false")
    return reservation


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
        parts = [pax.get("firstName"), pax.get("middleName"), pax.get("surname")]
        name = " ".join(str(item).strip() for item in parts if clean(item))
        if name:
            names.append(name)
    return names


def tickets_by_flight_reference(data: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for ticket in data.get("tickets") or []:
        number = clean(ticket.get("number"))
        if not number:
            continue
        for ref in ticket.get("flightReferences") or []:
            out.setdefault(str(ref), []).append(str(number))
    return out


def status_text(statuses: Any) -> str | None:
    if isinstance(statuses, list) and statuses:
        joined = ", ".join(str(item) for item in statuses)
        return f"confirmed ({joined})" if "HK" in statuses else joined
    if clean(statuses):
        return str(statuses)
    return "confirmed"


def carrier_name(code: str | None) -> str:
    return "Уральские авиалинии" if (code or "").upper() == "U6" else (code or "")


def convert_to_itinerary(data_or_response: dict[str, Any], tz_map: dict[str, str], booking_url: str | None = None) -> dict[str, Any]:
    if data_or_response.get("success") is False:
        die("Ural Airlines Reservation API returned success=false")
    data = data_or_response.get("data") if isinstance(data_or_response.get("data"), dict) else data_or_response
    if not isinstance(data, dict):
        die("Ural Airlines Reservation response has no data object")

    journey = data.get("journey") or {}
    ticket_map = tickets_by_flight_reference(data)
    flights: list[dict[str, Any]] = []
    missing_tz: set[str] = set()
    flight_groups = [
        ("outbound", journey.get("outboundFlights") or []),
        ("return", journey.get("returnFlights") or []),
        ("separate", journey.get("separateFlights") or []),
    ]

    for _group_name, group_flights in flight_groups:
        for seg in group_flights:
            dep_code = str(seg.get("origin") or "").upper()
            arr_code = str(seg.get("destination") or "").upper()
            for code in [dep_code, arr_code]:
                if code and code not in tz_map:
                    missing_tz.add(code)
            if missing_tz:
                continue

            marketing = str(seg.get("marketingCarrier") or seg.get("operatingCarrier") or "U6").upper()
            raw_flight_number = str(seg.get("flightNumber") or "").strip()
            flight_number = f"{marketing} {raw_flight_number}".strip()
            ref = str(seg.get("referenceNumber") or "")
            ticket_numbers = sorted(set(ticket_map.get(ref, [])))
            notes: list[str] = []
            for label, value in [
                ("Самолёт", seg.get("aircraft")),
                ("Класс бронирования", seg.get("classOfService")),
                ("Тариф", seg.get("commercialFamily")),
                ("Время в пути", seg.get("flightDuration")),
            ]:
                if clean(value):
                    notes.append(f"{label}: {value}")
            baggage = "не указано в бронировании"
            if baggage:
                notes.append("Багаж в данных бронирования не указан")

            flights.append(
                {
                    "carrier": carrier_name(marketing),
                    "flight_number": flight_number,
                    "departure": {
                        "airport": dep_code,
                        "city": DEFAULT_AIRPORT_CITY.get(dep_code),
                        "local": local_datetime(seg.get("departureDate")),
                        "tz": tz_map[dep_code],
                    },
                    "arrival": {
                        "airport": arr_code,
                        "city": DEFAULT_AIRPORT_CITY.get(arr_code),
                        "local": local_datetime(seg.get("arrivalDate")),
                        "tz": tz_map[arr_code],
                    },
                    "pnr": data.get("number"),
                    "ticket_number": ", ".join(ticket_numbers) if ticket_numbers else None,
                    "status": status_text(seg.get("statuses")),
                    "baggage": baggage,
                    "aircraft": seg.get("aircraft"),
                    "cabin": seg.get("classOfService"),
                    "fare": seg.get("commercialFamily"),
                    "notes": "; ".join(notes),
                }
            )

    if missing_tz:
        codes = ", ".join(sorted(missing_tz))
        die(f"missing timezone for airport(s): {codes}; rerun with --tz CODE=Area/City")
    if not flights:
        die("no flight segments found in Ural Airlines response")

    return {
        "calendar_name": "Ural Airlines flights",
        "booking_reference": data.get("number"),
        "links": [booking_url] if booking_url else [],
        "passengers": passenger_names(data),
        "alarms_minutes": [1440, 180],
        "notes": "Сформировано из данных страницы управления бронированием Уральских авиалиний.",
        "flights": flights,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Convert Ural Airlines manage-booking URL/API data to flight-calendar-ics JSON.")
    parser.add_argument("--url", help="Ural Airlines manage-booking URL containing pnr and lastName")
    parser.add_argument("--pnr", help="Booking locator, if not using --url")
    parser.add_argument("--last-name", help="Passenger surname, if not using --url")
    parser.add_argument("--output-json", required=True, type=Path, help="Where to write itinerary JSON")
    parser.add_argument("--tz", action="append", default=[], help="Timezone override CODE=Area/City; repeatable")
    args = parser.parse_args(argv)

    locator, last_name, booking_url = parse_ural_source(args.url, args.pnr, args.last_name)
    reservation = fetch_ural_reservation(locator, last_name, booking_url=booking_url)
    tz_map = {**DEFAULT_AIRPORT_TZ, **parse_tz_overrides(args.tz)}
    itinerary = convert_to_itinerary(reservation, tz_map, booking_url=booking_url)
    args.output_json.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(str(args.output_json), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(itinerary, ensure_ascii=False, indent=2) + "\n")
    os.chmod(args.output_json, 0o600)
    print(json.dumps({"ok": True, "segments": len(itinerary["flights"]), "json": str(args.output_json)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
