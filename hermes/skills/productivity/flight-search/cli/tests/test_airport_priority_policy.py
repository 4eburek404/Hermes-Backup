from __future__ import annotations

import unittest
from unittest.mock import patch

from flights_cli.execution.probe_dispatcher import (
    SegmentProbeOptions,
    dispatch_segment_probe,
)
from flights_cli.orchestrators.search_plan_builder import build_route_context
from flights_cli.store import Store
from helpers import live_assembly_args


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
        "exclude_carrier": [],
        "prefer_carrier": [],
        "avoid_carrier": [],
        "ticketing": "separate",
        "profile": "business",
        "min_same_airport_min": 120,
        "min_cross_airport_min": 300,
        "max_airports_per_city": 6,
        "coverage_mode": "targeted",
        "coverage_control": None,
        "coverage_control_limit": 12,
        "outbound_second_leg_day_offset": None,
        "return_second_leg_day_offset": None,
        "segment_limit": 30,
        "timeout": 60,
        "aggregate_control_limit": 0,
        "aggregate_control_carrier": None,
        "max_segment_searches": 300,
        "fail_fast": False,
        "live_cache_ttl_seconds": 0,
        "no_live_cache": True,
        "provider_policy": "auto",
    }
    defaults.update(overrides)
    return live_assembly_args(**defaults)


def dispatcher_options(**overrides: object) -> SegmentProbeOptions:
    values = {
        "segment_limit": 10,
        "timeout": 10,
        "fli_mcp_url": None,
        "fail_fast": False,
    }
    values.update(overrides)
    return SegmentProbeOptions(**values)


def kupibilet_result(
    query_origin: str,
    query_destination: str,
    actual_origin: str,
    actual_destination: str,
) -> dict[str, object]:
    return {
        "origin": query_origin,
        "destination": query_destination,
        "depart_date": "2026-08-12",
        "currency": "RUB",
        "source": "Kupibilet frontend_search (live aggregate)",
        "raw_variant_count": 1,
        "unique_flight_count": 1,
        "skipped": {},
        "offers": [
            {
                "id": "offer-1",
                "price": 10000,
                "currency": "RUB",
                "number_of_changes": 0,
                "duration": 120,
                "departure_at": "2026-08-12T10:00:00+03:00",
                "arrival_at": "2026-08-12T12:00:00+05:00",
                "segments": [
                    {
                        "origin": actual_origin,
                        "destination": actual_destination,
                        "departure_at": "2026-08-12T10:00:00+03:00",
                        "arrival_at": "2026-08-12T12:00:00+05:00",
                        "flight_number": "SU1400",
                        "marketing_carrier": "SU",
                        "operating_carrier": "SU",
                        "duration": 120,
                    }
                ],
            }
        ],
    }


def empty_kupibilet_result(
    query_origin: str, query_destination: str, depart_date: object
) -> dict[str, object]:
    depart = (
        depart_date.isoformat()
        if hasattr(depart_date, "isoformat")
        else str(depart_date)
    )
    return {
        "origin": query_origin,
        "destination": query_destination,
        "depart_date": depart,
        "currency": "RUB",
        "source": "Kupibilet frontend_search (live aggregate)",
        "raw_variant_count": 0,
        "unique_flight_count": 0,
        "skipped": {},
        "offers": [],
    }


class AirportPriorityPolicyTests(unittest.TestCase):
    def test_domestic_mow_round_trip_does_not_add_intra_moscow_hub_fallback(
        self,
    ) -> None:
        plan = build_route_context(
            live_args(origin="SVX", destination="MOW", return_date="2026-08-19"),
            Store(),
        )

        self.assertNotIn("segments", plan)

    def test_kupibilet_city_code_post_validation_accepts_moscow_actual_airport(
        self,
    ) -> None:
        spec = {
            "direction": "outbound",
            "leg": "direct_outbound",
            "origin": "MOW",
            "destination": "SVX",
            "date": "2026-08-12",
        }
        with (
            patch(
                "flights_cli.adapters.providers.registry.providers_for_segment",
                return_value=["kupibilet"],
            ),
            patch(
                "flights_cli.adapters.providers.kupibilet_adapter.cached_kupibilet_search",
                return_value=kupibilet_result("MOW", "SVX", "SVO", "SVX"),
            ),
        ):
            outcomes = dispatch_segment_probe(
                spec=spec,
                plan={"currency": "RUB"},
                options=dispatcher_options(),
                store=Store(),
                only_carriers=[],
                cache_ttl_seconds=0,
                use_live_cache=False,
                provider_policy="kupibilet",
            )

        self.assertEqual(outcomes[0].summary["status"], "ok")
        self.assertEqual(
            outcomes[0].summary["city_code_validation"]["accepted_offer_count"], 1
        )
        self.assertEqual(
            outcomes[0].segment_result["offers"][0]["departure_airport"], "SVO"
        )

    def test_kupibilet_city_code_post_validation_rejects_out_of_scope_airport(
        self,
    ) -> None:
        spec = {
            "direction": "outbound",
            "leg": "direct_outbound",
            "origin": "MOW",
            "destination": "SVX",
            "date": "2026-08-12",
        }
        with (
            patch(
                "flights_cli.adapters.providers.registry.providers_for_segment",
                return_value=["kupibilet"],
            ),
            patch(
                "flights_cli.adapters.providers.kupibilet_adapter.cached_kupibilet_search",
                return_value=kupibilet_result("MOW", "SVX", "ZIA", "SVX"),
            ),
        ):
            outcomes = dispatch_segment_probe(
                spec=spec,
                plan={"currency": "RUB"},
                options=dispatcher_options(),
                store=Store(),
                only_carriers=[],
                cache_ttl_seconds=0,
                use_live_cache=False,
                provider_policy="kupibilet",
            )

        self.assertEqual(outcomes[0].summary["status"], "invalid")
        self.assertEqual(
            outcomes[0].summary["reason"], "city_code_scope_validation_failed"
        )
        self.assertEqual(outcomes[0].summary["offer_count"], 0)
        self.assertEqual(
            outcomes[0].summary["city_code_validation"]["rejected_reasons"],
            {"origin_out_of_scope": 1},
        )
        self.assertEqual(outcomes[0].segment_result["offers"], [])

    def test_kupibilet_city_code_post_validation_marks_missing_actual_airport_fields_invalid(
        self,
    ) -> None:
        spec = {
            "direction": "outbound",
            "leg": "direct_outbound",
            "origin": "SVX",
            "destination": "MOW",
            "date": "2026-08-12",
        }
        result = kupibilet_result("SVX", "MOW", "SVX", "")
        with (
            patch(
                "flights_cli.adapters.providers.registry.providers_for_segment",
                return_value=["kupibilet"],
            ),
            patch(
                "flights_cli.adapters.providers.kupibilet_adapter.cached_kupibilet_search",
                return_value=result,
            ),
        ):
            outcomes = dispatch_segment_probe(
                spec=spec,
                plan={"currency": "RUB"},
                options=dispatcher_options(),
                store=Store(),
                only_carriers=[],
                cache_ttl_seconds=0,
                use_live_cache=False,
                provider_policy="kupibilet",
            )

        self.assertEqual(outcomes[0].summary["status"], "invalid")
        self.assertEqual(
            outcomes[0].summary["reason"], "city_code_scope_validation_failed"
        )
        self.assertEqual(
            outcomes[0].summary["city_code_validation"]["rejected_reasons"],
            {"missing_actual_airport_fields": 1},
        )


if __name__ == "__main__":
    unittest.main()
