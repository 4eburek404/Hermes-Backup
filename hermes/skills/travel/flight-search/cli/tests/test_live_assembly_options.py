from __future__ import annotations

import unittest
from datetime import date, timedelta

from flights_cli.config import DEFAULT_CATALOG_LIMIT, DEFAULT_DIRECT_CATALOG_LIMIT
from flights_cli.errors import CliError
from flights_cli.pipeline.search_request import (
    ExecutionSettings,
    search_request_from_payload,
)
from helpers import future_departure_date


def _request(depart: date) -> dict[str, object]:
    return {
        "schema_version": "flight_search_request.v1",
        "origin": "svx",
        "destination": "lon",
        "depart_date": depart.isoformat(),
        "return_date": (depart + timedelta(days=7)).isoformat(),
        "currency": "rub",
        "provider_policy": "auto",
        "origin_airports": ["SVX"],
        "destination_airports": ["LHR"],
        "max_connections": 0,
        "preferred_connections": 0,
        "only_carriers": ["SU"],
        "limit": 12,
    }


class SearchRequestTests(unittest.TestCase):
    def test_provider_policy_schema_defers_nonempty_names_to_registry(self) -> None:
        depart = future_departure_date()
        request = _request(depart)
        options = search_request_from_payload(
            {**request, "provider_policy": "future_provider"}
        )

        self.assertEqual(options.provider_policy, "future_provider")
        with self.assertRaises(CliError):
            search_request_from_payload({**request, "provider_policy": ""})

    def test_search_request_maps_request_fields(self) -> None:
        depart = future_departure_date()
        options = search_request_from_payload(_request(depart))

        self.assertEqual(options.route.origin, "SVX")
        self.assertEqual(options.route.destination, "LON")
        self.assertEqual(options.route.depart_date, depart.isoformat())
        self.assertEqual(
            options.route.return_date, (depart + timedelta(days=7)).isoformat()
        )
        self.assertEqual(options.route.origin_airports, ("SVX",))
        self.assertEqual(options.route.destination_airports, ("LHR",))
        self.assertEqual(options.filters.only_carriers, ("SU",))
        self.assertEqual(options.output.catalog_limit, 12)
        self.assertEqual(options.output.direct_catalog_limit, 12)

    def test_execution_budgets_are_not_part_of_the_public_request(self) -> None:
        depart = future_departure_date()
        request = _request(depart)

        # Бюджеты приходят отдельным объектом, а в запросе их присутствие —
        # ошибка контракта: запрос описывает желание, а не стоимость прогона.
        with self.assertRaises(CliError):
            search_request_from_payload({**request, "timeout": 42})

        options = search_request_from_payload(
            request, ExecutionSettings(timeout=42, no_live_cache=True)
        )
        self.assertEqual(options.execution.timeout, 42)
        self.assertTrue(options.no_live_cache)

    def test_unknown_property_is_rejected(self) -> None:
        depart = future_departure_date()
        request = _request(depart)
        with self.assertRaises(CliError):
            search_request_from_payload({**request, "profile": "safe"})

    def test_search_request_maps_carrier_filters(self) -> None:
        depart = future_departure_date()
        request = {
            "schema_version": "flight_search_request.v1",
            "origin": "nte",
            "destination": "svx",
            "depart_date": depart.isoformat(),
            "only_carriers": ["AF"],
        }
        options = search_request_from_payload(request)

        self.assertEqual(options.filters.only_carriers, ("AF",))
        self.assertEqual(options.effective_only_carriers(), ("AF",))
        self.assertEqual(search_request_from_payload(request), options)

    def test_search_request_defaults_are_explicit_in_typed_options(self) -> None:
        depart = future_departure_date()
        options = search_request_from_payload(
            {
                "schema_version": "flight_search_request.v1",
                "origin": "svx",
                "destination": "lon",
                "depart_date": depart.isoformat(),
            }
        )

        self.assertEqual(options.route.origin, "SVX")
        self.assertEqual(options.route.destination, "LON")
        self.assertEqual(options.currency, "RUB")
        self.assertEqual(options.provider_policy, "auto")
        self.assertIsNone(options.route.max_connections)
        self.assertIsNone(options.route.preferred_connections)
        self.assertEqual(options.output.catalog_limit, DEFAULT_CATALOG_LIMIT)
        self.assertEqual(
            options.output.direct_catalog_limit, DEFAULT_DIRECT_CATALOG_LIMIT
        )

    def test_zero_is_a_value_not_an_absence(self) -> None:
        depart = future_departure_date()
        options = search_request_from_payload(
            {
                "schema_version": "flight_search_request.v1",
                "origin": "svx",
                "destination": "dme",
                "depart_date": depart.isoformat(),
                "max_connections": 0,
                "preferred_connections": 0,
                "limit": 1,
            },
            ExecutionSettings(live_cache_ttl_seconds=0),
        )

        self.assertEqual(options.route.max_connections, 0)
        self.assertEqual(options.route.preferred_connections, 0)
        self.assertEqual(options.execution.live_cache_ttl_seconds, 0)
        self.assertEqual(options.output.catalog_limit, 1)
        self.assertEqual(options.output.direct_catalog_limit, 1)


if __name__ == "__main__":
    unittest.main()
