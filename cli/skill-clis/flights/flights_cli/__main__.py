from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from . import __version__

U6_CALENDAR_URL = "https://www.uralairlines.ru/ajax.php"
U6_CALENDAR_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.uralairlines.ru/",
    "Accept": "application/json",
    "User-Agent": f"flights-cli/{__version__}",
}

PLUGIN_PATH = Path.home() / ".hermes" / "plugins" / "travelpayouts-flights"
CACHE_DIR = PLUGIN_PATH / "cache"
HERMES_ENV_PATH = Path.home() / ".hermes" / ".env"
GRAPHQL_URL = "https://api.travelpayouts.com/graphql/v1/query"
KUPIBILET_FRONTEND_SEARCH_URL = "https://api-rs-lb.kupibilet.ru/frontend_search"
KUPIBILET_HEADERS = {
    "Accept": "application/json",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "Origin": "https://www.kupibilet.ru",
    "Referer": "https://www.kupibilet.ru/",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
}
DEFAULT_CURRENCY = "RUB"
SUPPORTED_CURRENCIES = {"RUB", "USD", "EUR", "KZT", "BYN", "TRY", "AED"}
DEFAULT_HUBS = ["IST", "SAW", "AYT"]
DEFAULT_ROUTE_ASSEMBLE_LIMIT_PER_PAIR = 10
DEFAULT_KB_ROUTE_OUTBOUND_SECOND_LEG_DAY_OFFSETS = [0, 1]
DEFAULT_KB_ROUTE_RETURN_SECOND_LEG_DAY_OFFSETS = [0, 1, 2]
IATA_RE = re.compile(r"^[A-Z]{3}$")
CARRIER_RE = re.compile(r"^[A-Z0-9]{2,3}$")
TRAVELPAYOUTS_ENV_KEYS = {"TRAVELPAYOUTS_TOKEN", "TRAVELPAYOUTS_MARKER"}
_DOTENV_LOADED_KEYS: set[str] = set()

GRAPHQL_ONE_WAY_QUERY = """
query PricesOneWay(
    $origin: String!,
    $destination: String!,
    $depart_dates: [Date!],
    $direct: Boolean!,
    $currency: String!
) {
    prices_one_way(
        params: {
            origin: $origin,
            destination: $destination,
            depart_dates: $depart_dates,
            direct: $direct
        },
        paging: { limit: 30, offset: 0 },
        sorting: VALUE_ASC,
        grouping: NONE,
        currency: $currency
    ) {
        departure_at
        value
        number_of_changes
        main_airline
        ticket_link
        trip_duration
        duration
        segments {
            departure_at
            arrival_at
            flight_legs {
                origin
                destination
                flight_number
                operating_carrier
                aircraft_code
                departure_at
                arrival_at
            }
            transfers {
                at
                to
                country_code
                duration_seconds
                night_transfer
                visa_required
            }
        }
    }
}
"""

GRAPHQL_ROUND_TRIP_QUERY = """
query PricesRoundTrip(
    $origin: String!,
    $destination: String!,
    $depart_dates: [Date!],
    $return_dates: [Date!]!,
    $direct: Boolean!,
    $currency: String!
) {
    prices_round_trip(
        params: {
            origin: $origin,
            destination: $destination,
            depart_dates: $depart_dates,
            return_dates: $return_dates,
            direct: $direct
        },
        paging: { limit: 30, offset: 0 },
        sorting: VALUE_ASC,
        grouping: NONE,
        currency: $currency
    ) {
        departure_at
        return_at
        value
        number_of_changes
        main_airline
        ticket_link
        trip_duration
        duration
        segments {
            departure_at
            arrival_at
            flight_legs {
                origin
                destination
                flight_number
                operating_carrier
                aircraft_code
                departure_at
                arrival_at
            }
            transfers {
                at
                to
                country_code
                duration_seconds
                night_transfer
                visa_required
            }
        }
    }
}
"""


MULTI_AIRPORT_GROUPS: dict[str, dict[str, Any]] = {
    "istanbul": {
        "label": "Istanbul",
        "airports": ["IST", "SAW"],
        "cross_transfer_min": 90,
        "min_cross_connection_min": 300,
        "note": "IST and SAW are separate airports; separate-ticket transfer needs border, bags, and ground transfer.",
    },
    "moscow": {
        "label": "Moscow",
        "airports": ["SVO", "DME", "VKO"],
        "cross_transfer_min": 90,
        "min_cross_connection_min": 300,
        "note": "SVO, DME, and VKO are separate airports; cross-airport transfer is a high-risk self-transfer.",
    },
    "london": {
        "label": "London",
        "airports": ["LHR", "LGW", "STN", "LTN"],
        "cross_transfer_min": 75,
        "min_cross_connection_min": 300,
        "note": "London airports are separate; acceptable for a stay in London, risky for same-day self-transfer.",
    },
}

SPECIAL_CITY_AIRPORTS = {
    "LON": ["LHR", "LGW", "STN", "LTN"],
    "MOW": ["SVO", "DME", "VKO"],
    "IST": ["IST", "SAW"],
}

AIRPORT_TO_GROUP: dict[str, str] = {}
for group_key, group in MULTI_AIRPORT_GROUPS.items():
    for code in group["airports"]:
        AIRPORT_TO_GROUP[code] = group_key

SINGLE_AIRPORT_NOTES = {
    "AYT": "Antalya is one airport, but leisure/charter schedules can create marginal self-transfer windows.",
    "GYD": "Baku is usually a single-airport hub for this workflow; still verify bags and ticket protection.",
    "DXB": "Dubai DXB is one airport for this workflow, typically reliable but often expensive.",
}

CACHE_NOTE = (
    "Travelpayouts/Aviasales data can be cached; prices and seats must be rechecked before purchase."
)

LOW_COST_CARRIERS = {"FR", "U2", "W6", "W9", "PC", "VF", "XQ", "2S"}
LEISURE_HUBS = {"AYT"}

RISK_PROFILES: dict[str, dict[str, Any]] = {
    "balanced": {
        "description": "Risk first, then price and total elapsed time.",
        "ideal_same_min": 180,
        "ideal_same_max": 420,
        "cross_airport_base": 32,
        "too_short_penalty": 76,
        "missing_time_penalty": 12,
        "night_penalty": 8,
        "api_night_transfer_penalty": 7,
        "visa_transfer_penalty": 52,
        "long_internal_transfer_penalty": 6,
        "leisure_hub_penalty": 7,
        "lowcost_penalty": 4,
        "unpreferred_airport_penalty": {"LTN": 4, "STN": 3},
        "rank_order": ["reject", "risk", "price", "elapsed"],
    },
    "safe": {
        "description": "Best connection quality first; price is secondary.",
        "ideal_same_min": 210,
        "ideal_same_max": 480,
        "cross_airport_base": 42,
        "too_short_penalty": 86,
        "missing_time_penalty": 18,
        "night_penalty": 12,
        "api_night_transfer_penalty": 12,
        "visa_transfer_penalty": 72,
        "long_internal_transfer_penalty": 9,
        "leisure_hub_penalty": 12,
        "lowcost_penalty": 7,
        "unpreferred_airport_penalty": {"LTN": 7, "STN": 6, "SAW": 4},
        "rank_order": ["reject", "risk", "elapsed", "price"],
    },
    "cheap": {
        "description": "Lowest price first among non-rejected itineraries; still demotes unsafe transfers.",
        "ideal_same_min": 150,
        "ideal_same_max": 540,
        "cross_airport_base": 26,
        "too_short_penalty": 72,
        "missing_time_penalty": 10,
        "night_penalty": 5,
        "api_night_transfer_penalty": 4,
        "visa_transfer_penalty": 40,
        "long_internal_transfer_penalty": 3,
        "leisure_hub_penalty": 3,
        "lowcost_penalty": 1,
        "unpreferred_airport_penalty": {},
        "rank_order": ["reject", "price", "risk", "elapsed"],
    },
    "business": {
        "description": "Same-airport, predictable, shorter elapsed time; penalizes budget airports/carriers.",
        "ideal_same_min": 180,
        "ideal_same_max": 360,
        "cross_airport_base": 48,
        "too_short_penalty": 88,
        "missing_time_penalty": 18,
        "night_penalty": 14,
        "api_night_transfer_penalty": 14,
        "visa_transfer_penalty": 76,
        "long_internal_transfer_penalty": 10,
        "leisure_hub_penalty": 13,
        "lowcost_penalty": 9,
        "unpreferred_airport_penalty": {"LTN": 12, "STN": 10, "LGW": 4, "SAW": 5},
        "rank_order": ["reject", "risk", "elapsed", "price"],
    },
}


class CliError(Exception):
    def __init__(self, message: str, *, error_type: str = "error", details: Any = None):
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.details = details


def load_env_file(path: Path = HERMES_ENV_PATH) -> set[str]:
    """Load Travelpayouts auth from Hermes .env without overriding process env."""
    loaded: set[str] = set()
    if not path.exists():
        return loaded
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return loaded
    for line in lines:
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        if raw.startswith("export "):
            raw = raw[len("export ") :].strip()
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        if key not in TRAVELPAYOUTS_ENV_KEYS or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value
        loaded.add(key)
    _DOTENV_LOADED_KEYS.update(loaded)
    return loaded


def auth_presence(key: str) -> dict[str, Any]:
    available = bool(os.getenv(key))
    if not available:
        return {"available": False, "source": "missing"}
    source = "hermes_env" if key in _DOTENV_LOADED_KEYS else "env"
    return {"available": True, "source": source}


@dataclass(slots=True)
class Location:
    input: str
    code: str
    kind: str
    name: str | None = None
    country_code: str | None = None
    airports: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "input": self.input,
            "code": self.code,
            "kind": self.kind,
            "name": self.name,
            "country_code": self.country_code,
            "airports": self.airports or [],
        }


class Store:
    def __init__(self, cache_dir: Path = CACHE_DIR):
        self.cache_dir = cache_dir
        self._cities: list[dict[str, Any]] | None = None
        self._airports: list[dict[str, Any]] | None = None
        self._airlines: list[dict[str, Any]] | None = None
        self._planes: list[dict[str, Any]] | None = None
        self._city_by_code: dict[str, dict[str, Any]] | None = None
        self._airport_by_code: dict[str, dict[str, Any]] | None = None
        self._airports_by_city: dict[str, list[dict[str, Any]]] | None = None

    def load_json(self, filename: str) -> list[dict[str, Any]]:
        path = self.cache_dir / filename
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    @property
    def cities(self) -> list[dict[str, Any]]:
        if self._cities is None:
            self._cities = self.load_json("cities_ru.json")
        return self._cities

    @property
    def airports(self) -> list[dict[str, Any]]:
        if self._airports is None:
            self._airports = self.load_json("airports.json")
        return self._airports

    @property
    def airlines(self) -> list[dict[str, Any]]:
        if self._airlines is None:
            self._airlines = self.load_json("airlines.json")
        return self._airlines

    @property
    def planes(self) -> list[dict[str, Any]]:
        if self._planes is None:
            self._planes = self.load_json("planes.json")
        return self._planes

    @property
    def city_by_code(self) -> dict[str, dict[str, Any]]:
        if self._city_by_code is None:
            self._city_by_code = {
                str(city.get("code", "")).upper(): city
                for city in self.cities
                if city.get("code")
            }
        return self._city_by_code

    @property
    def airport_by_code(self) -> dict[str, dict[str, Any]]:
        if self._airport_by_code is None:
            self._airport_by_code = {
                str(airport.get("code", "")).upper(): airport
                for airport in self.airports
                if airport.get("code")
            }
        return self._airport_by_code

    @property
    def airports_by_city(self) -> dict[str, list[dict[str, Any]]]:
        if self._airports_by_city is None:
            grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for airport in self.airports:
                city_code = str(airport.get("city_code", "")).upper()
                if city_code:
                    grouped[city_code].append(airport)
            self._airports_by_city = dict(grouped)
        return self._airports_by_city

    def cache_counts(self) -> dict[str, int]:
        return {
            "cities": len(self.cities),
            "airports": len(self.airports),
            "airlines": len(self.airlines),
            "planes": len(self.planes),
        }

    def city_name(self, code: str) -> str | None:
        city = self.city_by_code.get(code.upper())
        if not city:
            return None
        return str(city.get("name") or city.get("code") or "")

    def airport_name(self, code: str) -> str | None:
        airport = self.airport_by_code.get(code.upper())
        if not airport:
            return None
        name = airport.get("name")
        if name:
            return str(name)
        city_name = self.city_name(str(airport.get("city_code") or ""))
        return city_name

    def search_cities(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        q = query.strip().lower()
        if not q:
            return []

        exact_code: list[dict[str, Any]] = []
        exact_name: list[dict[str, Any]] = []
        starts_with: list[dict[str, Any]] = []
        contains: list[dict[str, Any]] = []

        for city in self.cities:
            code = str(city.get("code") or "").lower()
            if code == q:
                exact_code.append(city)
                continue

            names = [str(city.get("name") or "").lower()]
            translations = city.get("name_translations")
            if isinstance(translations, dict):
                names.extend(str(value).lower() for value in translations.values() if value)

            matched = False
            for name in names:
                if name == q:
                    exact_name.append(city)
                    matched = True
                    break
                if name.startswith(q):
                    starts_with.append(city)
                    matched = True
                    break
                if q in name:
                    contains.append(city)
                    matched = True
                    break

            if not matched and str(city.get("country_code") or "").lower() == q:
                contains.append(city)

        def ranked(bucket: list[dict[str, Any]]) -> list[dict[str, Any]]:
            return sorted(
                bucket,
                key=lambda city: (
                    str(city.get("code") or "").upper() not in SPECIAL_CITY_AIRPORTS,
                    not bool(city.get("has_flightable_airport")),
                    str(city.get("country_code") or ""),
                    str(city.get("code") or ""),
                ),
            )

        seen: set[str] = set()
        results: list[dict[str, Any]] = []
        for city in ranked(exact_code) + ranked(exact_name) + ranked(starts_with) + ranked(contains):
            code = str(city.get("code") or "").upper()
            if code and code not in seen:
                seen.add(code)
                results.append(city)
            if len(results) >= limit:
                break
        return results

    def resolve_location(self, value: str, *, prefer_airport: bool = False) -> Location:
        raw = value.strip()
        if not raw:
            raise CliError("location is required", error_type="validation_error")
        code = raw.upper()
        if IATA_RE.match(code):
            airport = self.airport_by_code.get(code)
            city = self.city_by_code.get(code)
            if airport and (prefer_airport or not city):
                return Location(
                    input=raw,
                    code=code,
                    kind="airport",
                    name=str(airport.get("name") or code),
                    country_code=str(airport.get("country_code") or "") or None,
                    airports=[code],
                )
            if city:
                airports = [a["code"] for a in self.flightable_airports_for_city(code)]
                if code in SPECIAL_CITY_AIRPORTS:
                    airports = SPECIAL_CITY_AIRPORTS[code]
                return Location(
                    input=raw,
                    code=code,
                    kind="city",
                    name=str(city.get("name") or code),
                    country_code=str(city.get("country_code") or "") or None,
                    airports=airports,
                )
            if airport:
                return Location(
                    input=raw,
                    code=code,
                    kind="airport",
                    name=str(airport.get("name") or code),
                    country_code=str(airport.get("country_code") or "") or None,
                    airports=[code],
                )
            return Location(input=raw, code=code, kind="iata", name=None, airports=[code])

        matches = self.search_cities(raw, limit=6)
        flightable = [city for city in matches if city.get("has_flightable_airport")]
        if len(flightable) == 1:
            city = flightable[0]
            city_code = str(city.get("code") or "").upper()
            airports = [a["code"] for a in self.flightable_airports_for_city(city_code)]
            if city_code in SPECIAL_CITY_AIRPORTS:
                airports = SPECIAL_CITY_AIRPORTS[city_code]
            return Location(
                input=raw,
                code=city_code,
                kind="city",
                name=str(city.get("name") or city_code),
                country_code=str(city.get("country_code") or "") or None,
                airports=airports,
            )
        preferred_special = [
            city
            for city in flightable
            if str(city.get("code") or "").upper() in SPECIAL_CITY_AIRPORTS
        ]
        if len(preferred_special) == 1:
            city = preferred_special[0]
            city_code = str(city.get("code") or "").upper()
            return Location(
                input=raw,
                code=city_code,
                kind="city",
                name=str(city.get("name") or city_code),
                country_code=str(city.get("country_code") or "") or None,
                airports=SPECIAL_CITY_AIRPORTS[city_code],
            )
        if not matches:
            raise CliError(
                f"could not resolve location {raw!r}; use a 3-letter IATA code or a city name",
                error_type="not_found",
            )
        suggestions = [city_to_output(self, city) for city in matches[:6]]
        raise CliError(
            f"ambiguous location {raw!r}; specify an IATA code",
            error_type="disambiguation_needed",
            details={"suggestions": suggestions},
        )

    def flightable_airports_for_city(self, city_code: str) -> list[dict[str, Any]]:
        airports = self.airports_by_city.get(city_code.upper(), [])
        flightable = [
            airport
            for airport in airports
            if airport.get("flightable", True) and str(airport.get("code") or "").isalpha()
        ]
        return sorted(flightable, key=lambda item: str(item.get("code") or ""))


def city_to_output(store: Store, city: dict[str, Any]) -> dict[str, Any]:
    code = str(city.get("code") or "").upper()
    airports = [a["code"] for a in store.flightable_airports_for_city(code)]
    if code in SPECIAL_CITY_AIRPORTS:
        airports = SPECIAL_CITY_AIRPORTS[code]
    translations = city.get("name_translations") if isinstance(city.get("name_translations"), dict) else {}
    return {
        "code": code,
        "name": city.get("name"),
        "name_en": translations.get("en"),
        "country_code": city.get("country_code"),
        "has_flightable_airport": bool(city.get("has_flightable_airport")),
        "airports": airports,
    }


def normalize_iata(value: str, field: str = "IATA") -> str:
    code = value.strip().upper()
    if not IATA_RE.match(code):
        raise CliError(f"{field} must be a 3-letter IATA code, got {value!r}", error_type="validation_error")
    return code


def normalize_carrier_code(value: str, field: str = "carrier") -> str:
    code = str(value or "").strip().upper()
    if not CARRIER_RE.match(code):
        raise CliError(f"{field} must be a 2-3 character airline code, got {value!r}", error_type="validation_error")
    return code


def normalize_carrier_codes(values: list[str] | None, field: str) -> set[str]:
    return {normalize_carrier_code(value, field) for value in (values or [])}


def parse_iso_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise CliError(f"{field} must be YYYY-MM-DD, got {value!r}", error_type="validation_error") from exc


def parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    raw = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def minutes_between(start: str, end: str) -> int | None:
    a = parse_iso_datetime(start)
    b = parse_iso_datetime(end)
    if not a or not b:
        return None
    if (a.tzinfo is None) != (b.tzinfo is None):
        a = a.replace(tzinfo=None)
        b = b.replace(tzinfo=None)
    return int((b - a).total_seconds() // 60)


def clamp_score(value: int | float) -> int:
    return max(0, min(100, int(round(value))))


def normalize_profile(value: str | None) -> str:
    profile = (value or "balanced").strip().lower()
    if profile not in RISK_PROFILES:
        raise CliError(
            f"profile must be one of {', '.join(sorted(RISK_PROFILES))}, got {value!r}",
            error_type="validation_error",
        )
    return profile


def risk_grade(score: int) -> str:
    if score <= 20:
        return "excellent"
    if score <= 40:
        return "good"
    if score <= 70:
        return "risky"
    return "reject"


def is_reject_score(score: int) -> bool:
    return score > 70


def airport_hour(value: str) -> int | None:
    parsed = parse_iso_datetime(value)
    return parsed.hour if parsed else None


def is_night_time(value: str) -> bool:
    hour = airport_hour(value)
    return hour is not None and (hour < 6 or hour >= 23)


def price_value(data: dict[str, Any]) -> int | None:
    raw = data.get("price")
    if raw is None and isinstance(data.get("pricing"), dict):
        raw = data["pricing"].get("price")
    if raw is None:
        return None
    try:
        return max(0, int(float(str(raw).replace(" ", "").replace(",", ""))))
    except (TypeError, ValueError):
        return None


def currency_value(data: dict[str, Any]) -> str | None:
    if isinstance(data.get("currency"), str):
        return data["currency"]
    pricing = data.get("pricing")
    if isinstance(pricing, dict) and isinstance(pricing.get("currency"), str):
        return pricing["currency"]
    return None


def elapsed_minutes(segments: list[dict[str, Any]]) -> int | None:
    if not segments:
        return None
    return minutes_between(str(segments[0].get("departure_at") or ""), str(segments[-1].get("arrival_at") or ""))


def validation_elapsed_minutes(validation: dict[str, Any]) -> int | None:
    journeys = validation.get("journeys")
    if not isinstance(journeys, list):
        return elapsed_minutes(validation["segments"])
    total = 0
    seen = False
    segments_by_index = {segment["index"]: segment for segment in validation["segments"]}
    for journey in journeys:
        indexes = journey.get("segment_indexes") if isinstance(journey, dict) else None
        if not indexes:
            continue
        journey_segments = [segments_by_index[index] for index in indexes if index in segments_by_index]
        elapsed = elapsed_minutes(journey_segments)
        if elapsed is not None:
            total += elapsed
            seen = True
    return total if seen else None


def segment_carriers(segment: dict[str, Any]) -> set[str]:
    carriers: set[str] = set()
    for key in ("carrier", "airline", "operating_carrier", "main_airline"):
        value = segment.get(key)
        if isinstance(value, str) and value.strip():
            code = value.strip().upper()
            if CARRIER_RE.match(code):
                carriers.add(code)
    flight_number = segment.get("flight_number")
    if isinstance(flight_number, str):
        code = carrier_from_flight_number(flight_number)
        if code:
            carriers.add(code)
    return carriers


def itinerary_carriers(segments: list[dict[str, Any]]) -> set[str]:
    carriers: set[str] = set()
    for segment in segments:
        carriers.update(segment_carriers(segment))
    return carriers


def airport_group(code: str) -> dict[str, Any] | None:
    group_key = AIRPORT_TO_GROUP.get(code.upper())
    if not group_key:
        return None
    group = MULTI_AIRPORT_GROUPS[group_key].copy()
    group["key"] = group_key
    return group


def explain_airport(store: Store, code: str) -> dict[str, Any]:
    normalized = normalize_iata(code)
    airport = store.airport_by_code.get(normalized)
    city_code = str(airport.get("city_code") or "") if airport else None
    group = airport_group(normalized)
    data = {
        "code": normalized,
        "known": bool(airport),
        "name": store.airport_name(normalized),
        "city_code": city_code,
        "city_name": store.city_name(city_code or "") if city_code else None,
        "country_code": airport.get("country_code") if airport else None,
        "iata_type": airport.get("iata_type") if airport else None,
        "flightable": airport.get("flightable") if airport else None,
        "group": None,
        "notes": [],
    }
    notes = data["notes"]
    if group:
        data["group"] = {
            "key": group["key"],
            "label": group["label"],
            "airports": group["airports"],
            "cross_transfer_min": group["cross_transfer_min"],
            "min_cross_connection_min": group["min_cross_connection_min"],
        }
        notes.append(group["note"])
    if normalized in SINGLE_AIRPORT_NOTES:
        notes.append(SINGLE_AIRPORT_NOTES[normalized])
    return data


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


def build_kupibilet_payload(origin: str, destination: str, depart_date: str, currency: str) -> dict[str, Any]:
    return {
        "trips": [{"departure": origin, "arrival": destination, "date": depart_date}],
        "travelers": {"adult": 1, "child": 0, "infant": 0},
        "cabin": "economy",
        "agent": "kupibilet",
        "lang": "ru",
        "currency": currency,
        "client_platform": "web",
        "filters": {},
        "sort_by": "price",
        "short_response": False,
    }


def decode_http_body(raw: bytes, content_encoding: str | None) -> bytes:
    encoding = (content_encoding or "").split(";", 1)[0].strip().lower()
    if encoding == "gzip":
        return gzip.decompress(raw)
    return raw


def kupibilet_price_amount(variant: dict[str, Any]) -> int | None:
    price = variant.get("price")
    if isinstance(price, dict):
        return price_value({"price": price.get("amount")})
    return price_value({"price": price})


def kupibilet_variant_currency(variant: dict[str, Any], fallback: str) -> str:
    price = variant.get("price")
    if isinstance(price, dict) and isinstance(price.get("currency"), str):
        return price["currency"].upper()
    return fallback


def kupibilet_flight_number(flight: dict[str, Any]) -> str:
    carrier = str(flight.get("marketing_carrier") or flight.get("operating_carrier") or "").upper()
    number = str(flight.get("transport_number") or flight.get("number") or "").strip()
    return f"{carrier}{number}" if carrier or number else ""


def kupibilet_flight_carriers(flight: dict[str, Any]) -> set[str]:
    carriers: set[str] = set()
    for key in ("marketing_carrier", "operating_carrier"):
        value = flight.get(key)
        if isinstance(value, str) and value.strip():
            code = value.strip().upper()
            if CARRIER_RE.match(code):
                carriers.add(code)
    flight_number = kupibilet_flight_number(flight)
    carrier = carrier_from_flight_number(flight_number)
    if carrier:
        carriers.add(carrier)
    return carriers


def kupibilet_variant_flight_ids(variant: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for segment in variant.get("segments", []):
        if isinstance(segment, dict) and isinstance(segment.get("flights"), list):
            ids.extend(str(item) for item in segment["flights"] if item)
    return ids


def normalize_kupibilet_flight(raw: dict[str, Any]) -> dict[str, Any]:
    flight_number = kupibilet_flight_number(raw)
    return {
        "flight_number": flight_number,
        "marketing_carrier": str(raw.get("marketing_carrier") or "").upper(),
        "operating_carrier": str(raw.get("operating_carrier") or "").upper(),
        "origin": str(raw.get("departure") or "").upper(),
        "destination": str(raw.get("arrival") or "").upper(),
        "departure_at": str(raw.get("departure_datetime") or ""),
        "arrival_at": str(raw.get("arrival_datetime") or ""),
        "aircraft": raw.get("equipment"),
        "duration": raw.get("duration"),
        "transport_kind": raw.get("transport_kind"),
        "is_charter": raw.get("is_charter"),
    }


def kupibilet_offer_key(flights: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(
        f"{flight.get('flight_number')}:{flight.get('departure_at')}:{flight.get('arrival_at')}"
        for flight in flights
    )


def parse_kupibilet_frontend_search(
    raw: dict[str, Any],
    *,
    origin: str,
    destination: str,
    depart_date: str,
    currency: str,
    only_carriers: list[str] | None = None,
    direct_only: bool = False,
    limit: int = 20,
) -> dict[str, Any]:
    variants = raw.get("variants") if isinstance(raw, dict) else None
    flights_by_id = raw.get("flights") if isinstance(raw, dict) else None
    if not isinstance(variants, list) or not isinstance(flights_by_id, dict):
        raise CliError("Kupibilet response does not contain variants/flights maps", error_type="upstream_error")

    carrier_filter = {code.strip().upper() for code in (only_carriers or []) if code.strip()}
    deduped: dict[tuple[str, ...], dict[str, Any]] = {}
    skipped = defaultdict(int)

    for index, variant in enumerate(variants):
        if not isinstance(variant, dict):
            skipped["bad_variant"] += 1
            continue
        flight_ids = kupibilet_variant_flight_ids(variant)
        if not flight_ids:
            skipped["no_flights"] += 1
            continue
        raw_flights = []
        for flight_id in flight_ids:
            raw_flight = flights_by_id.get(flight_id)
            if isinstance(raw_flight, dict):
                raw_flights.append(raw_flight)
        if len(raw_flights) != len(flight_ids):
            skipped["missing_flight_details"] += 1
            continue
        if any(flight.get("transport_kind") != "airplane" for flight in raw_flights):
            skipped["non_airplane"] += 1
            continue
        if direct_only and len(raw_flights) != 1:
            skipped["not_direct"] += 1
            continue
        if carrier_filter and not all(kupibilet_flight_carriers(flight) & carrier_filter for flight in raw_flights):
            skipped["carrier"] += 1
            continue

        normalized_flights = [normalize_kupibilet_flight(flight) for flight in raw_flights]
        key = kupibilet_offer_key(normalized_flights)
        if not key:
            skipped["empty_key"] += 1
            continue
        amount = kupibilet_price_amount(variant)
        offer = {
            "id": str(variant.get("id") or f"kupibilet:{index}"),
            "price": amount,
            "currency": kupibilet_variant_currency(variant, currency),
            "number_of_changes": max(0, len(normalized_flights) - 1),
            "duration": sum(int(flight.get("duration") or 0) for flight in raw_flights) or None,
            "departure_at": normalized_flights[0]["departure_at"],
            "arrival_at": normalized_flights[-1]["arrival_at"],
            "origin": normalized_flights[0]["origin"],
            "destination": normalized_flights[-1]["destination"],
            "flight_numbers": [flight["flight_number"] for flight in normalized_flights],
            "marketing_carriers": sorted({flight["marketing_carrier"] for flight in normalized_flights if flight["marketing_carrier"]}),
            "operating_carriers": sorted({flight["operating_carrier"] for flight in normalized_flights if flight["operating_carrier"]}),
            "flights": normalized_flights,
        }
        previous = deduped.get(key)
        previous_price = previous.get("price") if previous else None
        if previous is None or (amount is not None and (previous_price is None or amount < previous_price)):
            deduped[key] = offer

    offers = sorted(
        deduped.values(),
        key=lambda item: (
            item.get("price") if item.get("price") is not None else 10**12,
            item.get("departure_at") or "",
            "-".join(item.get("flight_numbers") or []),
        ),
    )[: max(0, limit)]
    return {
        "origin": origin,
        "destination": destination,
        "depart_date": depart_date,
        "currency": currency,
        "source": "Kupibilet frontend_search (live aggregate)",
        "source_url": KUPIBILET_FRONTEND_SEARCH_URL,
        "note": "Live aggregate source, not official aeroflot.ru; recheck final fare and seat availability before ticketing.",
        "filters": {"only_carriers": sorted(carrier_filter), "direct_only": direct_only, "dedupe": "flight_numbers+times"},
        "raw_variant_count": len(variants),
        "skipped": dict(skipped),
        "offer_count": len(offers),
        "unique_flight_count": len(deduped),
        "offers": offers,
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
        live = data.get("live")
        if isinstance(live, dict) and isinstance(live.get("data"), dict):
            current = live["data"]
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


def carrier_from_flight_number(flight_number: str) -> str | None:
    compact = re.sub(r"[^A-Z0-9]", "", str(flight_number or "").upper())
    if len(compact) >= 3 and compact[:2].isalnum() and compact[2].isdigit() and any(ch.isalpha() for ch in compact[:2]):
        return compact[:2]
    prefix = "".join(ch for ch in compact if ch.isalpha())
    return prefix if CARRIER_RE.match(prefix) else None


def carrier_from_leg(leg: dict[str, Any]) -> str | None:
    for key in ("operating_carrier", "carrier", "airline", "main_airline"):
        value = leg.get(key)
        if isinstance(value, str) and value.strip():
            code = value.strip().upper()
            if CARRIER_RE.match(code):
                return code
    return carrier_from_flight_number(str(leg.get("flight_number") or ""))


def normalize_transfer(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    transfer: dict[str, Any] = {}
    for key in ("at", "to", "country_code"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            transfer[key] = value.strip().upper()
    duration = raw.get("duration_seconds")
    if duration is not None:
        try:
            transfer["duration_seconds"] = max(0, int(float(duration)))
        except (TypeError, ValueError):
            pass
    for key in ("night_transfer", "visa_required"):
        if key in raw:
            transfer[key] = bool(raw.get(key))
    return transfer or None


def normalize_transfers(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    transfers = []
    for item in raw:
        transfer = normalize_transfer(item)
        if transfer is not None:
            transfers.append(transfer)
    return transfers


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


def collect_segment_results(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        results: list[dict[str, Any]] = []
        for item in payload:
            results.extend(collect_segment_results(item))
        return results
    if not isinstance(payload, dict):
        return []
    if payload.get("ok") is True and isinstance(payload.get("data"), dict):
        return collect_segment_results(payload["data"])
    if isinstance(payload.get("segment_result"), dict):
        return [payload["segment_result"]]
    if isinstance(payload.get("segment_results"), list):
        return collect_segment_results(payload["segment_results"])
    if isinstance(payload.get("results"), list):
        return collect_segment_results(payload["results"])
    if isinstance(payload.get("offers"), list) and (isinstance(payload.get("query"), dict) or payload.get("leg")):
        return [payload]
    return []


def read_json_file(path: str) -> Any:
    try:
        return json.loads(read_input_text(path))
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid JSON input {path}: {exc}", error_type="validation_error") from exc


def offer_price(*offers: dict[str, Any]) -> int | None:
    total = 0
    seen = False
    for offer in offers:
        price = price_value(offer)
        if price is not None:
            total += price
            seen = True
    return total if seen else None


def offer_currency(*offers: dict[str, Any]) -> str | None:
    for offer in offers:
        currency = currency_value(offer)
        if currency:
            return currency
    return None


def offer_summary(offer: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": offer.get("id"),
        "origin": offer.get("origin"),
        "destination": offer.get("destination"),
        "departure_airport": offer.get("departure_airport"),
        "arrival_airport": offer.get("arrival_airport"),
        "departure_at": offer.get("departure_at"),
        "arrival_at": offer.get("arrival_at"),
        "price": offer.get("price"),
        "currency": offer.get("currency"),
        "leg": offer.get("leg"),
    }


def rejected_pair(
    first: dict[str, Any],
    second: dict[str, Any],
    direction: str,
    *,
    ticketing: str,
    min_same_airport: int,
    min_cross_airport: int,
    profile: str,
) -> dict[str, Any] | None:
    first_arrival = str(first.get("arrival_airport") or first.get("destination") or "").upper()
    second_departure = str(second.get("departure_airport") or second.get("origin") or "").upper()
    if not first_arrival or not second_departure or first_arrival == second_departure:
        return None

    actual = minutes_between(str(first.get("arrival_at") or ""), str(second.get("departure_at") or ""))
    rule = connection_rule(first_arrival, second_departure, ticketing, min_same_airport, min_cross_airport, actual)
    arrival_group = airport_group(first_arrival)
    departure_group = airport_group(second_departure)
    same_group = bool(arrival_group and departure_group and arrival_group["key"] == departure_group["key"])
    airport_pair_status = "ground_transfer_required" if same_group else "airport_mismatch"
    first_segments = [seg for seg in (first.get("segments") or []) if isinstance(seg, dict)]
    second_segments = [seg for seg in (second.get("segments") or []) if isinstance(seg, dict)]
    prev_segment = first_segments[-1] if first_segments else {
        "origin": first.get("origin"),
        "destination": first_arrival,
        "arrival_at": first.get("arrival_at"),
    }
    next_segment = second_segments[0] if second_segments else {
        "origin": second_departure,
        "destination": second.get("destination"),
        "departure_at": second.get("departure_at"),
    }
    risk = connection_risk_points(rule, prev_segment, next_segment, profile)
    return {
        "direction": direction,
        "reason": rule["status"],
        "airport_pair_status": airport_pair_status,
        "severity": rule["severity"],
        "arrival_airport": first_arrival,
        "departure_airport": second_departure,
        "same_multi_airport_system": rule["same_multi_airport_system"],
        "airport_group": arrival_group["label"] if same_group and arrival_group else None,
        "actual_min": actual,
        "required_min": rule["required_min"],
        "risk": risk,
        "notes": rule["notes"],
        "first_offer": offer_summary(first),
        "second_offer": offer_summary(second),
        "price": offer_price(first, second),
        "currency": offer_currency(first, second),
    }


def pair_offers(first: dict[str, Any], second: dict[str, Any], direction: str) -> dict[str, Any] | None:
    if first.get("arrival_airport") != second.get("departure_airport"):
        return None
    segments = list(first.get("segments") or []) + list(second.get("segments") or [])
    if len(segments) < 2:
        return None
    return {
        "direction": direction,
        "segments": segments,
        "offers": [
            offer_summary(first),
            offer_summary(second),
        ],
        "price": offer_price(first, second),
        "currency": offer_currency(first, second),
    }


def assemble_direction(
    segment_results: list[dict[str, Any]],
    first_leg: str,
    second_leg: str,
    direction: str,
    limit_per_pair: int,
    *,
    ticketing: str,
    min_same_airport: int,
    min_cross_airport: int,
    profile: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    first_results = [result for result in segment_results if result.get("direction") == direction and result.get("leg") == first_leg]
    second_results = [result for result in segment_results if result.get("direction") == direction and result.get("leg") == second_leg]
    pairs = []
    rejected = []
    for first_result in first_results:
        for first_offer in list(first_result.get("offers") or [])[:limit_per_pair]:
            if not isinstance(first_offer, dict):
                continue
            for second_result in second_results:
                for second_offer in list(second_result.get("offers") or [])[:limit_per_pair]:
                    if not isinstance(second_offer, dict):
                        continue
                    pair = pair_offers(first_offer, second_offer, direction)
                    if pair is not None:
                        pairs.append(pair)
                    else:
                        rejection = rejected_pair(
                            first_offer,
                            second_offer,
                            direction,
                            ticketing=ticketing,
                            min_same_airport=min_same_airport,
                            min_cross_airport=min_cross_airport,
                            profile=profile,
                        )
                        if rejection is not None:
                            rejected.append(rejection)
    pairs.sort(key=lambda pair: (pair["price"] if pair["price"] is not None else 10**12, elapsed_minutes(pair["segments"]) or 10**9))
    severity_order = {"error": 0, "warn": 1, "ok": 2}
    rejected.sort(
        key=lambda item: (
            severity_order.get(str(item.get("severity")), 9),
            -int((item.get("risk") or {}).get("score") or 0),
            item["price"] if item.get("price") is not None else 10**12,
        )
    )
    return pairs, rejected


def candidate_from_pairs(outbound: dict[str, Any] | None, inbound: dict[str, Any] | None, index: int) -> dict[str, Any]:
    journeys = []
    offers = []
    price_parts = []
    if outbound:
        journeys.append({"direction": "outbound", "segments": outbound["segments"]})
        offers.extend(outbound["offers"])
        price_parts.append(outbound)
    if inbound:
        journeys.append({"direction": "return", "segments": inbound["segments"]})
        offers.extend(inbound["offers"])
        price_parts.append(inbound)
    first = journeys[0]["segments"][0]
    last = journeys[-1]["segments"][-1]
    return {
        "id": f"assembled-{index}:{first['origin']}-{last['destination']}",
        "price": offer_price(*price_parts),
        "currency": offer_currency(*price_parts),
        "journeys": journeys,
        "source_offers": offers,
    }


def build_route_plan(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    depart = parse_iso_date(args.depart_date, "depart-date")
    ret = parse_iso_date(args.return_date, "return-date") if args.return_date else None
    currency = args.currency.upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise CliError(f"currency must be one of {', '.join(sorted(SUPPORTED_CURRENCIES))}", error_type="validation_error")
    profile = normalize_profile(getattr(args, "profile", "balanced"))

    origin = store.resolve_location(args.origin)
    destination = store.resolve_location(args.destination)

    origin_airports = explicit_or_resolved_airports(
        store, origin, args.origin_airport, role="origin", max_airports=args.max_airports_per_city
    )
    destination_airports = explicit_or_resolved_airports(
        store, destination, args.destination_airport, role="destination", max_airports=args.max_airports_per_city
    )
    hubs = [normalize_iata(hub, "hub") for hub in (args.hub or DEFAULT_HUBS)]

    warnings: list[str] = [CACHE_NOTE]
    if destination.code == "LON":
        warnings.append("LON often returns empty in Travelpayouts; use specific London airports.")
    if origin.code == "LON":
        warnings.append("LON often returns empty in Travelpayouts; use specific London airports.")
    if any(hub in {"IST", "SAW"} for hub in hubs) and not {"IST", "SAW"}.issubset(set(hubs)):
        warnings.append("For Istanbul, query both IST and SAW when comparing hub options.")
    if "AYT" in hubs:
        warnings.append(SINGLE_AIRPORT_NOTES["AYT"])

    segments: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    def add_segment(direction: str, leg: str, dep_date: date, origin_code: str, dest_code: str) -> None:
        if origin_code == dest_code:
            return
        key = (direction, leg, origin_code, dest_code)
        if key in seen:
            return
        seen.add(key)
        segments.append(
            {
                "direction": direction,
                "leg": leg,
                "origin": origin_code,
                "destination": dest_code,
                "date": dep_date.isoformat(),
                "airport_pair_risk": airport_pair_risk(origin_code, dest_code),
                "request": compact_request_payload(
                    build_request_payload(origin_code, dest_code, dep_date, None, currency, args.direct_only)
                ),
                "command": segment_request_command(
                    origin_code,
                    dest_code,
                    dep_date,
                    currency=currency,
                    direct_only=args.direct_only,
                ),
            }
        )

    for origin_code in origin_airports:
        for hub in hubs:
            add_segment("outbound", "origin_to_hub", depart, origin_code, hub)
    for hub in hubs:
        for dest_code in destination_airports:
            add_segment("outbound", "hub_to_destination", depart, hub, dest_code)

    if ret:
        for dest_code in destination_airports:
            for hub in hubs:
                add_segment("return", "destination_to_hub", ret, dest_code, hub)
        for hub in hubs:
            for origin_code in origin_airports:
                add_segment("return", "hub_to_origin", ret, hub, origin_code)

    itinerary_families = []
    for hub in hubs:
        hub_info = explain_airport(store, hub)
        outbound_checks = [
            connection_rule(hub, hub, args.ticketing, args.min_same_airport_min, args.min_cross_airport_min)
        ]
        return_checks = outbound_checks if ret else []
        itinerary_families.append(
            {
                "hub": hub,
                "hub_info": hub_info,
                "outbound_airport_compatibility": outbound_checks,
                "return_airport_compatibility": return_checks,
            }
        )

    manual_ops = {
        "airport_expansions": 2,
        "hub_candidates": len(hubs),
        "segment_queries_to_prepare": len(segments),
        "airport_pair_risk_checks": len(segments),
        "route_family_compatibility_checks": len(hubs) * (2 if ret else 1),
        "manual_aviasales_links": len(origin_airports) * len(destination_airports),
    }
    cli_ops = {
        "route_plan_commands": 1,
        "generated_segment_commands": len(segments),
        "route_validate_command_after_results": 1,
        "airport_rules_embedded": True,
    }

    direct_links = [
        {
            "origin": origin_code,
            "destination": dest_code,
            "url": aviasales_url(origin_code, dest_code, depart, ret),
        }
        for origin_code in origin_airports
        for dest_code in destination_airports
    ]

    return {
        "origin": origin.to_dict(),
        "destination": destination.to_dict(),
        "origin_airports": origin_airports,
        "destination_airports": destination_airports,
        "hubs": hubs,
        "dates": {"departure": depart.isoformat(), "return": ret.isoformat() if ret else None},
        "ticketing": args.ticketing,
        "profile": {
            "name": profile,
            "description": RISK_PROFILES[profile]["description"],
            "rank_order": RISK_PROFILES[profile]["rank_order"],
        },
        "segments": segments,
        "itinerary_families": itinerary_families,
        "manual_links": {"aviasales": direct_links},
        "warnings": warnings,
        "metrics": {
            "without_cli": manual_ops,
            "with_cli": cli_ops,
            "segment_request_count": len(segments),
            "unique_airports_considered": sorted(set(origin_airports + destination_airports + hubs)),
            "profile_rank_order": RISK_PROFILES[profile]["rank_order"],
            "notes": [
                "Metrics are deterministic planning operations, not live API latency.",
                "The CLI does not call Travelpayouts during route plan.",
            ],
        },
    }


def explicit_or_resolved_airports(
    store: Store,
    location: Location,
    explicit: list[str] | None,
    *,
    role: str,
    max_airports: int,
) -> list[str]:
    if explicit:
        return [normalize_iata(code, f"{role}-airport") for code in explicit]
    airports = list(location.airports or [])
    if location.code in SPECIAL_CITY_AIRPORTS and role in {"origin", "destination"}:
        airports = SPECIAL_CITY_AIRPORTS[location.code]
    if not airports and location.kind in {"airport", "iata"}:
        airports = [location.code]
    if not airports:
        raise CliError(f"no flightable airports found for {location.input!r}", error_type="not_found")
    return airports[:max(1, max_airports)]


def airport_pair_risk(origin: str, destination: str) -> dict[str, Any]:
    origin_group = airport_group(origin)
    dest_group = airport_group(destination)
    same_group = bool(origin_group and dest_group and origin_group["key"] == dest_group["key"])
    notes: list[str] = []
    if origin != destination and same_group:
        notes.append(f"{origin} and {destination} are separate airports in {origin_group['label']}.")
    if destination in SINGLE_AIRPORT_NOTES:
        notes.append(SINGLE_AIRPORT_NOTES[destination])
    return {
        "origin_group": origin_group["label"] if origin_group else None,
        "destination_group": dest_group["label"] if dest_group else None,
        "same_multi_airport_system": same_group,
        "notes": notes,
    }


def connection_rule(
    arrival_airport: str,
    departure_airport: str,
    ticketing: str,
    min_same_airport: int,
    min_cross_airport: int,
    actual_minutes: int | None = None,
) -> dict[str, Any]:
    arrival = arrival_airport.upper()
    departure = departure_airport.upper()
    same_airport = arrival == departure
    arrival_group = airport_group(arrival)
    departure_group = airport_group(departure)
    same_group = bool(arrival_group and departure_group and arrival_group["key"] == departure_group["key"])

    if ticketing == "single":
        required = 60 if same_airport else min_cross_airport
    elif same_airport:
        required = min_same_airport
    elif same_group:
        required = min_cross_airport
    else:
        required = min_cross_airport

    severity = "ok"
    status = "compatible"
    notes: list[str] = []
    if not same_airport:
        if same_group:
            status = "ground_transfer_required"
            severity = "warn"
            notes.append(f"{arrival} to {departure} requires airport change inside {arrival_group['label']}.")
        else:
            status = "airport_mismatch"
            severity = "error"
            notes.append(f"Arrival airport {arrival} does not match next departure airport {departure}.")

    if actual_minutes is not None:
        if actual_minutes < 0:
            status = "invalid_time_order"
            severity = "error"
            notes.append("Next departure is before previous arrival.")
        elif actual_minutes < required:
            severity = "error"
            status = "too_short"
            notes.append(f"Connection is {actual_minutes} min, below required {required} min.")

    return {
        "arrival_airport": arrival,
        "departure_airport": departure,
        "same_airport": same_airport,
        "same_multi_airport_system": same_group,
        "ticketing": ticketing,
        "required_min": required,
        "actual_min": actual_minutes,
        "status": status,
        "severity": severity,
        "notes": notes,
    }


def connection_risk_points(
    rule: dict[str, Any],
    prev_segment: dict[str, Any],
    next_segment: dict[str, Any],
    profile: str,
) -> dict[str, Any]:
    config = RISK_PROFILES[profile]
    score = 0
    reasons: list[dict[str, Any]] = []
    actual = rule.get("actual_min")
    required = int(rule.get("required_min") or 0)

    def add(code: str, points: int, message: str) -> None:
        nonlocal score
        if points <= 0:
            return
        score += points
        reasons.append({"code": code, "points": points, "message": message})

    if rule["status"] == "invalid_time_order":
        add("invalid_time_order", 100, "Next departure is before previous arrival.")
    elif rule["status"] == "airport_mismatch" and not rule["same_multi_airport_system"]:
        add("airport_mismatch", 92, "Connection changes to an unrelated airport.")
    elif actual is None:
        add("missing_connection_time", config["missing_time_penalty"], "Connection time is unknown.")
    elif actual < required:
        short_by = required - actual
        add(
            "too_short_connection",
            min(100, int(config["too_short_penalty"]) + min(18, short_by // 15)),
            f"Connection is {actual} min, below required {required} min.",
        )
    elif not rule["same_airport"]:
        base = int(config["cross_airport_base"])
        if rule["same_multi_airport_system"]:
            add("cross_airport_transfer", base, "Ground transfer between airports is required.")
        else:
            add("airport_change", max(base, 55), "Arrival airport differs from next departure airport.")

    if actual is not None and actual >= required and rule["same_airport"]:
        ideal_min = int(config["ideal_same_min"])
        ideal_max = int(config["ideal_same_max"])
        if actual < ideal_min:
            add("below_ideal_buffer", min(18, max(3, (ideal_min - actual) // 10)), "Connection is valid but below ideal buffer.")
        elif actual > ideal_max:
            add("long_layover", min(18, max(2, (actual - ideal_max) // 60 * 3)), "Connection is longer than the profile's ideal range.")

    if is_night_time(str(prev_segment.get("arrival_at") or "")) or is_night_time(str(next_segment.get("departure_at") or "")):
        add("night_connection", int(config["night_penalty"]), "Connection touches late-night or early-morning hours.")

    return {
        "score": clamp_score(score),
        "grade": risk_grade(clamp_score(score)),
        "reasons": reasons,
    }


def segment_risk_points(segment: dict[str, Any], profile: str) -> dict[str, Any]:
    config = RISK_PROFILES[profile]
    score = 0
    reasons: list[dict[str, Any]] = []

    def add(code: str, points: int, message: str) -> None:
        nonlocal score
        if points <= 0:
            return
        score += points
        reasons.append({"code": code, "points": points, "message": message})

    origin = str(segment.get("origin") or "").upper()
    destination = str(segment.get("destination") or "").upper()
    for airport in (origin, destination):
        if airport in LEISURE_HUBS:
            add("leisure_hub", int(config["leisure_hub_penalty"]), f"{airport} is a leisure/charter-heavy hub.")
        airport_penalty = dict(config["unpreferred_airport_penalty"]).get(airport, 0)
        add("profile_airport_penalty", int(airport_penalty), f"{airport} is less preferred for profile {profile}.")

    lowcost = sorted(segment_carriers(segment) & LOW_COST_CARRIERS)
    if lowcost:
        add("lowcost_carrier", int(config["lowcost_penalty"]), f"Low-cost/leisure carrier signal: {', '.join(lowcost)}.")

    transfer_after = segment.get("transfer_after")
    if isinstance(transfer_after, dict):
        transfer_at = str(transfer_after.get("at") or destination or "").upper()
        if transfer_after.get("visa_required"):
            add(
                "visa_required_transfer",
                int(config["visa_transfer_penalty"]),
                f"Internal transfer at {transfer_at} reports visa_required=true.",
            )
        if transfer_after.get("night_transfer"):
            add(
                "api_night_transfer",
                int(config["api_night_transfer_penalty"]),
                f"Internal transfer at {transfer_at} is marked as a night transfer by provider.",
            )
        duration_seconds = transfer_after.get("duration_seconds")
        if isinstance(duration_seconds, int) and duration_seconds >= 8 * 3600:
            hours = duration_seconds // 3600
            add(
                "long_internal_transfer",
                int(config["long_internal_transfer_penalty"]),
                f"Internal transfer at {transfer_at} is about {hours}h.",
            )

    return {
        "score": clamp_score(score),
        "grade": risk_grade(clamp_score(score)),
        "reasons": reasons,
    }


def score_itinerary(validation: dict[str, Any], source: dict[str, Any], profile: str) -> dict[str, Any]:
    segments = validation["segments"]
    connection_scores = []
    segment_scores = []
    components: list[dict[str, Any]] = []
    total = 0

    for connection in validation["connections"]:
        prev_index, next_index = connection["between_segments"]
        risk = connection_risk_points(connection, segments[prev_index], segments[next_index], profile)
        connection_scores.append({**connection, "risk": risk})
        total += risk["score"]
        for reason in risk["reasons"]:
            components.append({"scope": "connection", "between_segments": [prev_index, next_index], **reason})

    for segment in segments:
        risk = segment_risk_points(segment, profile)
        segment_scores.append({"index": segment["index"], "origin": segment["origin"], "destination": segment["destination"], "risk": risk})
        total += risk["score"]
        for reason in risk["reasons"]:
            components.append({"scope": "segment", "segment": segment["index"], **reason})

    if validation["violations"]:
        total = max(total, 86)

    score = clamp_score(total)
    price = price_value(source)
    elapsed = validation_elapsed_minutes(validation)
    return {
        "profile": profile,
        "profile_description": RISK_PROFILES[profile]["description"],
        "score": score,
        "grade": risk_grade(score),
        "reject": is_reject_score(score),
        "price": price,
        "elapsed_min": elapsed,
        "connection_scores": connection_scores,
        "segment_scores": segment_scores,
        "components": components,
        "rank_key": rank_key(profile, score, price, elapsed),
    }


def normalize_input_segments(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    normalized_segments: list[dict[str, Any]] = []
    journeys_out: list[dict[str, Any]] = []

    def normalize_segment(seg: dict[str, Any], journey_index: int, direction: str | None) -> dict[str, Any]:
        index = len(normalized_segments)
        origin = normalize_iata(str(seg.get("origin") or ""), f"segments[{index}].origin")
        destination = normalize_iata(str(seg.get("destination") or ""), f"segments[{index}].destination")
        normalized = {
            "index": index,
            "journey_index": journey_index,
            "direction": direction,
            "origin": origin,
            "destination": destination,
            "departure_at": str(seg.get("departure_at") or ""),
            "arrival_at": str(seg.get("arrival_at") or ""),
            "flight_number": seg.get("flight_number"),
            "carrier": seg.get("carrier"),
            "airline": seg.get("airline"),
            "operating_carrier": seg.get("operating_carrier"),
            "main_airline": seg.get("main_airline"),
        }
        transfer_after = normalize_transfer(seg.get("transfer_after"))
        if transfer_after is not None:
            normalized["transfer_after"] = transfer_after
        transfers = normalize_transfers(seg.get("transfers"))
        if transfers:
            normalized["transfers"] = transfers
        normalized_segments.append(normalized)
        return normalized

    raw_journeys = data.get("journeys")
    if isinstance(raw_journeys, list) and raw_journeys:
        for journey_index, journey in enumerate(raw_journeys):
            if not isinstance(journey, dict):
                raise CliError(f"journeys[{journey_index}] must be an object", error_type="validation_error")
            raw_segments = journey.get("segments")
            if not isinstance(raw_segments, list) or not raw_segments:
                raise CliError(f"journeys[{journey_index}].segments must be a non-empty list", error_type="validation_error")
            direction = str(journey.get("direction") or journey.get("name") or f"journey-{journey_index + 1}")
            indexes = []
            for seg in raw_segments:
                if not isinstance(seg, dict):
                    raise CliError(f"journeys[{journey_index}].segments must contain objects", error_type="validation_error")
                indexes.append(normalize_segment(seg, journey_index, direction)["index"])
            journeys_out.append({"index": journey_index, "direction": direction, "segment_indexes": indexes})
    else:
        raw_segments = data.get("segments")
        if not isinstance(raw_segments, list) or len(raw_segments) < 2:
            raise CliError("input JSON must contain at least two segments", error_type="validation_error")
        indexes = []
        for seg in raw_segments:
            if not isinstance(seg, dict):
                raise CliError("segments must contain objects", error_type="validation_error")
            indexes.append(normalize_segment(seg, 0, "itinerary")["index"])
        journeys_out.append({"index": 0, "direction": "itinerary", "segment_indexes": indexes})

    return normalized_segments, journeys_out


def rank_key(profile: str, score: int, price: int | None, elapsed: int | None) -> list[int]:
    values = {
        "reject": 1 if is_reject_score(score) else 0,
        "risk": score,
        "price": price if price is not None else 10**12,
        "elapsed": elapsed if elapsed is not None else 10**9,
    }
    return [values[name] for name in RISK_PROFILES[profile]["rank_order"]]


def validate_itinerary(data: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    ticketing = str(data.get("ticketing") or args.ticketing or "separate")
    profile = normalize_profile(str(data.get("profile") or getattr(args, "profile", "balanced")))
    normalized_segments, journeys = normalize_input_segments(data)

    connections: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    segments_by_index = {segment["index"]: segment for segment in normalized_segments}
    for journey in journeys:
        journey_segments = [segments_by_index[index] for index in journey["segment_indexes"] if index in segments_by_index]
        for prev, nxt in zip(journey_segments, journey_segments[1:]):
            actual = minutes_between(prev["arrival_at"], nxt["departure_at"])
            rule = connection_rule(
                prev["destination"],
                nxt["origin"],
                ticketing,
                args.min_same_airport_min,
                args.min_cross_airport_min,
                actual,
            )
            rule["journey_index"] = journey["index"]
            rule["journey_direction"] = journey["direction"]
            rule["between_segments"] = [prev["index"], nxt["index"]]
            connections.append(rule)
            if rule["severity"] == "error":
                violations.append(rule)

    result = {
        "ok": not violations,
        "ticketing": ticketing,
        "profile": profile,
        "journeys": journeys,
        "segments": normalized_segments,
        "connections": connections,
        "violations": violations,
        "summary": {
            "segment_count": len(normalized_segments),
            "connection_count": len(connections),
            "violation_count": len(violations),
        },
    }
    result["risk"] = score_itinerary(result, data, profile)
    result["connections"] = result["risk"]["connection_scores"]
    return result


def command_doctor(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    cache_files = {}
    for name in ["cities_ru.json", "airports.json", "airlines.json", "planes.json"]:
        path = store.cache_dir / name
        cache_files[name] = {"exists": path.exists(), "path": str(path)}
    return {
        "version": __version__,
        "python": sys.executable,
        "offline_first": True,
        "live_api_default": False,
        "hermes_plugin_path": str(PLUGIN_PATH),
        "hermes_plugin_exists": PLUGIN_PATH.exists(),
        "cache_dir": str(store.cache_dir),
        "cache_dir_exists": store.cache_dir.exists(),
        "cache_files": cache_files,
        "cache_counts": store.cache_counts(),
        "auth": {
            "travelpayouts_token": auth_presence("TRAVELPAYOUTS_TOKEN"),
            "travelpayouts_marker": auth_presence("TRAVELPAYOUTS_MARKER"),
        },
        "safety": {
            "booking_or_purchase": False,
            "docker_touched": False,
            "live_calls_require_flag": "--live",
        },
        "risk_profiles": {
            name: {
                "description": config["description"],
                "rank_order": config["rank_order"],
                "ideal_same_min": config["ideal_same_min"],
                "ideal_same_max": config["ideal_same_max"],
            }
            for name, config in RISK_PROFILES.items()
        },
    }


def command_cities_search(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    return {
        "query": args.query,
        "cities": [city_to_output(store, city) for city in store.search_cities(args.query, args.limit)],
    }


def command_airports_explain(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    return {"airports": [explain_airport(store, code) for code in args.code]}


def command_request_search(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    del store
    origin = normalize_iata(args.origin, "origin")
    destination = normalize_iata(args.destination, "destination")
    depart = parse_iso_date(args.depart_date, "depart-date")
    ret = parse_iso_date(args.return_date, "return-date") if args.return_date else None
    currency = args.currency.upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise CliError(f"currency must be one of {', '.join(sorted(SUPPORTED_CURRENCIES))}", error_type="validation_error")

    payload = build_request_payload(origin, destination, depart, ret, currency, args.direct_only)
    result = {
        "dry_run": not args.live,
        "advisory_only": True,
        "cache_note": CACHE_NOTE,
        "request": payload,
        "manual_link": aviasales_url(origin, destination, depart, ret),
    }
    if not args.live:
        return result

    token = os.getenv("TRAVELPAYOUTS_TOKEN")
    if not token:
        raise CliError("TRAVELPAYOUTS_TOKEN is required for --live", error_type="missing_credentials")
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
            live_data = json.loads(raw.decode("utf-8"))
            status = response.status
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")[:1000]
        raise CliError(f"Travelpayouts HTTP {exc.code}: {body_text}", error_type="upstream_error") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise CliError(f"Travelpayouts request failed: {type(exc).__name__}", error_type="upstream_error") from exc

    result["live"] = {
        "status": status,
        "data": live_data,
    }
    return result



def fetch_kupibilet_search(
    origin: str,
    destination: str,
    depart_date: date,
    *,
    currency: str,
    only_carriers: list[str] | None = None,
    direct_only: bool = False,
    limit: int = 20,
    timeout: int = 60,
) -> dict[str, Any]:
    """Run one Kupibilet frontend_search request and normalize/dedupe offers."""
    payload = build_kupibilet_payload(origin, destination, depart_date.isoformat(), currency)
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        KUPIBILET_FRONTEND_SEARCH_URL,
        data=body,
        headers=KUPIBILET_HEADERS,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            decoded = decode_http_body(raw, response.headers.get("Content-Encoding"))
            data = json.loads(decoded.decode("utf-8"))
            status = response.status
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")[:1000]
        raise CliError(f"Kupibilet HTTP {exc.code}: {body_text}", error_type="upstream_error") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise CliError(f"Kupibilet request failed: {type(exc).__name__}: {exc}", error_type="upstream_error") from exc

    result = parse_kupibilet_frontend_search(
        data,
        origin=origin,
        destination=destination,
        depart_date=depart_date.isoformat(),
        currency=currency,
        only_carriers=only_carriers,
        direct_only=direct_only,
        limit=limit,
    )
    result["http_status"] = status
    result["request"] = {
        "method": "POST",
        "endpoint": KUPIBILET_FRONTEND_SEARCH_URL,
        "body": payload,
        "headers": {"Content-Type": "application/json", "Origin": "https://www.kupibilet.ru", "Referer": "https://www.kupibilet.ru/"},
    }
    return result


def command_kb_search(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    """Run a Kupibilet live aggregate search and normalize/dedupe offers."""
    del store
    origin = normalize_iata(args.origin, "origin")
    destination = normalize_iata(args.destination, "destination")
    depart = parse_iso_date(args.depart_date, "depart-date")
    currency = args.currency.upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise CliError(f"currency must be one of {', '.join(sorted(SUPPORTED_CURRENCIES))}", error_type="validation_error")
    only_carriers = [normalize_carrier_code(code, "only-carrier") for code in (args.only_carrier or [])]
    return fetch_kupibilet_search(
        origin,
        destination,
        depart,
        currency=currency,
        only_carriers=only_carriers,
        direct_only=args.direct_only,
        limit=args.limit,
        timeout=args.timeout,
    )


def command_u6_prices(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    """Fetch Ural Airlines (U6) price calendar and return structured data.

    Uses the public mobile_calendar endpoint (no auth required).
    Empty responses are NOT treated as errors — they indicate the calendar
    lacks coverage for this route.
    """
    del store
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
    url = U6_CALENDAR_URL + "?" + "&".join(f"{k}={v}" for k, v in url_parts)

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
    elif isinstance(raw_data, dict) and not raw_data.get("dates"):
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
                f"flights request search {origin} {destination} --depart-date {selected_date or 'YYYY-MM-DD'}",
                f"flights kb-search {origin} {destination} --depart-date {selected_date or 'YYYY-MM-DD'} --only-carrier U6",
            ],
            "note": "U6 price calendar returned no data for this route. Cross-check with aggregators.",
        }

    dates = raw_data.get("dates", [])
    final_date = raw_data.get("finalDate", "")

    priced: list[dict[str, Any]] = []
    for entry in dates:
        d = entry.get("date", "")
        p = entry.get("price")
        if p and p.get("price") is not None:
            priced.append({
                "date": d,
                "price": p["price"],
                "currency": p.get("code", "RUB"),
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
            f"flights request search {origin} {destination} --depart-date {selected_date or 'YYYY-MM-DD'}",
            f"flights kb-search {origin} {destination} --depart-date {selected_date or 'YYYY-MM-DD'} --only-carrier U6",
        ],
        "note": "Minimum one-way fares from Ural Airlines (U6) official calendar. For flight details use aggregators.",
    }


def command_route_validate(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    del store
    source = read_input_text(args.input)
    try:
        data = json.loads(source)
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid JSON input: {exc}", error_type="validation_error") from exc
    if not isinstance(data, dict):
        raise CliError("input JSON must be an object", error_type="validation_error")
    return validate_itinerary(data, args)


def extract_candidate_list(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        candidates = data
    elif isinstance(data, dict) and isinstance(data.get("itineraries"), list):
        candidates = data["itineraries"]
    elif isinstance(data, dict) and isinstance(data.get("candidates"), list):
        candidates = data["candidates"]
    else:
        raise CliError("input must be a list or an object with itineraries/candidates", error_type="validation_error")
    if not all(isinstance(candidate, dict) for candidate in candidates):
        raise CliError("all candidates must be objects", error_type="validation_error")
    return candidates


def carrier_policy_from_args(args: argparse.Namespace) -> dict[str, set[str]]:
    return {
        "only": normalize_carrier_codes(getattr(args, "only_carrier", None), "only-carrier"),
        "exclude": normalize_carrier_codes(getattr(args, "exclude_carrier", None), "exclude-carrier"),
        "prefer": normalize_carrier_codes(getattr(args, "prefer_carrier", None), "prefer-carrier"),
        "avoid": normalize_carrier_codes(getattr(args, "avoid_carrier", None), "avoid-carrier"),
    }


def carrier_policy_output(policy: dict[str, set[str]]) -> dict[str, list[str]]:
    return {key: sorted(value) for key, value in policy.items()}


def carrier_filter_result(segments: list[dict[str, Any]], policy: dict[str, set[str]]) -> dict[str, Any]:
    only = policy["only"]
    exclude = policy["exclude"]
    all_carriers = itinerary_carriers(segments)
    excluded = sorted(all_carriers & exclude)
    if excluded:
        return {
            "ok": False,
            "reason": "excluded_carrier",
            "carriers": sorted(all_carriers),
            "matched_carriers": excluded,
            "message": f"Candidate uses excluded carrier(s): {', '.join(excluded)}.",
        }
    if only:
        missing_segments = []
        for segment in segments:
            carriers = segment_carriers(segment)
            if not carriers or not carriers & only:
                missing_segments.append(
                    {
                        "index": segment.get("index"),
                        "origin": segment.get("origin"),
                        "destination": segment.get("destination"),
                        "carriers": sorted(carriers),
                    }
                )
        if missing_segments:
            return {
                "ok": False,
                "reason": "outside_only_carriers",
                "carriers": sorted(all_carriers),
                "matched_carriers": sorted(all_carriers & only),
                "missing_segments": missing_segments,
                "message": f"Not every segment is operated by selected carrier(s): {', '.join(sorted(only))}.",
            }
    return {
        "ok": True,
        "reason": None,
        "carriers": sorted(all_carriers),
        "matched_carriers": sorted(all_carriers & (only or all_carriers)),
    }


def apply_carrier_preferences(risk: dict[str, Any], segments: list[dict[str, Any]], policy: dict[str, set[str]]) -> dict[str, Any]:
    prefer = policy["prefer"]
    avoid = policy["avoid"]
    if not prefer and not avoid:
        return risk

    carriers = itinerary_carriers(segments)
    score = int(risk["score"])
    components = list(risk["components"])
    preference_components: list[dict[str, Any]] = []

    if prefer:
        matched = sorted(carriers & prefer)
        if matched:
            preference_components.append(
                {
                    "scope": "carrier",
                    "code": "preferred_carrier_match",
                    "points": 0,
                    "message": f"Uses preferred carrier(s): {', '.join(matched)}.",
                }
            )
        else:
            points = 14
            score += points
            preference_components.append(
                {
                    "scope": "carrier",
                    "code": "missing_preferred_carrier",
                    "points": points,
                    "message": f"Does not use preferred carrier(s): {', '.join(sorted(prefer))}.",
                }
            )

    avoided = sorted(carriers & avoid)
    if avoided:
        points = 24
        score += points
        preference_components.append(
            {
                "scope": "carrier",
                "code": "avoided_carrier",
                "points": points,
                "message": f"Uses avoided carrier(s): {', '.join(avoided)}.",
            }
        )

    score = clamp_score(score)
    adjusted = dict(risk)
    adjusted["score"] = score
    adjusted["grade"] = risk_grade(score)
    adjusted["reject"] = is_reject_score(score)
    adjusted["components"] = components + preference_components
    adjusted["carrier_preferences"] = {
        "carriers": sorted(carriers),
        "matched_preferred": sorted(carriers & prefer),
        "matched_avoided": sorted(carriers & avoid),
    }
    adjusted["rank_key"] = rank_key(str(risk["profile"]), score, risk.get("price"), risk.get("elapsed_min"))
    return adjusted


def rank_candidate_list(candidates: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    profile = normalize_profile(args.profile)
    policy = carrier_policy_from_args(args)
    ranked: list[dict[str, Any]] = []
    filtered: list[dict[str, Any]] = []
    include_filtered = max(0, int(getattr(args, "include_filtered", 20)))
    for index, candidate in enumerate(candidates):
        candidate_args = argparse.Namespace(
            ticketing=str(candidate.get("ticketing") or args.ticketing),
            min_same_airport_min=args.min_same_airport_min,
            min_cross_airport_min=args.min_cross_airport_min,
            profile=profile,
        )
        validation = validate_itinerary(candidate, candidate_args)
        carrier_filter = carrier_filter_result(validation["segments"], policy)
        candidate_id = candidate.get("id") or candidate.get("name") or f"candidate-{index + 1}"
        if not carrier_filter["ok"]:
            if len(filtered) < include_filtered:
                filtered.append(
                    {
                        "id": candidate_id,
                        "reason": carrier_filter["reason"],
                        "message": carrier_filter["message"],
                        "carriers": carrier_filter["carriers"],
                        "matched_carriers": carrier_filter.get("matched_carriers", []),
                        "missing_segments": carrier_filter.get("missing_segments", []),
                    }
                )
            continue
        risk = apply_carrier_preferences(validation["risk"], validation["segments"], policy)
        ranked.append(
            {
                "id": candidate_id,
                "ok": validation["ok"],
                "price": risk["price"],
                "currency": currency_value(candidate),
                "elapsed_min": risk["elapsed_min"],
                "carriers": carrier_filter["carriers"],
                "journeys": validation.get("journeys"),
                "risk": {
                    "profile": risk["profile"],
                    "score": risk["score"],
                    "grade": risk["grade"],
                    "reject": risk["reject"],
                    "rank_key": risk["rank_key"],
                    "top_reasons": risk["components"][: args.max_reasons],
                },
                "validation_summary": validation["summary"],
                "connections": validation["connections"],
            }
        )

    ranked.sort(key=lambda item: item["risk"]["rank_key"])
    for position, item in enumerate(ranked, 1):
        item["rank"] = position

    return {
        "profile": profile,
        "profile_description": RISK_PROFILES[profile]["description"],
        "rank_order": RISK_PROFILES[profile]["rank_order"],
        "count": len(ranked),
        "carrier_policy": {
            **carrier_policy_output(policy),
            "filtered_count": len(candidates) - len(ranked),
            "filtered": filtered,
        },
        "ranked": ranked,
    }


def command_route_rank(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    del store
    candidates = extract_candidate_list(read_json_file(args.input))
    return rank_candidate_list(candidates, args)


def normalize_day_offsets(values: list[int] | None, default: list[int], field: str) -> list[int]:
    raw_values = default if values is None else values
    offsets: list[int] = []
    for value in raw_values:
        try:
            offset = int(value)
        except (TypeError, ValueError) as exc:
            raise CliError(f"{field} must be an integer day offset, got {value!r}", error_type="validation_error") from exc
        if offset < 0 or offset > 7:
            raise CliError(f"{field} must be between 0 and 7 days, got {offset}", error_type="validation_error")
        if offset not in offsets:
            offsets.append(offset)
    return offsets


def build_kupibilet_route_segment_plan(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    depart = parse_iso_date(args.depart_date, "depart-date")
    ret = parse_iso_date(args.return_date, "return-date") if args.return_date else None
    currency = args.currency.upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise CliError(f"currency must be one of {', '.join(sorted(SUPPORTED_CURRENCIES))}", error_type="validation_error")
    profile = normalize_profile(getattr(args, "profile", "balanced"))

    origin = store.resolve_location(args.origin)
    destination = store.resolve_location(args.destination)
    origin_airports = explicit_or_resolved_airports(
        store, origin, args.origin_airport, role="origin", max_airports=args.max_airports_per_city
    )
    destination_airports = explicit_or_resolved_airports(
        store, destination, args.destination_airport, role="destination", max_airports=args.max_airports_per_city
    )
    hubs = [normalize_iata(hub, "hub") for hub in (args.hub or DEFAULT_HUBS)]
    outbound_second_offsets = normalize_day_offsets(
        getattr(args, "outbound_second_leg_day_offset", None),
        DEFAULT_KB_ROUTE_OUTBOUND_SECOND_LEG_DAY_OFFSETS,
        "outbound-second-leg-day-offset",
    )
    return_second_offsets = normalize_day_offsets(
        getattr(args, "return_second_leg_day_offset", None),
        DEFAULT_KB_ROUTE_RETURN_SECOND_LEG_DAY_OFFSETS,
        "return-second-leg-day-offset",
    )

    segments: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()

    def add_segment(direction: str, leg: str, dep_date: date, origin_code: str, dest_code: str) -> None:
        if origin_code == dest_code:
            return
        key = (direction, leg, origin_code, dest_code, dep_date.isoformat())
        if key in seen:
            return
        seen.add(key)
        segments.append(
            {
                "direction": direction,
                "leg": leg,
                "origin": origin_code,
                "destination": dest_code,
                "date": dep_date.isoformat(),
            }
        )

    for origin_code in origin_airports:
        for hub in hubs:
            add_segment("outbound", "origin_to_hub", depart, origin_code, hub)
    for offset in outbound_second_offsets:
        leg_date = depart + timedelta(days=offset)
        for hub in hubs:
            for dest_code in destination_airports:
                add_segment("outbound", "hub_to_destination", leg_date, hub, dest_code)

    if ret:
        for dest_code in destination_airports:
            for hub in hubs:
                add_segment("return", "destination_to_hub", ret, dest_code, hub)
        for offset in return_second_offsets:
            leg_date = ret + timedelta(days=offset)
            for hub in hubs:
                for origin_code in origin_airports:
                    add_segment("return", "hub_to_origin", leg_date, hub, origin_code)

    warnings = [
        "Kupibilet live segment assembly uses direct-only one-way searches; availability and price still require final booking-screen recheck.",
        "Assembled candidates are usually separate-ticket/self-transfer unless the booking site later confirms protected through-ticketing.",
    ]
    if any(hub in {"IST", "SAW"} for hub in hubs) and not {"IST", "SAW"}.issubset(set(hubs)):
        warnings.append("For Istanbul, include both --hub IST and --hub SAW when comparing airport systems.")

    return {
        "origin": origin.code,
        "destination": destination.code,
        "origin_airports": origin_airports,
        "destination_airports": destination_airports,
        "hubs": hubs,
        "dates": {"depart": depart.isoformat(), "return": ret.isoformat() if ret else None},
        "currency": currency,
        "profile": profile,
        "ticketing": args.ticketing,
        "second_leg_day_offsets": {
            "outbound": outbound_second_offsets,
            "return": return_second_offsets if ret else [],
        },
        "segments": segments,
        "warnings": warnings,
        "metrics": {"segment_search_count": len(segments)},
    }


def kupibilet_offer_to_segment_offer(
    offer: dict[str, Any],
    *,
    direction: str,
    leg: str,
    query_origin: str,
    query_destination: str,
    query_date: str,
    currency: str,
    index: int,
) -> dict[str, Any] | None:
    raw_flights = offer.get("flights")
    if not isinstance(raw_flights, list) or not raw_flights:
        return None
    segments = []
    for flight in raw_flights:
        if not isinstance(flight, dict):
            continue
        origin = str(flight.get("origin") or "").upper()
        destination = str(flight.get("destination") or "").upper()
        if not origin or not destination:
            continue
        flight_number = str(flight.get("flight_number") or "")
        operating = str(flight.get("operating_carrier") or "").upper()
        marketing = str(flight.get("marketing_carrier") or "").upper()
        carrier = operating or marketing or carrier_from_flight_number(flight_number)
        segments.append(
            {
                "origin": origin,
                "destination": destination,
                "departure_at": str(flight.get("departure_at") or ""),
                "arrival_at": str(flight.get("arrival_at") or ""),
                "carrier": carrier,
                "flight_number": flight_number or None,
                "marketing_carrier": marketing or None,
                "operating_carrier": operating or None,
                "aircraft_code": flight.get("aircraft"),
            }
        )
    if not segments:
        return None
    price = price_value({"price": offer.get("price")})
    currency_value_result = offer.get("currency") if isinstance(offer.get("currency"), str) else currency
    offer_id = f"kb:{direction}:{leg}:{query_origin}-{query_destination}:{query_date}:{offer.get('id') or index}"
    return {
        "id": offer_id,
        "direction": direction,
        "leg": leg,
        "query_origin": query_origin,
        "query_destination": query_destination,
        "query_date": query_date,
        "origin": segments[0]["origin"],
        "destination": segments[-1]["destination"],
        "departure_airport": segments[0]["origin"],
        "arrival_airport": segments[-1]["destination"],
        "departure_at": segments[0]["departure_at"],
        "arrival_at": segments[-1]["arrival_at"],
        "price": price,
        "currency": currency_value_result,
        "carrier": segments[0].get("carrier"),
        "main_airline": segments[0].get("carrier"),
        "changes": offer.get("number_of_changes"),
        "duration_min": offer.get("duration"),
        "source": "Kupibilet frontend_search direct-only",
        "segments": segments,
        "transfers": [],
        "internal_connection_count": max(0, len(segments) - 1),
    }


def kupibilet_result_to_segment_result(result: dict[str, Any], *, direction: str, leg: str) -> dict[str, Any]:
    query_origin = str(result.get("origin") or "").upper()
    query_destination = str(result.get("destination") or "").upper()
    query_date = str(result.get("depart_date") or "")
    currency = str(result.get("currency") or DEFAULT_CURRENCY).upper()
    offers = []
    parse_errors = 0
    for index, offer in enumerate(result.get("offers") or []):
        if not isinstance(offer, dict):
            parse_errors += 1
            continue
        normalized = kupibilet_offer_to_segment_offer(
            offer,
            direction=direction,
            leg=leg,
            query_origin=query_origin,
            query_destination=query_destination,
            query_date=query_date,
            currency=currency,
            index=index,
        )
        if normalized is None:
            parse_errors += 1
            continue
        offers.append(normalized)
    return {
        "direction": direction,
        "leg": leg,
        "query": {"origin": query_origin, "destination": query_destination, "date": query_date, "currency": currency},
        "source_key": "kupibilet_frontend_search",
        "source": result.get("source"),
        "source_url": result.get("source_url"),
        "raw_count": result.get("raw_variant_count"),
        "unique_flight_count": result.get("unique_flight_count"),
        "parse_errors": parse_errors,
        "offers": offers,
    }


def kupibilet_segment_search_summary(spec: dict[str, Any], result: dict[str, Any], segment_result: dict[str, Any]) -> dict[str, Any]:
    return {
        **spec,
        "status": "ok",
        "http_status": result.get("http_status"),
        "raw_variant_count": result.get("raw_variant_count"),
        "unique_flight_count": result.get("unique_flight_count"),
        "offer_count": len(segment_result.get("offers") or []),
        "skipped": result.get("skipped", {}),
    }


def empty_assembled_result(args: argparse.Namespace) -> dict[str, Any]:
    policy = carrier_policy_from_args(args)
    return {
        "profile": args.profile,
        "profile_description": RISK_PROFILES[args.profile]["description"],
        "rank_order": RISK_PROFILES[args.profile]["rank_order"],
        "count": 0,
        "carrier_policy": {**carrier_policy_output(policy), "filtered_count": 0, "filtered": []},
        "ranked": [],
        "assembly": {
            "segment_result_count": 0,
            "outbound_pair_count": 0,
            "return_pair_count": 0,
            "rejected_pair_count": 0,
            "rejected_pair_sample_count": 0,
            "candidate_count": 0,
            "limit_per_pair": args.limit_per_pair,
            "max_candidates": args.max_candidates,
        },
        "candidates": [],
        "rejected_pairs": [],
    }


def command_route_kb_assemble(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    plan = build_kupibilet_route_segment_plan(args, store)
    max_searches = max(1, int(args.max_segment_searches))
    if plan["metrics"]["segment_search_count"] > max_searches:
        raise CliError(
            f"planned {plan['metrics']['segment_search_count']} segment searches exceeds --max-segment-searches {max_searches}",
            error_type="validation_error",
            details={"planned": plan["metrics"]["segment_search_count"], "max_segment_searches": max_searches},
        )
    only_carriers = [normalize_carrier_code(code, "only-carrier") for code in (args.only_carrier or [])]
    segment_results: list[dict[str, Any]] = []
    searches: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for spec in plan["segments"]:
        try:
            result = fetch_kupibilet_search(
                spec["origin"],
                spec["destination"],
                parse_iso_date(spec["date"], "segment-date"),
                currency=plan["currency"],
                only_carriers=only_carriers,
                direct_only=True,
                limit=args.segment_limit,
                timeout=args.timeout,
            )
        except CliError as exc:
            failure = {**spec, "status": "error", "error": {"type": exc.error_type, "message": exc.message}}
            failures.append(failure)
            searches.append(failure)
            if args.fail_fast:
                raise
            continue
        segment_result = kupibilet_result_to_segment_result(result, direction=spec["direction"], leg=spec["leg"])
        searches.append(kupibilet_segment_search_summary(spec, result, segment_result))
        if segment_result["offers"]:
            segment_results.append(segment_result)

    assembled = assemble_segment_results(segment_results, args) if segment_results else empty_assembled_result(args)
    assembled["live_search"] = {
        "source": "Kupibilet frontend_search direct-only segment assembly",
        "note": "Live aggregate source; recheck price/seat availability and whether segments can be ticketed together before purchase.",
        "plan": {key: value for key, value in plan.items() if key != "segments"},
        "segment_searches": searches,
        "failure_count": len(failures),
        "failures": failures,
        "included_segment_result_count": min(len(segment_results), args.include_segment_results),
    }
    assembled["segment_results"] = segment_results[: args.include_segment_results]
    return assembled


def command_results_parse(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    del store
    payload = read_json_file(args.input)
    return parse_travelpayouts_results(args, payload)


def assemble_segment_results(segment_results: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    if not segment_results:
        raise CliError("no parsed segment results found; run `flights results parse` first", error_type="validation_error")

    outbound_pairs, outbound_rejected = assemble_direction(
        segment_results,
        "origin_to_hub",
        "hub_to_destination",
        "outbound",
        args.limit_per_pair,
        ticketing=args.ticketing,
        min_same_airport=args.min_same_airport_min,
        min_cross_airport=args.min_cross_airport_min,
        profile=args.profile,
    )
    return_pairs, return_rejected = assemble_direction(
        segment_results,
        "destination_to_hub",
        "hub_to_origin",
        "return",
        args.limit_per_pair,
        ticketing=args.ticketing,
        min_same_airport=args.min_same_airport_min,
        min_cross_airport=args.min_cross_airport_min,
        profile=args.profile,
    )
    rejected_pairs = outbound_rejected + return_rejected

    candidates: list[dict[str, Any]] = []
    if outbound_pairs and return_pairs:
        for outbound in outbound_pairs:
            for inbound in return_pairs:
                candidates.append(candidate_from_pairs(outbound, inbound, len(candidates) + 1))
                if len(candidates) >= args.max_candidates:
                    break
            if len(candidates) >= args.max_candidates:
                break
    else:
        for outbound in outbound_pairs:
            candidates.append(candidate_from_pairs(outbound, None, len(candidates) + 1))
            if len(candidates) >= args.max_candidates:
                break
        for inbound in return_pairs:
            candidates.append(candidate_from_pairs(None, inbound, len(candidates) + 1))
            if len(candidates) >= args.max_candidates:
                break

    rank_args = argparse.Namespace(
        profile=args.profile,
        ticketing=args.ticketing,
        min_same_airport_min=args.min_same_airport_min,
        min_cross_airport_min=args.min_cross_airport_min,
        max_reasons=args.max_reasons,
        only_carrier=getattr(args, "only_carrier", None),
        exclude_carrier=getattr(args, "exclude_carrier", None),
        prefer_carrier=getattr(args, "prefer_carrier", None),
        avoid_carrier=getattr(args, "avoid_carrier", None),
        include_filtered=getattr(args, "include_filtered", 20),
    )
    policy = carrier_policy_from_args(rank_args)
    ranked = rank_candidate_list(candidates, rank_args) if candidates else {
        "profile": args.profile,
        "profile_description": RISK_PROFILES[args.profile]["description"],
        "rank_order": RISK_PROFILES[args.profile]["rank_order"],
        "count": 0,
        "carrier_policy": {**carrier_policy_output(policy), "filtered_count": 0, "filtered": []},
        "ranked": [],
    }
    ranked["assembly"] = {
        "segment_result_count": len(segment_results),
        "outbound_pair_count": len(outbound_pairs),
        "return_pair_count": len(return_pairs),
        "rejected_pair_count": len(rejected_pairs),
        "rejected_pair_sample_count": min(len(rejected_pairs), args.include_rejected_pairs),
        "candidate_count": len(candidates),
        "limit_per_pair": args.limit_per_pair,
        "max_candidates": args.max_candidates,
    }
    ranked["candidates"] = candidates[: args.include_candidates]
    ranked["rejected_pairs"] = rejected_pairs[: args.include_rejected_pairs]
    return ranked


def command_route_assemble(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    del store
    segment_results: list[dict[str, Any]] = []
    for path in (args.input or ["-"]):
        segment_results.extend(collect_segment_results(read_json_file(path)))
    return assemble_segment_results(segment_results, args)


def command_metrics_workflow(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    plan_args = argparse.Namespace(
        origin=args.origin,
        destination=args.destination,
        depart_date=args.depart_date,
        return_date=args.return_date,
        hub=args.hub,
        origin_airport=args.origin_airport,
        destination_airport=args.destination_airport,
        currency=args.currency,
        direct_only=False,
        ticketing=args.ticketing,
        min_same_airport_min=args.min_same_airport_min,
        min_cross_airport_min=args.min_cross_airport_min,
        max_airports_per_city=args.max_airports_per_city,
        profile=getattr(args, "profile", "balanced"),
    )
    plan = build_route_plan(plan_args, store)
    return {
        "scenario": {
            "origin": args.origin,
            "destination": args.destination,
            "departure": args.depart_date,
            "return": args.return_date,
            "hubs": plan["hubs"],
        },
        "metrics": plan["metrics"],
    }


def read_input_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise CliError(f"could not read {path}: {exc}", error_type="io_error") from exc


def output_envelope(command: str, data: Any) -> dict[str, Any]:
    return {"ok": True, "command": command, "data": data}


def error_envelope(exc: CliError) -> dict[str, Any]:
    error = {"type": exc.error_type, "message": exc.message}
    if exc.details is not None:
        error["details"] = exc.details
    return {"ok": False, "error": error}


def emit_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def render_human(command: str, data: Any) -> str:
    if command == "kb-search":
        lines = [
            f"Kupibilet live search: {data['origin']} → {data['destination']}",
            f"Date: {data['depart_date']}",
            f"Results: {data['offer_count']} unique offers from {data['raw_variant_count']} raw variants",
            f"Source: {data['source']}",
            f"Note: {data.get('note', '')}",
            "",
        ]
        if not data.get("offers"):
            lines.append("(no matching offers found)")
        for i, offer in enumerate(data.get("offers", []), 1):
            price = offer.get("price")
            price_text = f"{price:,.0f} {offer.get('currency', data.get('currency', ''))}" if price is not None else "price n/a"
            changes = "direct" if offer.get("number_of_changes") == 0 else f"{offer.get('number_of_changes')} stop(s)"
            lines.append(f"  {i}. {price_text}  {changes}  {offer.get('duration') or '?'}min")
            leg_bits = []
            for flight in offer.get("flights", []):
                operating = flight.get("operating_carrier")
                marketing = flight.get("marketing_carrier")
                op_note = f" op:{operating}" if operating and marketing and operating != marketing else ""
                dep = str(flight.get("departure_at") or "")
                arr = str(flight.get("arrival_at") or "")
                leg_bits.append(
                    f"{flight.get('flight_number')} {flight.get('origin')}{dep[11:16]}→{flight.get('destination')}{arr[11:16]}{op_note}"
                )
            if leg_bits:
                lines.append("     " + " | ".join(leg_bits))
        return "\n".join(lines)
    if command == "u6-prices":
        if data.get("empty"):
            return (
                f"U6 price calendar: {data['origin']} → {data['destination']}\n"
                f"Status: no data ({data.get('empty_reason', 'unknown')})\n"
                f"Note: {data.get('note', '')}\n"
                "\n"
                "Cross-check:\n  "
                + "\n  ".join(data.get("cross_check_commands", []))
            )
        stats = data.get("stats", {})
        lines = [
            f"U6 price calendar: {data['origin']} → {data['destination']}",
            f"Range: {data.get('from_date', '')} — {data.get('final_date', '?')}  ({data['priced_dates']} priced / {data['unpriced_dates']} no-flight days)",
            f"Prices: min={stats.get('min') or '-'}  max={stats.get('max') or '-'}  avg={stats.get('avg') or '-'} RUB",
            "",
            "Date         Price",
            "-----------  ------",
        ]
        for entry in data.get("results", []):
            lines.append(f"{entry['date']}  {entry['price']:>6} {entry.get('currency', 'RUB')}")
        if not data.get("results"):
            lines.append("(no results matching filters)")
        if len(data.get("results", [])) < data.get("priced_dates", 0):
            lines.append(f"({data['priced_dates'] - len(data.get('results', []))} more matching filter, use --limit to see more)")
        lines.append("")
        lines.append("Cross-check:")
        for cmd in data.get("cross_check_commands", []):
            lines.append(f"  {cmd}")
        return "\n".join(lines)
    if command == "doctor":
        counts = data["cache_counts"]
        token = data["auth"]["travelpayouts_token"]
        return "\n".join(
            [
                f"flights {data['version']}",
                f"plugin: {'ok' if data['hermes_plugin_exists'] else 'missing'} {data['hermes_plugin_path']}",
                f"cache: cities={counts['cities']} airports={counts['airports']} airlines={counts['airlines']} planes={counts['planes']}",
                f"token: {'present' if token['available'] else 'missing'}",
                "live API: disabled unless --live",
            ]
        )
    if command == "cities search":
        lines = [f"cities for {data['query']!r}: {len(data['cities'])}"]
        for city in data["cities"]:
            airports = ",".join(city.get("airports") or [])
            lines.append(f"{city['code']}\t{city.get('name') or ''}\t{city.get('country_code') or ''}\t{airports}")
        return "\n".join(lines)
    if command == "airports explain":
        lines = []
        for airport in data["airports"]:
            lines.append(f"{airport['code']}: {airport.get('city_name') or airport.get('name') or 'unknown'}")
            for note in airport.get("notes") or []:
                lines.append(f"  - {note}")
        return "\n".join(lines)
    if command == "route plan":
        metrics = data["metrics"]
        lines = [
            f"route: {','.join(data['origin_airports'])} -> {','.join(data['destination_airports'])}",
            f"hubs: {', '.join(data['hubs'])}",
            f"segment requests: {metrics['segment_request_count']}",
            "first commands:",
        ]
        for segment in data["segments"][:8]:
            lines.append(f"  {segment['command']}")
        if len(data["segments"]) > 8:
            lines.append(f"  ... {len(data['segments']) - 8} more")
        if data["warnings"]:
            lines.append("warnings:")
            lines.extend(f"  - {warning}" for warning in data["warnings"])
        return "\n".join(lines)
    if command == "route validate":
        lines = [
            f"ok: {data['ok']}",
            f"risk: {data['risk']['score']} ({data['risk']['grade']}) profile={data['risk']['profile']}",
            f"segments: {data['summary']['segment_count']}, connections: {data['summary']['connection_count']}, violations: {data['summary']['violation_count']}",
        ]
        for violation in data["violations"]:
            lines.append(f"violation: {violation['arrival_airport']} -> {violation['departure_airport']}: {violation['status']}")
            for note in violation.get("notes") or []:
                lines.append(f"  - {note}")
        return "\n".join(lines)
    if command == "route rank":
        lines = [f"profile: {data['profile']} ({data['rank_order']})"]
        for item in data["ranked"]:
            lines.append(
                f"{item['rank']}. {item['id']} risk={item['risk']['score']}:{item['risk']['grade']} price={item['price']} elapsed={item['elapsed_min']}"
            )
            for reason in item["risk"]["top_reasons"][:3]:
                lines.append(f"  - +{reason['points']} {reason['code']}: {reason['message']}")
        return "\n".join(lines)
    if command == "route assemble":
        assembly = data["assembly"]
        lines = [
            f"profile: {data['profile']} ({data['rank_order']})",
            f"assembled candidates: {assembly['candidate_count']} from outbound_pairs={assembly['outbound_pair_count']} return_pairs={assembly['return_pair_count']}",
            f"rejected pairs: {assembly.get('rejected_pair_count', 0)}",
        ]
        for item in data["ranked"]:
            lines.append(
                f"{item['rank']}. {item['id']} risk={item['risk']['score']}:{item['risk']['grade']} price={item['price']} elapsed={item['elapsed_min']}"
            )
        return "\n".join(lines)
    if command == "route kb-assemble":
        assembly = data["assembly"]
        live = data.get("live_search", {})
        plan = live.get("plan", {})
        metrics = plan.get("metrics", {})
        lines = [
            f"Kupibilet direct-segment assembly: {plan.get('origin')} → {plan.get('destination')}",
            f"hubs: {', '.join(plan.get('hubs') or [])}",
            f"segment searches: {len(live.get('segment_searches') or [])}/{metrics.get('segment_search_count', 0)} failures={live.get('failure_count', 0)}",
            f"assembled candidates: {assembly['candidate_count']} from outbound_pairs={assembly['outbound_pair_count']} return_pairs={assembly['return_pair_count']}",
            f"rejected pairs: {assembly.get('rejected_pair_count', 0)}",
            f"note: {live.get('note', '')}",
            "",
        ]
        if not data.get("ranked"):
            lines.append("(no assembled candidates)")
        for item in data.get("ranked", [])[:10]:
            lines.append(
                f"{item['rank']}. {item['id']} risk={item['risk']['score']}:{item['risk']['grade']} price={item['price']} elapsed={item['elapsed_min']}"
            )
        return "\n".join(lines)
    if command == "results parse":
        result = data["segment_result"]
        query = result["query"]
        return "\n".join(
            [
                f"{result['direction']} {result['leg']}: {query.get('origin')}->{query.get('destination')} {query.get('date')}",
                f"offers: {len(result['offers'])}/{result['raw_count']} parse_errors={result['parse_errors']}",
            ]
        )
    if command == "request search":
        req = data["request"]
        lines = [
            f"{req['method']} {req['endpoint']}",
            f"query: {req['query_name']}",
            f"variables: {json.dumps(req['variables'], ensure_ascii=False, sort_keys=True)}",
            f"dry_run: {data['dry_run']}",
            f"manual link: {data['manual_link']}",
        ]
        return "\n".join(lines)
    if command == "metrics workflow":
        metrics = data["metrics"]
        return "\n".join(
            [
                f"without cli: {json.dumps(metrics['without_cli'], ensure_ascii=False, sort_keys=True)}",
                f"with cli: {json.dumps(metrics['with_cli'], ensure_ascii=False, sort_keys=True)}",
                f"segment requests: {metrics['segment_request_count']}",
            ]
        )
    return json.dumps(data, ensure_ascii=False, indent=2)


def add_common_route_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("origin", help="Origin city/airport, e.g. SVX or Ekaterinburg")
    parser.add_argument("destination", help="Destination city/airport, e.g. LON or London")
    parser.add_argument("--depart-date", required=True, help="Departure date YYYY-MM-DD")
    parser.add_argument("--return-date", help="Return date YYYY-MM-DD")
    parser.add_argument("--hub", action="append", help="Hub airport. Repeatable. Default: IST, SAW, AYT")
    parser.add_argument("--origin-airport", action="append", help="Force origin airport. Repeatable.")
    parser.add_argument("--destination-airport", action="append", help="Force destination airport. Repeatable.")
    parser.add_argument("--currency", default=DEFAULT_CURRENCY, help="Currency. Default RUB.")
    parser.add_argument("--ticketing", choices=["separate", "single"], default="separate")
    parser.add_argument("--profile", choices=sorted(RISK_PROFILES), default="balanced", help="Risk/ranking profile.")
    parser.add_argument("--min-same-airport-min", type=int, default=120)
    parser.add_argument("--min-cross-airport-min", type=int, default=300)
    parser.add_argument("--max-airports-per-city", type=int, default=6)


def add_carrier_selection_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--only-carrier", action="append", help="Hard filter: every segment must use one of these carrier codes. Repeatable.")
    parser.add_argument("--exclude-carrier", action="append", help="Hard filter: reject candidates using this carrier code. Repeatable.")
    parser.add_argument("--prefer-carrier", action="append", help="Soft preference: demote candidates that do not use this carrier. Repeatable.")
    parser.add_argument("--avoid-carrier", action="append", help="Soft preference: penalize candidates using this carrier. Repeatable.")
    parser.add_argument("--include-filtered", type=int, default=20, help="Include first N carrier-filtered candidates in JSON output.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flights",
        description="Offline-first flight routing helper for Hermes/Travelpayouts workflows.",
    )
    parser.add_argument("--json", action="store_true", help="Emit stable JSON envelope.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="Check local caches, plugin path, and auth presence.")
    doctor.set_defaults(func=command_doctor, command_name="doctor")

    cities = sub.add_parser("cities", help="City lookup commands.")
    cities_sub = cities.add_subparsers(dest="cities_command", required=True)
    cities_search = cities_sub.add_parser("search", help="Search city name or IATA code in local cache.")
    cities_search.add_argument("query")
    cities_search.add_argument("--limit", type=int, default=5)
    cities_search.set_defaults(func=command_cities_search, command_name="cities search")

    airports = sub.add_parser("airports", help="Airport rule lookup commands.")
    airports_sub = airports.add_subparsers(dest="airports_command", required=True)
    airports_explain = airports_sub.add_parser("explain", help="Explain airport and multi-airport risk rules.")
    airports_explain.add_argument("code", nargs="+")
    airports_explain.set_defaults(func=command_airports_explain, command_name="airports explain")

    u6_prices = sub.add_parser("u6-prices", help="Ural Airlines (U6) price calendar — daily min fares, price discovery, no auth required.")
    u6_prices.add_argument("origin", help="Origin IATA code (e.g. SVX).")
    u6_prices.add_argument("destination", help="Destination IATA code (e.g. IST).")
    u6_prices.add_argument("--from-date", required=True, help="Start date YYYY-MM-DD (calendar covers ~3 months from this date).")
    u6_prices.add_argument("--lang", default="ru", help="Language code (default: ru).")
    u6_prices.add_argument("--date", dest="selected_date", help="Filter to a specific date YYYY-MM-DD.")
    u6_prices.add_argument("--sort", choices=["price", "date"], default="price", help="Sort results by price or date (default: price).")
    u6_prices.add_argument("--limit", type=int, default=20, help="Max results to show (default: 20).")
    u6_prices.add_argument("--min-price", type=int, help="Minimum price filter (RUB).")
    u6_prices.add_argument("--max-price", type=int, help="Maximum price filter (RUB).")
    u6_prices.set_defaults(func=command_u6_prices, command_name="u6-prices")

    kb_search = sub.add_parser("kb-search", help="Kupibilet live aggregate search; use --only-carrier SU for Aeroflot-marketed flights.")
    kb_search.add_argument("origin", help="Origin IATA code (e.g. SVX).")
    kb_search.add_argument("destination", help="Destination city/airport IATA code (e.g. MOW or SVO).")
    kb_search.add_argument("--depart-date", required=True, help="Departure date YYYY-MM-DD.")
    kb_search.add_argument("--currency", default=DEFAULT_CURRENCY, help="Currency code (default: RUB).")
    kb_search.add_argument("--only-carrier", action="append", help="Require each flight leg to match this marketing or operating carrier. Repeatable.")
    kb_search.add_argument("--direct-only", action="store_true", help="Only direct one-leg offers.")
    kb_search.add_argument("--limit", type=int, default=20, help="Maximum normalized offers to show.")
    kb_search.add_argument("--timeout", type=int, default=60, help="HTTP timeout seconds.")
    kb_search.set_defaults(func=command_kb_search, command_name="kb-search")

    route = sub.add_parser("route", help="Route planning and validation commands.")
    route_sub = route.add_subparsers(dest="route_command", required=True)
    route_plan = route_sub.add_parser("plan", help="Build segment query plan through hubs without API calls.")
    add_common_route_flags(route_plan)
    route_plan.add_argument("--direct-only", action="store_true")
    route_plan.set_defaults(func=build_route_plan, command_name="route plan")

    route_validate = route_sub.add_parser("validate", help="Validate airport compatibility and connection windows from JSON.")
    route_validate.add_argument("--input", default="-", help="Input JSON file, or - for stdin.")
    route_validate.add_argument("--ticketing", choices=["separate", "single"], default="separate")
    route_validate.add_argument("--profile", choices=sorted(RISK_PROFILES), default="balanced")
    route_validate.add_argument("--min-same-airport-min", type=int, default=120)
    route_validate.add_argument("--min-cross-airport-min", type=int, default=300)
    route_validate.set_defaults(func=command_route_validate, command_name="route validate")

    route_rank = route_sub.add_parser("rank", help="Score and rank itinerary candidates from JSON.")
    route_rank.add_argument("--input", default="-", help="Input JSON list, or object with itineraries/candidates.")
    route_rank.add_argument("--ticketing", choices=["separate", "single"], default="separate")
    route_rank.add_argument("--profile", choices=sorted(RISK_PROFILES), default="balanced")
    route_rank.add_argument("--min-same-airport-min", type=int, default=120)
    route_rank.add_argument("--min-cross-airport-min", type=int, default=300)
    route_rank.add_argument("--max-reasons", type=int, default=5)
    add_carrier_selection_flags(route_rank)
    route_rank.set_defaults(func=command_route_rank, command_name="route rank")

    route_assemble = route_sub.add_parser("assemble", help="Assemble parsed segment results into ranked itinerary candidates.")
    route_assemble.add_argument("--input", action="append", help="Parsed result JSON. Repeatable; omit for stdin.")
    route_assemble.add_argument("--ticketing", choices=["separate", "single"], default="separate")
    route_assemble.add_argument("--profile", choices=sorted(RISK_PROFILES), default="balanced")
    route_assemble.add_argument("--min-same-airport-min", type=int, default=120)
    route_assemble.add_argument("--min-cross-airport-min", type=int, default=300)
    route_assemble.add_argument(
        "--limit-per-pair",
        type=int,
        default=DEFAULT_ROUTE_ASSEMBLE_LIMIT_PER_PAIR,
        help=(
            "Depth per segment-result list before pairing (default: 10). "
            "Keep >=10 for complex routes so frontier-relevant options (schedule, duration, "
            "connection safety, airport/carrier preference) are not truncated before ranking."
        ),
    )
    route_assemble.add_argument("--max-candidates", type=int, default=50)
    route_assemble.add_argument("--max-reasons", type=int, default=5)
    route_assemble.add_argument("--include-candidates", type=int, default=5, help="Include first N raw assembled candidates in JSON output.")
    route_assemble.add_argument("--include-rejected-pairs", type=int, default=20, help="Include first N rejected/airport-mismatch pairs.")
    add_carrier_selection_flags(route_assemble)
    route_assemble.set_defaults(func=command_route_assemble, command_name="route assemble")

    route_kb_assemble = route_sub.add_parser(
        "kb-assemble",
        help="Run Kupibilet direct-only segment searches through hubs and assemble ranked candidates.",
    )
    add_common_route_flags(route_kb_assemble)
    route_kb_assemble.add_argument("--segment-limit", type=int, default=30, help="Max direct offers kept per live segment search.")
    route_kb_assemble.add_argument("--timeout", type=int, default=60, help="HTTP timeout seconds per Kupibilet segment search.")
    route_kb_assemble.add_argument(
        "--outbound-second-leg-day-offset",
        action="append",
        type=int,
        help="Day offset(s) for hub→destination searches after depart date. Repeatable. Default: 0 and 1.",
    )
    route_kb_assemble.add_argument(
        "--return-second-leg-day-offset",
        action="append",
        type=int,
        help="Day offset(s) for hub→origin searches after return date. Repeatable. Default: 0, 1, and 2.",
    )
    route_kb_assemble.add_argument("--limit-per-pair", type=int, default=DEFAULT_ROUTE_ASSEMBLE_LIMIT_PER_PAIR)
    route_kb_assemble.add_argument("--max-candidates", type=int, default=50)
    route_kb_assemble.add_argument("--max-reasons", type=int, default=5)
    route_kb_assemble.add_argument("--include-candidates", type=int, default=5)
    route_kb_assemble.add_argument("--include-rejected-pairs", type=int, default=20)
    route_kb_assemble.add_argument("--include-segment-results", type=int, default=0, help="Include first N normalized segment-result blocks in JSON output.")
    route_kb_assemble.add_argument("--max-segment-searches", type=int, default=80, help="Safety cap for live segment requests.")
    route_kb_assemble.add_argument("--fail-fast", action="store_true", help="Abort on the first live segment-search error instead of keeping partial results.")
    add_carrier_selection_flags(route_kb_assemble)
    route_kb_assemble.set_defaults(func=command_route_kb_assemble, command_name="route kb-assemble")

    results = sub.add_parser("results", help="Parse provider results into normalized segment offers.")
    results_sub = results.add_subparsers(dest="results_command", required=True)
    results_parse = results_sub.add_parser("parse", help="Parse Travelpayouts GraphQL response or request-search live envelope.")
    results_parse.add_argument("--input", default="-", help="Raw response JSON or flights request-search envelope.")
    results_parse.add_argument("--direction", choices=["outbound", "return"], default="outbound")
    results_parse.add_argument(
        "--leg",
        choices=["origin_to_hub", "hub_to_destination", "destination_to_hub", "hub_to_origin", "segment"],
        default="segment",
    )
    results_parse.add_argument("--origin", help="Query origin IATA override.")
    results_parse.add_argument("--destination", help="Query destination IATA override.")
    results_parse.add_argument("--date", help="Query date YYYY-MM-DD override.")
    results_parse.add_argument("--currency", help="Currency override.")
    results_parse.add_argument("--limit", type=int, default=20)
    results_parse.set_defaults(func=command_results_parse, command_name="results parse")

    request = sub.add_parser("request", help="Raw Travelpayouts request builder/read-only escape hatch.")
    request_sub = request.add_subparsers(dest="request_command", required=True)
    request_search = request_sub.add_parser("search", help="Build or run one Travelpayouts GraphQL search.")
    request_search.add_argument("origin")
    request_search.add_argument("destination")
    request_search.add_argument("--depart-date", required=True)
    request_search.add_argument("--return-date")
    request_search.add_argument("--currency", default=DEFAULT_CURRENCY)
    request_search.add_argument("--direct-only", action="store_true")
    request_search.add_argument("--dry-run", action="store_true", help="Default behavior; included for explicitness.")
    request_search.add_argument("--live", action="store_true", help="Actually call Travelpayouts API using TRAVELPAYOUTS_TOKEN.")
    request_search.add_argument("--timeout", type=int, default=20)
    request_search.set_defaults(func=command_request_search, command_name="request search")

    metrics = sub.add_parser("metrics", help="Workflow metrics commands.")
    metrics_sub = metrics.add_subparsers(dest="metrics_command", required=True)
    metrics_workflow = metrics_sub.add_parser("workflow", help="Compare manual planning operations with CLI planning.")
    add_common_route_flags(metrics_workflow)
    metrics_workflow.set_defaults(func=command_metrics_workflow, command_name="metrics workflow")

    return parser


def normalize_global_json(argv: list[str]) -> list[str]:
    if "--json" not in argv[1:]:
        return argv
    return [argv[0], "--json"] + [item for item in argv[1:] if item != "--json"]


def main(argv: list[str] | None = None) -> int:
    load_env_file()
    argv = normalize_global_json(list(sys.argv if argv is None else argv))
    parser = build_parser()
    args = parser.parse_args(argv[1:])
    store = Store()
    try:
        data = args.func(args, store)
    except CliError as exc:
        if args.json:
            print(json.dumps(error_envelope(exc), ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        else:
            print(f"error: {exc.message}", file=sys.stderr)
            if exc.details is not None:
                print(json.dumps(exc.details, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    if args.json:
        emit_json(output_envelope(args.command_name, data))
    else:
        print(render_human(args.command_name, data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
