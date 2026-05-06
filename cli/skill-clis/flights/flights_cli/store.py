from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import CACHE_DIR, IATA_RE, SPECIAL_CITY_AIRPORTS
from .errors import CliError

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
        self._countries: list[dict[str, Any]] | None = None
        self._cities: list[dict[str, Any]] | None = None
        self._airports: list[dict[str, Any]] | None = None
        self._airlines: list[dict[str, Any]] | None = None
        self._alliances: list[dict[str, Any]] | None = None
        self._planes: list[dict[str, Any]] | None = None
        self._routes: list[dict[str, Any]] | None = None
        self._city_by_code: dict[str, dict[str, Any]] | None = None
        self._airport_by_code: dict[str, dict[str, Any]] | None = None
        self._airline_by_code: dict[str, dict[str, Any]] | None = None
        self._alliances_by_airline: dict[str, list[str]] | None = None
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

    def load_manifest(self, filename: str = "catalog_manifest.json") -> dict[str, Any]:
        path = self.cache_dir / filename
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    @property
    def countries(self) -> list[dict[str, Any]]:
        if self._countries is None:
            self._countries = self.load_json("countries.json")
        return self._countries

    @property
    def cities(self) -> list[dict[str, Any]]:
        if self._cities is None:
            self._cities = self.load_json("cities_ru.json")
        return self._cities

    @property
    def airports(self) -> list[dict[str, Any]]:
        if self._airports is None:
            self._airports = self.load_json("airports_en.json")
        return self._airports

    @property
    def airlines(self) -> list[dict[str, Any]]:
        if self._airlines is None:
            self._airlines = self.load_json("airlines_en.json")
        return self._airlines

    @property
    def alliances(self) -> list[dict[str, Any]]:
        if self._alliances is None:
            self._alliances = self.load_json("alliances.json")
        return self._alliances

    @property
    def planes(self) -> list[dict[str, Any]]:
        if self._planes is None:
            self._planes = self.load_json("planes.json")
        return self._planes

    @property
    def routes(self) -> list[dict[str, Any]]:
        if self._routes is None:
            self._routes = self.load_json("routes.json")
        return self._routes

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
    def airline_by_code(self) -> dict[str, dict[str, Any]]:
        if self._airline_by_code is None:
            self._airline_by_code = {
                str(airline.get("code", "")).upper(): airline
                for airline in self.airlines
                if airline.get("code")
            }
        return self._airline_by_code

    @property
    def alliances_by_airline(self) -> dict[str, list[str]]:
        if self._alliances_by_airline is None:
            grouped: dict[str, list[str]] = defaultdict(list)
            for alliance in self.alliances:
                name = str(alliance.get("name") or "").strip()
                airlines = alliance.get("airlines")
                if not name or not isinstance(airlines, list):
                    continue
                for airline in airlines:
                    code = str(airline or "").upper()
                    if code:
                        grouped[code].append(name)
            self._alliances_by_airline = {code: sorted(names) for code, names in grouped.items()}
        return self._alliances_by_airline

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
            "countries": len(self.countries),
            "cities": len(self.cities),
            "airports": len(self.airports),
            "airlines": len(self.airlines),
            "alliances": len(self.alliances),
            "planes": len(self.planes),
            "routes": len(self.routes),
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
