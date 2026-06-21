from __future__ import annotations

import argparse
import inspect
import unittest
from unittest.mock import patch

import flights_cli.execution.aggregate_control_runner as aggregate_control_runner
import flights_cli.execution.probe_dispatcher as probe_dispatcher
from flights_cli.cli import build_parser
from flights_cli.execution.aggregate_control_runner import AggregateControlOptions, run_aggregate_controls
from flights_cli.orchestrators.live_route_assembly import run_live_route_assembly
from flights_cli.ports.providers import ProviderCapabilities, ProviderProbeResult
from flights_cli.store import Store
from helpers import live_assembly_args


class FakeAggregateAdapter:
    name = "kupibilet"
    capabilities = ProviderCapabilities(probe_types=frozenset({"full_route_aggregate"}), supports_full_route_aggregate=True)

    def __init__(self) -> None:
        self.aggregate_queries: list[dict[str, object]] = []

    def search_segment(self, query: dict[str, object]) -> ProviderProbeResult:
        raise AssertionError("not used by aggregate runner")

    def search_aggregate(self, query: dict[str, object]) -> ProviderProbeResult:
        self.aggregate_queries.append(query)
        return ProviderProbeResult(
            probe_id=str(query.get("probe_id") or "aggregate-probe"),
            probe_type="full_route_aggregate",
            provider="kupibilet",
            query={"origin": query["origin"], "destination": query["destination"], "date": query["date"]},
            execution_state="searched",
            cache_status="disabled",
            evidence_type="positive_live_evidence",
            result_summary={
                "direction": query["direction"],
                "origin": query["origin"],
                "destination": query["destination"],
                "date": query["date"],
                "status": "ok",
                "provider": "kupibilet",
                "filters": {"direct_only": False, "only_carriers": query["only_carriers"]},
                "offer_count": 1,
                "raw_offer_count": 1,
                "suppressed_three_plus_count": 0,
                "suppressed_airport_change_count": 0,
                "cache_status": "disabled",
                "top_offers": [{"id": "agg-adapter-offer"}],
            },
            normalized_offers=[{"id": "agg-adapter-offer"}],
        )


class FakeSegmentAdapter:
    name = "kupibilet"
    capabilities = ProviderCapabilities(probe_types=frozenset({"segment_direct", "segment_hub_leg"}))

    def __init__(self) -> None:
        self.segment_queries: list[dict[str, object]] = []

    def search_segment(self, query: dict[str, object]) -> ProviderProbeResult:
        self.segment_queries.append(query)
        leg = str(query["leg"])
        return ProviderProbeResult(
            probe_id=str(query.get("probe_id") or "fake-segment"),
            probe_type="segment_direct" if leg in {"direct_outbound", "direct_return"} else "segment_hub_leg",
            provider="kupibilet",
            query={"origin": query["origin"], "destination": query["destination"], "date": query["date"]},
            execution_state="searched",
            cache_status="disabled",
            evidence_type="negative_provider_empty",
            result_summary={
                "direction": query["direction"],
                "leg": leg,
                "origin": query["origin"],
                "destination": query["destination"],
                "date": query["date"],
                "status": "ok",
                "provider": "kupibilet",
                "offer_count": 0,
                "cache_status": "disabled",
            },
            normalized_result={
                "direction": query["direction"],
                "leg": leg,
                "origin": query["origin"],
                "destination": query["destination"],
                "offers": [],
            },
        )

    def search_aggregate(self, query: dict[str, object]) -> ProviderProbeResult:
        raise AssertionError("not used by segment pipeline test")


class ProviderPortDispatchTests(unittest.TestCase):
    def test_live_route_assembly_dispatches_segment_search_through_provider_port(self) -> None:
        args = live_assembly_args(
                origin='SVX',
                destination='LON',
                depart_date='2026-07-20',
                provider_policy='kupibilet',
                max_segment_searches=40,
                aggregate_control_limit=0,
                no_live_cache=True,
                no_direct_route_intel=True,
            )
        adapter = FakeSegmentAdapter()

        with patch("flights_cli.execution.probe_dispatcher.provider_adapters_for_segment", return_value=[adapter], create=True):
            result = run_live_route_assembly(args, Store())

        self.assertGreaterEqual(len(adapter.segment_queries), 1)
        self.assertEqual(result["live_search"]["segment_searches"][0]["provider"], "kupibilet")

    def test_aggregate_controls_execute_through_provider_port(self) -> None:
        options = AggregateControlOptions(
            aggregate_control_limit=3,
            only_carriers=("SU",),
            aggregate_control_carriers=(),
            live_cache_ttl_seconds=0,
            no_live_cache=True,
            timeout=10,
            provider_policy="kupibilet",
        )
        plan = {
            "origin": "SVX",
            "destination": "DEL",
            "currency": "RUB",
            "dates": {"depart": "2026-08-12", "return": None},
        }
        adapter = FakeAggregateAdapter()

        with patch("flights_cli.execution.aggregate_control_runner.provider_adapter", return_value=adapter, create=True):
            controls = run_aggregate_controls(options, plan)

        self.assertEqual(len(controls), 1)
        self.assertEqual(controls[0]["provider"], "kupibilet")
        self.assertEqual(controls[0]["top_offers"], [{"id": "agg-adapter-offer"}])
        self.assertEqual(adapter.aggregate_queries[0]["only_carriers"], ["SU"])
        self.assertFalse(adapter.aggregate_queries[0]["direct_only"])

    def test_execution_layer_has_no_direct_provider_search_symbols(self) -> None:
        dispatcher_source = inspect.getsource(probe_dispatcher)
        aggregate_source = inspect.getsource(aggregate_control_runner)
        forbidden_symbols = [
            "cached_kupibilet_search",
            "cached_fli_mcp_search",
            "kupibilet_result_to_segment_result",
            "kupibilet_segment_search_summary",
            "fli_result_to_segment_result",
            "fli_segment_search_summary",
        ]
        for symbol in forbidden_symbols:
            self.assertNotIn(symbol, dispatcher_source)
            self.assertNotIn(symbol, aggregate_source)


if __name__ == "__main__":
    unittest.main()
