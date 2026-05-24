from __future__ import annotations

import argparse
import unittest
from datetime import date
from unittest.mock import patch

from flights_cli.adapters.providers.registry import providers_for_segment
from flights_cli.domain.airports import explicit_or_resolved_airports
from flights_cli.execution.probe_dispatcher import dispatch_segment_probe
from flights_cli.orchestrators.kb_assemble import build_kupibilet_route_segment_plan, run_kupibilet_route_assembly
from flights_cli.store import Store


def live_args(**overrides: object) -> argparse.Namespace:
    values = {
        "origin": "IST",
        "destination": "LON",
        "depart_date": "2026-08-12",
        "return_date": None,
        "hub": None,
        "routing_strategy": "auto",
        "origin_airport": None,
        "destination_airport": None,
        "currency": "RUB",
        "direct_only": False,
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
        "limit_per_pair": 10,
        "candidate_pool_limit": 5000,
        "max_candidates": 50,
        "max_reasons": 5,
        "include_candidates": 5,
        "include_ranked_candidates": 5,
        "include_rejected_pairs": 20,
        "include_segment_results": 0,
        "aggregate_control_limit": 0,
        "aggregate_control_carrier": None,
        "max_segment_searches": 300,
        "fail_fast": False,
        "live_cache_ttl_seconds": 0,
        "no_live_cache": True,
        "direct_route_index_ttl_seconds": 0,
        "no_direct_route_intel": True,
        "agent_report": False,
        "agent_mode": False,
        "agent_brief": False,
        "provider_policy": "auto",
        "fli_mcp_url": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def dispatcher_args(**overrides: object) -> argparse.Namespace:
    values = {
        "segment_limit": 10,
        "timeout": 10,
        "fli_mcp_url": None,
        "fail_fast": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def direct_segments(plan: dict[str, object], *, direction: str = "outbound") -> list[dict[str, object]]:
    leg = "direct_outbound" if direction == "outbound" else "direct_return"
    return [
        segment
        for segment in plan["segments"]  # type: ignore[index]
        if isinstance(segment, dict)
        and segment.get("direction") == direction
        and segment.get("leg") == leg
    ]


def pairs(segments: list[dict[str, object]]) -> list[tuple[str, str]]:
    return [(str(segment["origin"]), str(segment["destination"])) for segment in segments]


def kupibilet_result(query_origin: str, query_destination: str, actual_origin: str, actual_destination: str) -> dict[str, object]:
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
                "flights": [
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


def empty_kupibilet_result(query_origin: str, query_destination: str, depart_date: object) -> dict[str, object]:
    depart = depart_date.isoformat() if hasattr(depart_date, "isoformat") else str(depart_date)
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
    def test_ist_code_resolves_to_exact_ist_only_and_fli_direct_candidates_do_not_include_saw(self) -> None:
        store = Store()
        ist = store.resolve_location("IST")
        self.assertEqual(
            explicit_or_resolved_airports(store, ist, None, role="origin", max_airports=6),
            ["IST"],
        )

        plan = build_kupibilet_route_segment_plan(live_args(origin="IST", destination="LON"), store)
        outbound_direct = direct_segments(plan)

        self.assertEqual(pairs(outbound_direct), [("IST", "LHR"), ("IST", "LGW")])
        self.assertNotIn("SAW", {airport for pair in pairs(outbound_direct) for airport in pair})
        self.assertTrue(all(providers_for_segment(segment, store, "auto") == ["fli"] for segment in outbound_direct))

    def test_lon_default_policy_keeps_lhr_tier_before_lgw_and_excludes_stn_ltn(self) -> None:
        plan = build_kupibilet_route_segment_plan(live_args(origin="IST", destination="LON"), Store())

        self.assertEqual(plan["destination_airports"], ["LHR", "LGW"])
        self.assertEqual(
            plan["airport_scope"]["destination"]["preferred_airport_tiers"],
            [
                {"tier": 1, "airports": ["LHR"], "role": "preferred"},
                {"tier": 2, "airports": ["LGW"], "role": "fallback"},
            ],
        )
        self.assertEqual(plan["airport_scope"]["destination"]["excluded_by_default"], ["STN", "LTN"])
        outbound_direct = direct_segments(plan)
        self.assertEqual(pairs(outbound_direct), [("IST", "LHR"), ("IST", "LGW")])
        self.assertEqual([segment["destination_airport_priority"]["tier"] for segment in outbound_direct], [1, 2])

    def test_ist_lon_round_trip_direct_candidates_are_lhr_lgw_then_lgw_lhr_to_ist_without_saw_or_stn_ltn(self) -> None:
        plan = build_kupibilet_route_segment_plan(
            live_args(origin="IST", destination="LON", return_date="2026-08-19"),
            Store(),
        )

        outbound_direct = direct_segments(plan, direction="outbound")
        return_direct = direct_segments(plan, direction="return")

        self.assertEqual(pairs(outbound_direct), [("IST", "LHR"), ("IST", "LGW")])
        self.assertEqual(pairs(return_direct), [("LHR", "IST"), ("LGW", "IST")])
        generated_airports = {airport for pair in pairs(outbound_direct + return_direct) for airport in pair}
        self.assertFalse({"SAW", "STN", "LTN"} & generated_airports)

    def test_kupibilet_mow_destination_and_origin_generate_city_code_first_with_exact_fallbacks(self) -> None:
        svx_to_mow = build_kupibilet_route_segment_plan(live_args(origin="SVX", destination="MOW"), Store())
        mow_to_svx = build_kupibilet_route_segment_plan(live_args(origin="MOW", destination="SVX"), Store())

        outbound_to_mow = direct_segments(svx_to_mow)
        outbound_from_mow = direct_segments(mow_to_svx)

        self.assertEqual(pairs(outbound_to_mow)[0], ("SVX", "MOW"))
        self.assertEqual(pairs(outbound_from_mow)[0], ("MOW", "SVX"))
        self.assertEqual(outbound_to_mow[0]["provider_request_strategy"], "city_code_first")
        self.assertEqual(outbound_from_mow[0]["provider_request_strategy"], "city_code_first")
        self.assertEqual(
            [pair for pair in pairs(outbound_to_mow) if pair[1] in {"SVO", "DME", "VKO"}],
            [("SVX", "SVO"), ("SVX", "DME"), ("SVX", "VKO")],
        )
        self.assertEqual(
            [pair for pair in pairs(outbound_from_mow) if pair[0] in {"SVO", "DME", "VKO"}],
            [("SVO", "SVX"), ("DME", "SVX"), ("VKO", "SVX")],
        )
        self.assertTrue(all(segment.get("fallback_for_city_code_request") for segment in outbound_to_mow[1:4]))
        self.assertTrue(all(segment.get("fallback_for_city_code_request") for segment in outbound_from_mow[1:4]))

    def test_kupibilet_mow_to_lon_uses_moscow_city_code_with_london_preference_without_broad_fanout(self) -> None:
        plan = build_kupibilet_route_segment_plan(live_args(origin="MOW", destination="LON"), Store())
        outbound_direct = direct_segments(plan)
        direct_pairs = pairs(outbound_direct)

        self.assertEqual(direct_pairs[0], ("MOW", "LHR"))
        self.assertIn(("MOW", "LGW"), direct_pairs)
        self.assertLess(direct_pairs.index(("MOW", "LHR")), direct_pairs.index(("MOW", "LGW")))
        self.assertFalse({"STN", "LTN"} & {destination for _, destination in direct_pairs})
        self.assertLess(len(direct_pairs), 12)
        self.assertEqual(
            [segment["destination_airport_priority"]["tier"] for segment in outbound_direct if segment.get("provider_request_strategy") == "city_code_first"],
            [1, 2],
        )

    def test_kupibilet_mow_lhr_offer_skips_moscow_exact_fallbacks_and_lgw_provider_calls(self) -> None:
        args = live_args(origin="MOW", destination="LON", provider_policy="kupibilet", include_segment_results=20)
        calls: list[tuple[str, str]] = []

        def fake_fetch(origin: str, destination: str, depart_date: object, **_: object) -> dict[str, object]:
            calls.append((origin, destination))
            if (origin, destination) == ("MOW", "LHR"):
                return kupibilet_result("MOW", "LHR", "SVO", "LHR")
            return empty_kupibilet_result(origin, destination, depart_date)

        with patch("flights_cli.orchestrators.kb_assemble.fetch_kupibilet_search", side_effect=fake_fetch):
            result = run_kupibilet_route_assembly(args, Store())

        self.assertIn(("MOW", "LHR"), calls)
        self.assertNotIn(("MOW", "LGW"), calls)
        self.assertFalse(
            {
                ("SVO", "LHR"),
                ("DME", "LHR"),
                ("VKO", "LHR"),
                ("SVO", "LGW"),
                ("DME", "LGW"),
                ("VKO", "LGW"),
            }
            & set(calls)
        )
        skipped_direct = {
            (str(search.get("origin")), str(search.get("destination"))): search.get("reason")
            for search in result["live_search"]["segment_searches"]
            if search.get("leg") == "direct_outbound" and search.get("status") == "skipped"
        }
        self.assertEqual(skipped_direct[("MOW", "LGW")], "preferred_airport_tier_has_offers")
        self.assertEqual(skipped_direct[("SVO", "LHR")], "city_code_request_has_offers")
        self.assertEqual(skipped_direct[("SVO", "LGW")], "preferred_airport_tier_has_offers")

    def test_kupibilet_mow_lgw_fallback_waits_until_lhr_city_and_exact_attempts_are_empty(self) -> None:
        args = live_args(origin="MOW", destination="LON", provider_policy="kupibilet", include_segment_results=20)
        calls: list[tuple[str, str]] = []

        def fake_fetch(origin: str, destination: str, depart_date: object, **_: object) -> dict[str, object]:
            calls.append((origin, destination))
            if (origin, destination) == ("MOW", "LGW"):
                return kupibilet_result("MOW", "LGW", "SVO", "LGW")
            return empty_kupibilet_result(origin, destination, depart_date)

        with patch("flights_cli.orchestrators.kb_assemble.fetch_kupibilet_search", side_effect=fake_fetch):
            run_kupibilet_route_assembly(args, Store())

        lhr_attempts = [("MOW", "LHR"), ("SVO", "LHR"), ("DME", "LHR"), ("VKO", "LHR")]
        for pair in lhr_attempts:
            self.assertIn(pair, calls)
        self.assertIn(("MOW", "LGW"), calls)
        self.assertGreater(
            calls.index(("MOW", "LGW")),
            max(calls.index(pair) for pair in lhr_attempts),
        )

    def test_kupibilet_city_code_post_validation_accepts_moscow_actual_airport(self) -> None:
        spec = {"direction": "outbound", "leg": "direct_outbound", "origin": "MOW", "destination": "SVX", "date": "2026-08-12"}
        with patch("flights_cli.execution.probe_dispatcher.providers_for_segment", return_value=["kupibilet"]), patch(
            "flights_cli.execution.probe_dispatcher.cached_kupibilet_search",
            return_value=kupibilet_result("MOW", "SVX", "SVO", "SVX"),
        ):
            outcomes = dispatch_segment_probe(
                spec=spec,
                plan={"currency": "RUB"},
                args=dispatcher_args(),
                store=Store(),
                only_carriers=[],
                cache_ttl_seconds=0,
                use_live_cache=False,
                provider_policy="kupibilet",
            )

        self.assertEqual(outcomes[0].summary["status"], "ok")
        self.assertEqual(outcomes[0].summary["city_code_validation"]["accepted_offer_count"], 1)
        self.assertEqual(outcomes[0].segment_result["offers"][0]["departure_airport"], "SVO")

    def test_kupibilet_city_code_post_validation_rejects_out_of_scope_airport(self) -> None:
        spec = {"direction": "outbound", "leg": "direct_outbound", "origin": "MOW", "destination": "SVX", "date": "2026-08-12"}
        with patch("flights_cli.execution.probe_dispatcher.providers_for_segment", return_value=["kupibilet"]), patch(
            "flights_cli.execution.probe_dispatcher.cached_kupibilet_search",
            return_value=kupibilet_result("MOW", "SVX", "ZIA", "SVX"),
        ):
            outcomes = dispatch_segment_probe(
                spec=spec,
                plan={"currency": "RUB"},
                args=dispatcher_args(),
                store=Store(),
                only_carriers=[],
                cache_ttl_seconds=0,
                use_live_cache=False,
                provider_policy="kupibilet",
            )

        self.assertEqual(outcomes[0].summary["status"], "invalid")
        self.assertEqual(outcomes[0].summary["reason"], "city_code_scope_validation_failed")
        self.assertEqual(outcomes[0].summary["offer_count"], 0)
        self.assertEqual(outcomes[0].summary["city_code_validation"]["rejected_reasons"], {"origin_out_of_scope": 1})
        self.assertEqual(outcomes[0].segment_result["offers"], [])

    def test_kupibilet_city_code_post_validation_marks_missing_actual_airport_fields_invalid(self) -> None:
        spec = {"direction": "outbound", "leg": "direct_outbound", "origin": "SVX", "destination": "MOW", "date": "2026-08-12"}
        result = kupibilet_result("SVX", "MOW", "SVX", "")
        with patch("flights_cli.execution.probe_dispatcher.providers_for_segment", return_value=["kupibilet"]), patch(
            "flights_cli.execution.probe_dispatcher.cached_kupibilet_search",
            return_value=result,
        ):
            outcomes = dispatch_segment_probe(
                spec=spec,
                plan={"currency": "RUB"},
                args=dispatcher_args(),
                store=Store(),
                only_carriers=[],
                cache_ttl_seconds=0,
                use_live_cache=False,
                provider_policy="kupibilet",
            )

        self.assertEqual(outcomes[0].summary["status"], "invalid")
        self.assertEqual(outcomes[0].summary["reason"], "city_code_scope_validation_failed")
        self.assertEqual(outcomes[0].summary["city_code_validation"]["rejected_reasons"], {"missing_actual_airport_fields": 1})


if __name__ == "__main__":
    unittest.main()
