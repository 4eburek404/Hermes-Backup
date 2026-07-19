from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from flights_cli.orchestrators.search_plan_builder import (
    build_route_context,
)
from flights_cli.domain.airports import explicit_or_resolved_airports
from flights_cli.store import Store
from helpers import build_search_plan, live_assembly_args


def live_args(**overrides: object):
    defaults = {
        "origin": "IST",
        "destination": "LON",
        "depart_date": "2026-08-12",
        "return_date": None,
        "hub": None,
        "routing_strategy": "auto",
        "origin_airport": None,
        "destination_airport": None,
        "currency": "RUB",
        "only_carrier": [],
        "profile": "business",
        "min_same_airport_min": 120,
        "min_cross_airport_min": 300,
        "max_airports_per_city": 6,
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

    def test_aggregate_provider_plans_preserve_city_scope_in_both_directions(
        self,
    ) -> None:
        store = catalog_store(self)
        expected_outbound = (["AAA", "AAB"], ["BBA", "BBB", "BBC"])

        for provider in ("tutu", "kupibilet"):
            with self.subTest(provider=provider):
                plan = build_search_plan(
                    live_args(
                        origin="AAA",
                        destination="BBB",
                        return_date="2026-08-19",
                        provider_policy=provider,
                    ),
                    store,
                )
                queries = [
                    query
                    for query in plan["phases"]["primary"]
                    if query["provider"] == provider
                ]
                outbound = next(
                    query for query in queries if query["direction"] == "outbound"
                )
                inbound = next(
                    query for query in queries if query["direction"] == "return"
                )
                self.assertEqual(
                    (
                        outbound["query"]["origin_airports"],
                        outbound["query"]["destination_airports"],
                    ),
                    expected_outbound,
                )
                self.assertEqual(
                    (
                        inbound["query"]["origin_airports"],
                        inbound["query"]["destination_airports"],
                    ),
                    tuple(reversed(expected_outbound)),
                )

    def test_domestic_mow_round_trip_does_not_add_intra_moscow_hub_fallback(
        self,
    ) -> None:
        plan = build_route_context(
            live_args(
                origin="SVX",
                destination="MOW",
                return_date="2026-08-19",
                destination_airports=["DME", "SVO", "VKO"],
            ),
            Store(),
        )

        self.assertNotIn("segments", plan)


if __name__ == "__main__":
    unittest.main()
