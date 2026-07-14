from __future__ import annotations

import unittest
from unittest.mock import patch

from flights_cli.execution.aggregate_control_runner import (
    AggregateControlOptions,
    run_aggregate_controls,
)
from flights_cli.execution.search_executor import execute_search
from flights_cli.ports.providers import ProviderCapabilities, ProviderProbeResult
from flights_cli.store import Store
from helpers import live_assembly_args


class FakeAggregateAdapter:
    name = "kupibilet"
    capabilities = ProviderCapabilities(
        probe_types=frozenset({"full_route_aggregate"}),
        supports_full_route_aggregate=True,
    )

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
            query={
                "origin": query["origin"],
                "destination": query["destination"],
                "date": query["date"],
            },
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
                "filters": {
                    "direct_only": False,
                    "only_carriers": query["only_carriers"],
                },
                "offer_count": 1,
                "raw_offer_count": 1,
                "suppressed_three_plus_count": 0,
                "suppressed_airport_change_count": 0,
                "cache_status": "disabled",
                "top_offers": [{"id": "agg-adapter-offer"}],
            },
            offers=({"id": "agg-adapter-offer"},),
        )


class ProviderPortDispatchTests(unittest.TestCase):
    def test_search_executor_dispatches_primary_offer_through_provider_port(
        self,
    ) -> None:
        args = live_assembly_args(
            origin="SVX",
            destination="LON",
            depart_date="2026-07-20",
            provider_policy="kupibilet",
            max_segment_searches=40,
            aggregate_control_limit=0,
            no_live_cache=True,
        )
        adapter = FakeAggregateAdapter()

        with (
            patch(
                "flights_cli.execution.offer_query_runner.provider_adapter",
                return_value=adapter,
                create=True,
            ),
            patch(
                "flights_cli.execution.search_executor.SearchWavePlanner.run",
                return_value={},
            ),
        ):
            result = execute_search(args, Store()).projection_input

        self.assertGreaterEqual(len(adapter.aggregate_queries), 1)
        self.assertEqual(
            result["live_search"]["primary_offer_results"][0]["provider"], "kupibilet"
        )

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

        with patch(
            "flights_cli.execution.aggregate_control_runner.provider_adapter",
            return_value=adapter,
            create=True,
        ):
            controls = run_aggregate_controls(
                options,
                plan,
                planned_queries=[
                    {
                        "role": "aggregate_evidence",
                        "source_type": "provider_full_route",
                        "probe_type": "carrier_aggregate",
                        "provider": None,
                        "direction": "outbound",
                        "origin": "SVX",
                        "destination": "DEL",
                        "date": "2026-08-12",
                        "currency": "RUB",
                        "direct_only": False,
                        "only_carriers": ["SU"],
                        "limit": 3,
                        "execution_state": "not_executed",
                    }
                ],
            )

        self.assertEqual(len(controls), 1)
        self.assertEqual(controls[0]["provider"], "kupibilet")
        self.assertEqual(controls[0]["top_offers"], [{"id": "agg-adapter-offer"}])
        self.assertEqual(adapter.aggregate_queries[0]["only_carriers"], ["SU"])
        self.assertFalse(adapter.aggregate_queries[0]["direct_only"])


if __name__ == "__main__":
    unittest.main()
