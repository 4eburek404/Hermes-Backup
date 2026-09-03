from __future__ import annotations

import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from flights_cli.domain.airports import explicit_or_resolved_airports
from flights_cli.errors import CliError
from flights_cli.store import Store
from helpers import build_search_plan, future_departure_date, live_assembly_args


def live_args(**overrides: object):
    defaults = {
        "origin": "IST",
        "destination": "LON",
        "return_date": None,
        "origin_airport": None,
        "destination_airport": None,
        "currency": "RUB",
        "only_carrier": [],
        "segment_limit": 30,
        "timeout": 60,
        "max_segment_searches": 300,
        "fail_fast": False,
        "live_cache_ttl_seconds": 0,
        "no_live_cache": True,
        "provider_policy": "auto",
    }
    defaults.update(overrides)
    return live_assembly_args(**defaults)


def catalog_store(test_case: unittest.TestCase) -> Store:
    tmp_dir = tempfile.TemporaryDirectory()
    test_case.addCleanup(tmp_dir.cleanup)
    cache = Path(tmp_dir.name)
    cities = [
        {
            "code": "AAA",
            "name": "Город отправления",
            "country_code": "TR",
            "has_flightable_airport": True,
        },
        {
            "code": "BBB",
            "name": "Город назначения",
            "country_code": "GB",
            "has_flightable_airport": True,
        },
    ]
    airports = [
        {
            "code": "AAA",
            "city_code": "AAA",
            "country_code": "TR",
            "flightable": True,
            "iata_type": "airport",
        },
        {
            "code": "AAB",
            "city_code": "AAA",
            "country_code": "TR",
            "flightable": True,
            "iata_type": "airport",
        },
        {
            "code": "AAC",
            "city_code": "AAA",
            "country_code": "TR",
            "flightable": True,
            "iata_type": "railway",
        },
        {
            "code": "BBA",
            "city_code": "BBB",
            "country_code": "GB",
            "flightable": True,
            "iata_type": "airport",
        },
        {
            "code": "BBB",
            "city_code": "BBB",
            "country_code": "GB",
            "flightable": True,
            "iata_type": "airport",
        },
        {
            "code": "BBC",
            "city_code": "BBB",
            "country_code": "GB",
            "flightable": True,
            "iata_type": "airport",
        },
    ]
    (cache / "cities_ru.json").write_text(json.dumps(cities), encoding="utf-8")
    (cache / "airports_en.json").write_text(json.dumps(airports), encoding="utf-8")
    return Store(cache)


class AirportPriorityPolicyTests(unittest.TestCase):
    def test_city_scope_comes_from_catalog_and_excludes_non_airports(self) -> None:
        store = catalog_store(self)

        origin = store.resolve_location("Город отправления")
        destination = store.resolve_location("Город назначения")

        self.assertEqual(origin.kind, "city")
        self.assertEqual(origin.airports, ["AAA", "AAB"])
        self.assertEqual(destination.airports, ["BBA", "BBB", "BBC"])

    def test_explicit_airport_scope_remains_exact_when_city_code_is_the_same(
        self,
    ) -> None:
        store = catalog_store(self)

        location = store.resolve_location("AAA")
        airports = explicit_or_resolved_airports(
            location,
            ["AAA"],
            role="origin",
            max_airports=6,
        )

        self.assertEqual(location.kind, "city")
        self.assertEqual(location.airports, ["AAA", "AAB"])
        self.assertEqual(airports, ["AAA"])

    def test_aggregate_provider_plans_preserve_city_scope(self) -> None:
        store = catalog_store(self)
        depart = future_departure_date()
        expected = (["AAA", "AAB"], ["BBA", "BBB", "BBC"])

        for provider in ("tutu", "kupibilet"):
            with self.subTest(provider=provider):
                plan = build_search_plan(
                    live_args(
                        origin="AAA",
                        destination="BBB",
                        depart_date=depart.isoformat(),
                        provider_policy=provider,
                    ),
                    store,
                )
                queries = [
                    query
                    for query in plan["phases"]["primary"]
                    if query["provider"] == provider
                ]
                self.assertEqual(len(queries), 1)
                self.assertEqual(
                    (
                        queries[0]["query"]["origin_airports"],
                        queries[0]["query"]["destination_airports"],
                    ),
                    expected,
                )

    def test_round_trip_keeps_outbound_scope_on_the_single_probe(self) -> None:
        store = catalog_store(self)
        depart = future_departure_date()
        return_date = (depart + timedelta(days=7)).isoformat()

        plan = build_search_plan(
            live_args(
                origin="AAA",
                destination="BBB",
                depart_date=depart.isoformat(),
                return_date=return_date,
                provider_policy="tutu",
            ),
            store,
        )

        attempts = plan["phases"]["primary"]
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["direction"], "outbound")
        self.assertEqual(attempts[0]["query"]["origin_airports"], ["AAA", "AAB"])
        self.assertEqual(
            attempts[0]["query"]["destination_airports"], ["BBA", "BBB", "BBC"]
        )
        self.assertEqual(attempts[0]["query"]["return_date"], return_date)

    def test_round_trip_is_refused_for_a_provider_without_the_capability(self) -> None:
        store = catalog_store(self)
        depart = future_departure_date()

        with self.assertRaises(CliError) as raised:
            build_search_plan(
                live_args(
                    origin="AAA",
                    destination="BBB",
                    depart_date=depart.isoformat(),
                    return_date=(depart + timedelta(days=7)).isoformat(),
                    provider_policy="kupibilet",
                ),
                store,
            )

        self.assertEqual(raised.exception.error_type, "validation_error")
        self.assertIn("round-trip", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
