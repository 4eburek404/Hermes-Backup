from __future__ import annotations

import unittest
from datetime import date, timedelta

from flights_cli.config import DEFAULT_CATALOG_LIMIT, DEFAULT_DIRECT_CATALOG_LIMIT
from flights_cli.errors import CliError
from flights_cli.pipeline.search_request import search_request_from_payload
from helpers import future_departure_date


def _request(depart: date) -> dict[str, object]:
    return {
        "schema_version": "flight_search_request.v3",
        "origin": "svx",
        "destination": "lon",
        "depart_date": depart.isoformat(),
        "return_date": (depart + timedelta(days=7)).isoformat(),
        "currency": "rub",
        "profile": "business",
        "provider_policy": "auto",
        "route_options": {
            "routing_strategy": "hub-list",
            "hubs": ["IST", "DXB"],
            "origin_airports": ["SVX"],
            "destination_airports": ["LHR"],
            "max_airports_per_city": 3,
            "min_same_airport_min": 150,
            "min_cross_airport_min": 360,
            "max_connections": 0,
            "tier2_max_connections": 0,
            "gateway_discovery_limit": 5,
            "gateway_probe_batch_size": 2,
            "gateway_probe_max_batches": 3,
        },
        "filters": {
            "only_carriers": ["SU"],
        },
        "evidence": {
            "segment_limit": 11,
            "timeout": 42,
            "max_segment_searches": 99,
            "fail_fast": True,
            "live_cache_ttl_seconds": 123,
            "no_live_cache": True,
        },
        "output": {
            "catalog_limit": 12,
            "direct_catalog_limit": 35,
        },
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
        request = _request(depart)
        options = search_request_from_payload(request)

        expected = {
            "origin": "SVX",
            "destination": "LON",
            "depart_date": depart.isoformat(),
            "return_date": (depart + timedelta(days=7)).isoformat(),
            "hubs": ("IST", "DXB"),
            "profile": "business",
            "only_carriers": ("SU",),
        }
        self.assertEqual(options.route.origin, expected["origin"])
        self.assertEqual(options.route.destination, expected["destination"])
        self.assertEqual(options.route.depart_date, expected["depart_date"])
        self.assertEqual(options.route.return_date, expected["return_date"])
        self.assertEqual(options.route.hubs, expected["hubs"])
        self.assertEqual(options.route.gateway_discovery_limit, 5)
        self.assertEqual(options.route.gateway_probe_batch_size, 2)
        self.assertEqual(options.route.gateway_probe_max_batches, 3)
        self.assertEqual(options.profile, expected["profile"])
        self.assertEqual(options.filters.only_carriers, expected["only_carriers"])
        self.assertEqual(options.evidence.primary_offer_limit, 35)
        self.assertEqual(options.output.catalog_limit, 12)
        self.assertEqual(options.output.direct_catalog_limit, 35)

    def test_search_app_rejects_non_business_profile(self) -> None:
        depart = future_departure_date()
        request = _request(depart)
        with self.assertRaises(CliError):
            search_request_from_payload({**request, "profile": "safe"})

    def test_search_request_maps_carrier_filters(self) -> None:
        depart = future_departure_date()
        request = {
            "schema_version": "flight_search_request.v3",
            "origin": "nte",
            "destination": "svx",
            "depart_date": depart.isoformat(),
            "filters": {"only_carriers": ["AF"]},
        }
        options = search_request_from_payload(request)

        self.assertEqual(options.filters.only_carriers, ("AF",))
        self.assertEqual(options.effective_only_carriers(), ("AF",))
        self.assertEqual(search_request_from_payload(request), options)

    def test_search_request_defaults_are_explicit_in_typed_options(self) -> None:
        depart = future_departure_date()
        options = search_request_from_payload(
            {
                "schema_version": "flight_search_request.v3",
                "origin": "svx",
                "destination": "lon",
                "depart_date": depart.isoformat(),
            }
        )

        self.assertEqual(options.route.origin, "SVX")
        self.assertEqual(options.route.destination, "LON")
        self.assertEqual(options.currency, "RUB")
        self.assertEqual(options.profile, "business")
        self.assertEqual(options.evidence.provider_policy, "auto")
        self.assertEqual(
            options.evidence.primary_offer_limit, DEFAULT_DIRECT_CATALOG_LIMIT
        )
        self.assertEqual(options.output.catalog_limit, DEFAULT_CATALOG_LIMIT)
        self.assertEqual(
            options.output.direct_catalog_limit, DEFAULT_DIRECT_CATALOG_LIMIT
        )

    def test_search_request_preserves_contract_allowed_zero_values(self) -> None:
        depart = future_departure_date()
        options = search_request_from_payload(
            {
                "schema_version": "flight_search_request.v3",
                "origin": "svx",
                "destination": "dme",
                "depart_date": depart.isoformat(),
                "route_options": {
                    "min_same_airport_min": 0,
                    "min_cross_airport_min": 0,
                    "max_connections": 0,
                    "tier2_max_connections": 0,
                    "gateway_discovery_limit": 0,
                    "gateway_probe_batch_size": 0,
                    "gateway_probe_max_batches": 0,
                },
                "evidence": {"live_cache_ttl_seconds": 0},
                "output": {
                    "catalog_limit": 1,
                    "direct_catalog_limit": 1,
                },
            }
        )

        self.assertEqual(options.route.max_connections, 0)
        self.assertEqual(options.route.tier2_max_connections, 0)
        self.assertEqual(options.route.min_same_airport_min, 0)
        self.assertEqual(options.route.min_cross_airport_min, 0)
        self.assertEqual(options.route.gateway_discovery_limit, 0)
        self.assertEqual(options.route.gateway_probe_batch_size, 0)
        self.assertEqual(options.route.gateway_probe_max_batches, 0)
        self.assertEqual(options.evidence.live_cache_ttl_seconds, 0)
        self.assertEqual(options.evidence.primary_offer_limit, 1)
        self.assertEqual(options.output.catalog_limit, 1)
        self.assertEqual(options.output.direct_catalog_limit, 1)


if __name__ == "__main__":
    unittest.main()
