from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .catalog_storage import CatalogStorage
from .config import IATA_RE, resolve_cache_dir
from .errors import CliError


@dataclass(slots=True)
class Location:
    input: str
    code: str
    kind: str
    country_code: str | None = None
    airports: list[str] | None = None


class Store:
    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or resolve_cache_dir()
        self.catalog_storage = CatalogStorage(self.cache_dir)
        self._countries: list[dict[str, Any]] | None = None
        self._cities: list[dict[str, Any]] | None = None
        self._airports: list[dict[str, Any]] | None = None
        self._airlines: list[dict[str, Any]] | None = None
        self._localized_airlines: list[dict[str, Any]] | None = None
        self._alliances: list[dict[str, Any]] | None = None
        self._planes: list[dict[str, Any]] | None = None
        self._city_by_code: dict[str, dict[str, Any]] | None = None
        self._airport_by_code: dict[str, dict[str, Any]] | None = None
        self._airports_by_city: dict[str, list[dict[str, Any]]] | None = None

    @property
    def countries(self) -> list[dict[str, Any]]:
        if self._countries is None:
            self._countries = self.catalog_storage.read_rows("countries.json")
        return self._countries

    @property
    def cities(self) -> list[dict[str, Any]]:
        if self._cities is None:
            self._cities = self.catalog_storage.read_rows("cities_ru.json")
        return self._cities

    @property
    def airports(self) -> list[dict[str, Any]]:
        if self._airports is None:
            self._airports = self.catalog_storage.read_rows("airports_en.json")
        return self._airports

    @property
    def airlines(self) -> list[dict[str, Any]]:
        if self._airlines is None:
            self._airlines = self.catalog_storage.read_rows("airlines_en.json")
        return self._airlines

    @property
    def localized_airlines(self) -> list[dict[str, Any]]:
        if self._localized_airlines is None:
            self._localized_airlines = self.catalog_storage.read_rows(
                "airlines_ru.json"
            )
        return self._localized_airlines

    def airline_rows(self, *, localized_first: bool = False) -> list[dict[str, Any]]:
        """Return semantic airline metadata without exposing storage filenames."""

        first = self.localized_airlines if localized_first else self.airlines
        second = self.airlines if localized_first else self.localized_airlines
        return [*first, *second]

    @property
    def alliances(self) -> list[dict[str, Any]]:
        if self._alliances is None:
            self._alliances = self.catalog_storage.read_rows("alliances.json")
        return self._alliances

    @property
    def planes(self) -> list[dict[str, Any]]:
        if self._planes is None:
            self._planes = self.catalog_storage.read_rows("planes.json")
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
            "countries": len(self.countries),
            "cities": len(self.cities),
            "airports": len(self.airports),
            "airlines": len(self.airlines),
            "alliances": len(self.alliances),
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
                names.extend(
                    str(value).lower() for value in translations.values() if value
                )

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
                    not bool(city.get("has_flightable_airport")),
                    -len(
                        self.flightable_airports_for_city(str(city.get("code") or ""))
                    ),
                    str(city.get("country_code") or ""),
                    str(city.get("code") or ""),
                ),
            )

        seen: set[str] = set()
        results: list[dict[str, Any]] = []
        for city in (
            ranked(exact_code)
            + ranked(exact_name)
            + ranked(starts_with)
            + ranked(contains)
        ):
            code = str(city.get("code") or "").upper()
            if code and code not in seen:
                seen.add(code)
                results.append(city)
            if len(results) >= limit:
                break
        return results

    def resolve_location(self, value: str) -> Location:
        raw = value.strip()
        if not raw:
            raise CliError("location is required", error_type="validation_error")
        code = raw.upper()
        if IATA_RE.match(code):
            airport = self.airport_by_code.get(code)
            city = self.city_by_code.get(code)
            if city:
                airports = [a["code"] for a in self.flightable_airports_for_city(code)]
                if airports:
                    return Location(
                        input=raw,
                        code=code,
                        kind="city",
                        country_code=str(city.get("country_code") or "") or None,
                        airports=airports,
                    )
            if airport:
                return Location(
                    input=raw,
                    code=code,
                    kind="airport",
                    country_code=str(airport.get("country_code") or "") or None,
                    airports=[code],
                )
            return Location(input=raw, code=code, kind="iata", airports=[code])

        matches = self.search_cities(raw, limit=6)
        flightable = [city for city in matches if city.get("has_flightable_airport")]
        if len(flightable) == 1:
            city = flightable[0]
            city_code = str(city.get("code") or "").upper()
            airports = [a["code"] for a in self.flightable_airports_for_city(city_code)]
            return Location(
                input=raw,
                code=city_code,
                kind="city",
                country_code=str(city.get("country_code") or "") or None,
                airports=airports,
            )
        airport_counts = [
            (city, len(self.flightable_airports_for_city(str(city.get("code") or ""))))
            for city in flightable
        ]
        max_airport_count = max((count for _, count in airport_counts), default=0)
        best_supported = [
            city for city, count in airport_counts if count == max_airport_count
        ]
        if max_airport_count and len(best_supported) == 1:
            city = best_supported[0]
            city_code = str(city.get("code") or "").upper()
            return Location(
                input=raw,
                code=city_code,
                kind="city",
                country_code=str(city.get("country_code") or "") or None,
                airports=[
                    airport["code"]
                    for airport in self.flightable_airports_for_city(city_code)
                ],
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
            if airport.get("flightable", True)
            and str(airport.get("iata_type") or "").lower() in {"", "airport"}
            and IATA_RE.fullmatch(str(airport.get("code") or "").upper())
        ]
        return sorted(flightable, key=lambda item: str(item.get("code") or ""))


def city_to_output(store: Store, city: dict[str, Any]) -> dict[str, Any]:
    code = str(city.get("code") or "").upper()
    airports = [a["code"] for a in store.flightable_airports_for_city(code)]
    translations = (
        city.get("name_translations")
        if isinstance(city.get("name_translations"), dict)
        else {}
    )
    return {
        "code": code,
        "name": city.get("name"),
        "name_en": translations.get("en"),
        "country_code": city.get("country_code"),
        "has_flightable_airport": bool(city.get("has_flightable_airport")),
        "airports": airports,
    }
