from __future__ import annotations

import unittest
from unittest.mock import patch

from flights_cli.orchestrators.search_workflow import SearchWorkflow
from flights_cli.ports.providers import ProviderCapabilities, ProviderProbeResult
from flights_cli.store import Store
from helpers import future_departure_date, live_assembly_args


class FakeAggregateAdapter:
    name = "kupibilet"
    capabilities = ProviderCapabilities(
        probe_types=frozenset({"full_route_aggregate"}),
        supports_full_route_aggregate=True,
    )

    def __init__(self) -> None:
        self.queries: list[dict[str, object]] = []
        self.segment_queries: list[dict[str, object]] = []

    def search_segment(self, query: dict[str, object]) -> ProviderProbeResult:
        """Шлюзовое плечо ходит сюда, а не в агрегатный порт.

        Раньше метод бросал исключение, а сам фейк подставлялся только в
        offer_query_runner — поэтому плечо уходило в живой Kupibilet мимо него.
        """

        self.segment_queries.append(query)
        return ProviderProbeResult(
            probe_id=str(query.get("probe_id") or "segment-probe"),
            probe_type="segment_direct",
            provider="kupibilet",
            query=dict(query),
            execution_state="searched",
            cache_status="disabled",
            evidence_type="negative_provider_empty",
            result_summary={"status": "ok", "provider": "kupibilet", "offer_count": 0},
            offers=(),
        )

    def search_aggregate(self, query: dict[str, object]) -> ProviderProbeResult:
        self.queries.append(query)
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
        depart = future_departure_date()
        args = live_assembly_args(
            origin="SVX",
            destination="LON",
            depart_date=depart.isoformat(),
            provider_policy="kupibilet",
            max_segment_searches=40,
            no_live_cache=True,
        )
        adapter = FakeAggregateAdapter()

        # Два независимых шва: агрегатный путь резолвит адаптер у себя, шлюзовое
        # плечо — через реестр. Патчить надо оба, иначе тест уходит в живую сеть.
        with (
            patch(
                "flights_cli.execution.offer_query_runner.provider_adapter",
                return_value=adapter,
            ),
            patch(
                "flights_cli.adapters.providers.registry.provider_adapter",
                return_value=adapter,
            ),
        ):
            result = SearchWorkflow(Store()).run_artifacts(args)

        self.assertGreaterEqual(len(adapter.queries), 1)
        self.assertEqual(
            result.evidence.primary_offer_results[0]["provider"], "kupibilet"
        )


if __name__ == "__main__":
    unittest.main()
