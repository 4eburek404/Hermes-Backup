from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from flights_cli.apps.search import command_search
from flights_cli.ports.providers import ProviderCapabilities, ProviderProbeResult
from flights_cli.store import Store


DEPART_DATE = "2026-08-15"
RETURN_DATE = "2026-08-22"


def _segment(
    origin: str,
    destination: str,
    departure_at: str,
    arrival_at: str,
    flight_number: str,
    carrier: str,
) -> dict[str, Any]:
    return {
        "origin": origin,
        "destination": destination,
        "departure_at": departure_at,
        "arrival_at": arrival_at,
        "flight_number": flight_number,
        "carrier": carrier,
        "marketing_carrier": carrier,
        "operating_carrier": carrier,
    }


def _offer(
    offer_id: str,
    segments: list[dict[str, Any]],
    *,
    price: int,
    carrier: str,
) -> dict[str, Any]:
    return {
        "id": offer_id,
        "origin": segments[0]["origin"],
        "destination": segments[-1]["destination"],
        "departure_airport": segments[0]["origin"],
        "arrival_airport": segments[-1]["destination"],
        "departure_at": segments[0]["departure_at"],
        "arrival_at": segments[-1]["arrival_at"],
        "price": price,
        "currency": "RUB",
        "carrier": carrier,
        "main_airline": carrier,
        "segments": segments,
        "changes": max(0, len(segments) - 1),
        "number_of_changes": max(0, len(segments) - 1),
        "flight_numbers": [str(segment["flight_number"]) for segment in segments],
    }


def _empty_result(query: dict[str, Any], provider: str) -> ProviderProbeResult:
    return ProviderProbeResult(
        probe_id=str(query.get("probe_id") or f"{provider}:empty"),
        probe_type=str(query.get("probe_type") or "segment_hub_leg"),  # type: ignore[arg-type]
        provider=provider,  # type: ignore[arg-type]
        query=dict(query),
        execution_state="searched",
        cache_status="disabled",
        evidence_type="negative_provider_empty",
        result_summary={
            "direction": query.get("direction"),
            "leg": query.get("leg"),
            "origin": query.get("origin"),
            "destination": query.get("destination"),
            "date": query.get("date"),
            "status": "ok",
            "provider": provider,
            "offer_count": 0,
            "cache_status": "disabled",
        },
        normalized_result={
            "direction": query.get("direction"),
            "leg": query.get("leg"),
            "query": {
                "origin": query.get("origin"),
                "destination": query.get("destination"),
                "date": query.get("date"),
                "currency": query.get("currency"),
            },
            "offers": [],
        },
    )


class FixtureSegmentAdapter:
    capabilities = ProviderCapabilities(
        supports_direct_only=True,
        supports_carrier_filter=True,
        supports_cache=False,
        probe_types=frozenset({"segment_direct", "segment_hub_leg"}),
    )

    def __init__(self, name: str, fixtures: "PipelineFixtures") -> None:
        self.name = name
        self.fixtures = fixtures

    def search_segment(self, query: dict[str, Any]) -> ProviderProbeResult:
        self.fixtures.segment_queries.append(
            {
                "provider": self.name,
                "origin": query.get("origin"),
                "destination": query.get("destination"),
                "date": query.get("date"),
                "leg": query.get("leg"),
                "direct_only": query.get("direct_only"),
            }
        )
        offers = [
            dict(offer)
            for offer in self.fixtures.segment_offers.get(
                (
                    str(query.get("origin") or "").upper(),
                    str(query.get("destination") or "").upper(),
                    str(query.get("date") or ""),
                    str(query.get("leg") or ""),
                ),
                [],
            )
        ]
        if not offers:
            return _empty_result(query, self.name)
        result_summary = {
            "direction": query.get("direction"),
            "leg": query.get("leg"),
            "origin": query.get("origin"),
            "destination": query.get("destination"),
            "date": query.get("date"),
            "status": "ok",
            "provider": self.name,
            "offer_count": len(offers),
            "cache_status": "disabled",
        }
        normalized_result = {
            "direction": query.get("direction"),
            "leg": query.get("leg"),
            "query": {
                "origin": query.get("origin"),
                "destination": query.get("destination"),
                "date": query.get("date"),
                "currency": query.get("currency"),
            },
            "provider": self.name,
            "source_key": f"{self.name}:fixture",
            "raw_count": len(offers),
            "parse_errors": 0,
            "offers": offers,
        }
        return ProviderProbeResult(
            probe_id=str(query.get("probe_id") or f"{self.name}:segment"),
            probe_type=str(query.get("probe_type") or "segment_hub_leg"),  # type: ignore[arg-type]
            provider=self.name,  # type: ignore[arg-type]
            query=dict(query),
            execution_state="searched",
            cache_status="disabled",
            evidence_type="positive_live_evidence",
            result_summary=result_summary,
            normalized_offers=offers,
            normalized_result=normalized_result,
        )

    def search_aggregate(self, query: dict[str, Any]) -> ProviderProbeResult:
        raise AssertionError("segment adapter must not service aggregate probes")


class FixtureAggregateAdapter:
    name = "kupibilet"
    capabilities = ProviderCapabilities(
        supports_full_route_aggregate=True,
        supports_direct_only=True,
        supports_cache=False,
        probe_types=frozenset({"full_route_aggregate", "carrier_aggregate"}),
    )

    def __init__(self, fixtures: "PipelineFixtures") -> None:
        self.fixtures = fixtures

    def search_segment(self, query: dict[str, Any]) -> ProviderProbeResult:
        raise AssertionError("aggregate adapter must not service segment probes")

    def search_aggregate(self, query: dict[str, Any]) -> ProviderProbeResult:
        self.fixtures.aggregate_queries.append(dict(query))
        offers = [
            dict(offer)
            for offer in self.fixtures.aggregate_offers.get(
                (
                    str(query.get("direction") or ""),
                    str(query.get("origin") or "").upper(),
                    str(query.get("destination") or "").upper(),
                    str(query.get("date") or ""),
                ),
                [],
            )
        ]
        result_summary = {
            "direction": query.get("direction"),
            "origin": query.get("origin"),
            "destination": query.get("destination"),
            "date": query.get("date"),
            "status": "ok",
            "provider": self.name,
            "filters": {
                "direct_only": bool(query.get("direct_only")),
                "only_carriers": list(query.get("only_carriers") or []),
            },
            "offer_count": len(offers),
            "raw_offer_count": len(offers),
            "raw_variant_count": len(offers),
            "suppressed_three_plus_count": 0,
            "suppressed_airport_change_count": 0,
            "cache_status": "disabled",
            "top_offers": offers,
            "error": None,
        }
        return ProviderProbeResult(
            probe_id=str(query.get("probe_id") or "kupibilet:aggregate"),
            probe_type=str(query.get("probe_type") or "full_route_aggregate"),  # type: ignore[arg-type]
            provider="kupibilet",
            query=dict(query),
            execution_state="searched",
            cache_status="disabled",
            evidence_type="positive_live_evidence"
            if offers
            else "negative_provider_empty",
            result_summary=result_summary,
            normalized_offers=offers,
        )


class PipelineFixtures:
    def __init__(self) -> None:
        self.segment_offers: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
        self.aggregate_offers: dict[
            tuple[str, str, str, str], list[dict[str, Any]]
        ] = {}
        self.segment_queries: list[dict[str, Any]] = []
        self.aggregate_queries: list[dict[str, Any]] = []
        self.kupibilet_segment_adapter = FixtureSegmentAdapter("kupibilet", self)
        self.fli_segment_adapter = FixtureSegmentAdapter("fli", self)
        self.aggregate_adapter = FixtureAggregateAdapter(self)

    def segment_provider(self, spec: dict[str, Any], *_: Any, **__: Any) -> list[Any]:
        origin = str(spec.get("origin") or "").upper()
        provider = (
            self.fli_segment_adapter
            if origin in {"IST", "DXB"}
            else self.kupibilet_segment_adapter
        )
        return [provider]

    def add_segment_offer(
        self,
        origin: str,
        destination: str,
        leg: str,
        offer: dict[str, Any],
        *,
        date: str = DEPART_DATE,
    ) -> None:
        self.segment_offers.setdefault((origin, destination, date, leg), []).append(
            offer
        )

    def add_aggregate_offer(
        self,
        direction: str,
        origin: str,
        destination: str,
        date: str,
        offer: dict[str, Any],
    ) -> None:
        self.aggregate_offers.setdefault(
            (direction, origin, destination, date), []
        ).append(offer)


def _request(destination: str, **overrides: Any) -> dict[str, Any]:
    route_options = {
        "routing_strategy": overrides.pop("routing_strategy", "ru-priority"),
        "hubs": overrides.pop("hubs", []),
        "max_connections": overrides.pop("max_connections", None),
        "coverage_control_limit": overrides.pop("coverage_control_limit", 6),
    }
    destination_airports = overrides.pop("destination_airports", None)
    if destination_airports is not None:
        route_options["destination_airports"] = destination_airports
    evidence = {
        "aggregate_control_limit": overrides.pop("aggregate_control_limit", 1),
        "max_segment_searches": overrides.pop("max_segment_searches", 80),
        "no_live_cache": True,
        "no_direct_route_intel": True,
    }
    output = {
        "agent_brief": False,
        "include_candidates": 5,
        "include_ranked_candidates": 5,
        "include_rejected_pairs": 20,
        "include_segment_results": overrides.pop("include_segment_results", 20),
        "max_candidates": 50,
    }
    request = {
        "schema_version": "flight_search_request.v1",
        "origin": overrides.pop("origin", "SVX"),
        "destination": destination,
        "depart_date": overrides.pop("depart_date", DEPART_DATE),
        "currency": "RUB",
        "profile": "business",
        "ticketing": "separate",
        "provider_policy": overrides.pop("provider_policy", "auto"),
        "route_options": route_options,
        "evidence": evidence,
        "output": output,
    }
    return_date = overrides.pop("return_date", None)
    if return_date is not None:
        request["return_date"] = return_date
    if overrides:
        raise AssertionError(f"unsupported request overrides: {sorted(overrides)}")
    return request


class SearchPipelineRegressionTests(unittest.TestCase):
    def run_search(
        self, request: dict[str, Any], fixtures: PipelineFixtures
    ) -> dict[str, Any]:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json") as tmp:
            json.dump(request, tmp)
            tmp.flush()
            with (
                patch(
                    "flights_cli.execution.probe_dispatcher.provider_adapters_for_segment",
                    side_effect=fixtures.segment_provider,
                ),
                patch(
                    "flights_cli.execution.aggregate_control_runner.provider_adapter",
                    return_value=fixtures.aggregate_adapter,
                ),
            ):
                return command_search(
                    argparse.Namespace(request=Path(tmp.name)), Store()
                )

    def assert_user_answer_contract(self, result: dict[str, Any]) -> str:
        self.assertEqual(result["schema_version"], "flight_search_result.v2")
        self.assertEqual(result["wire_version"], "flight_search_result.v2")
        self.assertIsInstance(result["route_result"], dict)
        report = result["agent_report"]
        self.assertIs(report, result["route_result"]["agent_report"])
        text = report["user_answer"]["rendered_text"]
        self.assertIsInstance(text, str)
        self.assertTrue(text.strip())
        for debug_key in (
            "live_search",
            "route_result",
            "segment_results",
            "aggregate_controls",
            "probe_ledger",
            "search_plan",
            "fallback_segment_plan",
            "ranked_candidates",
            "raw_variant_count",
        ):
            self.assertNotIn(debug_key, text)
        self.assertNotIn('{"', text)
        return text

    def test_svx_ams_keeps_segment_fallback_when_aggregate_is_empty(self) -> None:
        fixtures = PipelineFixtures()
        fixtures.add_segment_offer(
            "SVX",
            "IST",
            "origin_to_hub",
            _offer(
                "svx-ist-u6",
                [
                    _segment(
                        "SVX",
                        "IST",
                        f"{DEPART_DATE}T08:00:00+05:00",
                        f"{DEPART_DATE}T10:30:00+03:00",
                        "U6773",
                        "U6",
                    )
                ],
                price=10000,
                carrier="U6",
            ),
        )
        fixtures.add_segment_offer(
            "IST",
            "AMS",
            "hub_to_destination",
            _offer(
                "ist-ams-tk",
                [
                    _segment(
                        "IST",
                        "AMS",
                        f"{DEPART_DATE}T14:00:00+03:00",
                        f"{DEPART_DATE}T17:00:00+02:00",
                        "TK1953",
                        "TK",
                    )
                ],
                price=12000,
                carrier="TK",
            ),
        )

        result = self.run_search(_request("AMS"), fixtures)

        self.assert_user_answer_contract(result)
        self.assertEqual(result["route_result"]["assembly"]["candidate_count"], 1)
        self.assertEqual(
            result["route_result"]["ranked_candidates"][0]["ranked"]["price"],
            22000,
        )
        aggregate = result["route_result"]["live_search"]["aggregate_controls"][0]
        self.assertEqual(aggregate["offer_count"], 0)
        self.assertIn(
            {
                "provider": "fli",
                "origin": "IST",
                "destination": "AMS",
                "date": DEPART_DATE,
                "leg": "gateway_to_destination",
                "direct_only": False,
            },
            fixtures.segment_queries,
        )

    def test_svx_fra_keeps_cheaper_segment_fallback_over_expensive_aggregate(
        self,
    ) -> None:
        fixtures = PipelineFixtures()
        fixtures.add_segment_offer(
            "SVX",
            "IST",
            "origin_to_hub",
            _offer(
                "svx-ist-u6",
                [
                    _segment(
                        "SVX",
                        "IST",
                        f"{DEPART_DATE}T08:00:00+05:00",
                        f"{DEPART_DATE}T10:30:00+03:00",
                        "U6773",
                        "U6",
                    )
                ],
                price=11000,
                carrier="U6",
            ),
        )
        fixtures.add_segment_offer(
            "IST",
            "FRA",
            "hub_to_destination",
            _offer(
                "ist-fra-tk",
                [
                    _segment(
                        "IST",
                        "FRA",
                        f"{DEPART_DATE}T13:30:00+03:00",
                        f"{DEPART_DATE}T15:40:00+02:00",
                        "TK1593",
                        "TK",
                    )
                ],
                price=14000,
                carrier="TK",
            ),
        )
        fixtures.add_aggregate_offer(
            "outbound",
            "SVX",
            "FRA",
            DEPART_DATE,
            _offer(
                "svx-fra-aggregate-expensive",
                [
                    _segment(
                        "SVX",
                        "SVO",
                        f"{DEPART_DATE}T06:00:00+05:00",
                        f"{DEPART_DATE}T06:45:00+03:00",
                        "SU1419",
                        "SU",
                    ),
                    _segment(
                        "SVO",
                        "FRA",
                        f"{DEPART_DATE}T14:00:00+03:00",
                        f"{DEPART_DATE}T16:10:00+02:00",
                        "SU2300",
                        "SU",
                    ),
                ],
                price=90000,
                carrier="SU",
            ),
        )

        result = self.run_search(_request("FRA"), fixtures)

        self.assert_user_answer_contract(result)
        ranked = result["route_result"]["ranked_candidates"][0]
        self.assertEqual(ranked["ranked"]["price"], 25000)
        self.assertLess(
            ranked["ranked"]["price"],
            result["route_result"]["live_search"]["aggregate_controls"][0][
                "top_offers"
            ][0]["price"],
        )
        recommended = result["agent_report"]["frontier"]["recommended_options"][0]
        self.assertNotEqual(recommended.get("category"), "provider_aggregate_candidate")

    def test_svx_lon_preserves_lhr_lgw_stn_airport_scope(self) -> None:
        fixtures = PipelineFixtures()
        fixtures.add_segment_offer(
            "SVX",
            "IST",
            "origin_to_hub",
            _offer(
                "svx-ist-u6",
                [
                    _segment(
                        "SVX",
                        "IST",
                        f"{DEPART_DATE}T08:00:00+05:00",
                        f"{DEPART_DATE}T10:30:00+03:00",
                        "U6773",
                        "U6",
                    )
                ],
                price=10000,
                carrier="U6",
            ),
        )
        for airport, flight, price, arrival in (
            ("LHR", "TK1979", 13000, "16:50"),
            ("LGW", "TK1981", 12500, "17:15"),
            ("STN", "TK7790", 9000, "18:30"),
        ):
            fixtures.add_segment_offer(
                "IST",
                airport,
                "hub_to_destination",
                _offer(
                    f"ist-{airport.lower()}",
                    [
                        _segment(
                            "IST",
                            airport,
                            f"{DEPART_DATE}T13:30:00+03:00",
                            f"{DEPART_DATE}T{arrival}:00+01:00",
                            flight,
                            "TK",
                        )
                    ],
                    price=price,
                    carrier="TK",
                ),
            )

        result = self.run_search(
            _request(
                "LON",
                routing_strategy="hub-list",
                hubs=["IST"],
                aggregate_control_limit=0,
                destination_airports=["LHR", "LGW", "STN"],
            ),
            fixtures,
        )

        text = self.assert_user_answer_contract(result)
        plan = result["route_result"]["live_search"]["plan"]
        self.assertEqual(["LHR", "LGW", "STN"], plan["destination_airports"])
        search_summaries = result["route_result"]["live_search"]["segment_searches"]
        self.assertIn(
            {
                "destination": "LGW",
                "status": "skipped",
                "reason": "preferred_airport_tier_has_offers",
            },
            [
                {
                    "destination": search.get("destination"),
                    "status": search.get("status"),
                    "reason": search.get("reason"),
                }
                for search in search_summaries
                if search.get("origin") == "IST"
            ],
        )
        candidate_destinations = {
            segment["destination"]
            for detail in result["route_result"]["ranked_candidates"]
            for journey in detail["candidate"]["journeys"]
            for segment in journey["segments"]
            if segment["origin"] == "IST"
        }
        self.assertEqual({"LHR", "STN"}, candidate_destinations)
        self.assertIn("LON", text)

    def test_connected_direct_probe_result_is_not_direct_inventory(self) -> None:
        fixtures = PipelineFixtures()
        fixtures.add_segment_offer(
            "SVX",
            "IST",
            "direct_outbound",
            _offer(
                "svx-svo-ist-connected",
                [
                    _segment(
                        "SVX",
                        "SVO",
                        f"{DEPART_DATE}T00:40:00+05:00",
                        f"{DEPART_DATE}T01:10:00+03:00",
                        "SU1419",
                        "SU",
                    ),
                    _segment(
                        "SVO",
                        "IST",
                        f"{DEPART_DATE}T07:20:00+03:00",
                        f"{DEPART_DATE}T12:20:00+03:00",
                        "SU2172",
                        "SU",
                    ),
                ],
                price=29000,
                carrier="SU",
            ),
        )
        fixtures.add_segment_offer(
            "SVX",
            "IST",
            "direct_outbound",
            _offer(
                "svx-ist-nonstop",
                [
                    _segment(
                        "SVX",
                        "IST",
                        f"{DEPART_DATE}T07:20:00+05:00",
                        f"{DEPART_DATE}T10:50:00+03:00",
                        "U6773",
                        "U6",
                    )
                ],
                price=33000,
                carrier="U6",
            ),
        )

        result = self.run_search(
            _request("IST", aggregate_control_limit=0, max_segment_searches=20),
            fixtures,
        )

        self.assert_user_answer_contract(result)
        assembly = result["route_result"]["assembly"]
        self.assertEqual(assembly["outbound_direct_count"], 1)
        self.assertFalse(assembly["all_direct_inventory"])
        self.assertEqual(assembly["direct_flights"][0]["flight_number"], "U6773")

    def test_round_trip_two_one_way_aggregates_are_not_protected_round_trip(
        self,
    ) -> None:
        fixtures = PipelineFixtures()
        fixtures.add_aggregate_offer(
            "outbound",
            "SVX",
            "FRA",
            DEPART_DATE,
            _offer(
                "agg-outbound",
                [
                    _segment(
                        "SVX",
                        "SVO",
                        f"{DEPART_DATE}T06:00:00+05:00",
                        f"{DEPART_DATE}T06:45:00+03:00",
                        "SU1419",
                        "SU",
                    ),
                    _segment(
                        "SVO",
                        "FRA",
                        f"{DEPART_DATE}T10:30:00+03:00",
                        f"{DEPART_DATE}T12:40:00+02:00",
                        "SU2300",
                        "SU",
                    ),
                ],
                price=31000,
                carrier="SU",
            ),
        )
        fixtures.add_aggregate_offer(
            "return",
            "FRA",
            "SVX",
            RETURN_DATE,
            _offer(
                "agg-return",
                [
                    _segment(
                        "FRA",
                        "SVO",
                        f"{RETURN_DATE}T13:30:00+02:00",
                        f"{RETURN_DATE}T18:00:00+03:00",
                        "SU2301",
                        "SU",
                    ),
                    _segment(
                        "SVO",
                        "SVX",
                        f"{RETURN_DATE}T21:00:00+03:00",
                        f"{RETURN_DATE}T01:20:00+05:00",
                        "SU1418",
                        "SU",
                    ),
                ],
                price=34000,
                carrier="SU",
            ),
        )

        result = self.run_search(
            _request(
                "FRA",
                return_date=RETURN_DATE,
                aggregate_control_limit=1,
                max_segment_searches=40,
            ),
            fixtures,
        )

        text = self.assert_user_answer_contract(result)
        provider_options = [
            option
            for option in result["agent_report"]["frontier"]["priority_options"]
            if option.get("category") == "provider_aggregate_candidate"
        ]
        self.assertGreaterEqual(len(provider_options), 2)
        self.assertFalse(
            any(
                option.get("ticketing_model") == "round_trip_single_ticket"
                for option in provider_options
            )
        )
        self.assertEqual(
            result["agent_report"]["frontier"]["decision_frontier"]["options"],
            [],
        )
        self.assertNotIn("protected round-trip fare", text.lower())
        self.assertIn("separate one-way", json.dumps(provider_options).lower())


if __name__ == "__main__":
    unittest.main()
