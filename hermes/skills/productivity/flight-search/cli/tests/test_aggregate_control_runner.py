from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from flights_cli.execution.aggregate_control_runner import (
    AggregateControlOptions,
    evaluate_graph_coverage_controls,
    run_aggregate_controls,
)
from flights_cli.execution.probe_ledger import ProbeExecutionLedger
from flights_cli.errors import CliError
from flights_cli.ports.providers import ProviderProbeResult
from flights_cli.store import Store


def aggregate_options(**overrides: object) -> AggregateControlOptions:
    values = {
        "aggregate_control_limit": 3,
        "aggregate_control_carriers": (),
        "only_carriers": (),
        "provider_policy": "fli",
        "live_cache_ttl_seconds": 0,
        "no_live_cache": True,
        "timeout": 10,
    }
    values.update(overrides)
    return AggregateControlOptions(**values)


def store_with_airports(test_case: unittest.TestCase) -> Store:
    tmp_dir = tempfile.TemporaryDirectory()
    test_case.addCleanup(tmp_dir.cleanup)
    cache = Path(tmp_dir.name)
    (cache / "airports_en.json").write_text(
        """
        [
          {"code": "SVX", "country_code": "RU", "flightable": true},
          {"code": "CDG", "country_code": "FR", "flightable": true},
          {"code": "IST", "country_code": "TR", "flightable": true},
          {"code": "LHR", "country_code": "GB", "flightable": true}
        ]
        """,
        encoding="utf-8",
    )
    return Store(cache)


class FakeAggregateAdapter:
    def __init__(self, name: str) -> None:
        self.name = name
        self.aggregate_queries: list[dict[str, Any]] = []

    def search_aggregate(self, query: dict[str, Any]) -> ProviderProbeResult:
        self.aggregate_queries.append(query)
        return ProviderProbeResult(
            probe_id=str(query["probe_id"]),
            probe_type="full_route_aggregate",
            provider=self.name,
            query=query,
            execution_state="searched",
            cache_status="disabled",
            evidence_type="positive_live_evidence",
            result_summary={
                "direction": query["direction"],
                "origin": query["origin"],
                "destination": query["destination"],
                "date": query["date"],
                "status": "ok",
                "provider": self.name,
                "filters": {
                    "direct_only": False,
                    "only_carriers": query["only_carriers"],
                },
                "offer_count": 1,
                "raw_offer_count": 1,
                "suppressed_three_plus_count": 0,
                "suppressed_airport_change_count": 0,
                "cache_status": "disabled",
                "top_offers": [{"id": "agg-offer"}],
            },
            normalized_offers=[{"id": "agg-offer"}],
        )


class FakeKupibiletAggregateAdapter(FakeAggregateAdapter):
    def __init__(self) -> None:
        super().__init__("kupibilet")


class FailingAggregateAdapter(FakeAggregateAdapter):
    def search_aggregate(self, query: dict[str, Any]) -> ProviderProbeResult:
        self.aggregate_queries.append(query)
        raise CliError(
            f"{self.name} unavailable",
            error_type="provider_unavailable",
            details={"provider": self.name},
        )


class AggregateControlRunnerTests(unittest.TestCase):
    def test_fli_policy_ru_touching_aggregate_is_skipped_by_route_boundary(
        self,
    ) -> None:
        plan = {
            "origin": "SVX",
            "destination": "CDG",
            "dates": {"depart": "2026-08-16", "return": None},
            "currency": "RUB",
        }
        ledger = ProbeExecutionLedger()

        controls = run_aggregate_controls(
            aggregate_options(),
            plan,
            probe_ledger=ledger,
            store=store_with_airports(self),
        )

        diagnostics = ledger.to_coverage_diagnostics(
            {"coverage_mode": "targeted", "coverage_limits": {}}
        )
        self.assertEqual(len(controls), 1)
        self.assertEqual(controls[0]["status"], "skipped")
        self.assertEqual(controls[0]["provider"], "fli")
        self.assertEqual(controls[0]["reason"], "route_touches_ru")
        self.assertEqual(
            [item["type"] for item in diagnostics["skipped_controls"]],
            ["full_route_aggregate"],
        )
        self.assertEqual(diagnostics["not_supported_controls"], [])
        self.assertEqual(diagnostics["not_executed_controls"], [])
        self.assertEqual(
            diagnostics["completeness"]["planned_count"],
            diagnostics["completeness"]["terminal_count"],
        )
        self.assertTrue(
            diagnostics["completeness"]["all_planned_controls_have_terminal_state"]
        )

    def test_kupibilet_policy_executes_supported_aggregate(self) -> None:
        plan = {
            "origin": "SVX",
            "destination": "CDG",
            "dates": {"depart": "2026-08-16", "return": None},
            "currency": "RUB",
        }
        adapter = FakeKupibiletAggregateAdapter()

        def adapter_lookup(name: str, **_: Any) -> FakeKupibiletAggregateAdapter:
            if name != "kupibilet":
                raise AssertionError(f"unexpected aggregate adapter {name}")
            return adapter

        with patch(
            "flights_cli.execution.aggregate_control_runner.provider_adapter",
            side_effect=adapter_lookup,
        ):
            controls = run_aggregate_controls(
                aggregate_options(provider_policy="kupibilet"),
                plan,
                store=store_with_airports(self),
            )

        self.assertEqual(len(controls), 1)
        self.assertEqual(controls[0]["provider"], "kupibilet")
        self.assertEqual(controls[0]["status"], "ok")
        self.assertEqual(len(adapter.aggregate_queries), 1)

    def test_graph_evidence_satisfies_control_before_provider_probe(self) -> None:
        plan = {
            "origin": "SVX",
            "destination": "CDG",
            "dates": {"depart": "2026-08-16", "return": None},
            "currency": "RUB",
        }
        offer_graph = {
            "schema_version": "flight_offer_graph.v1",
            "edges": [
                {
                    "id": "edge-1",
                    "origin": "SVX",
                    "destination": "CDG",
                    "departure_at": "2026-08-16T10:00:00+05:00",
                    "carrier": "SU",
                }
            ],
            "offers": [
                {
                    "id": "graph-offer",
                    "source_type": "provider_full_route",
                    "provider": "tutu",
                    "direction": "outbound",
                    "route": ["SVX", "CDG"],
                    "edge_ids": ["edge-1"],
                    "price": 42000,
                    "currency": "RUB",
                }
            ],
        }
        ledger = ProbeExecutionLedger()

        with patch(
            "flights_cli.execution.aggregate_control_runner.provider_adapter",
            side_effect=AssertionError("provider probe should not run"),
        ):
            controls = run_aggregate_controls(
                aggregate_options(provider_policy="kupibilet", only_carriers=("SU",)),
                plan,
                probe_ledger=ledger,
                store=store_with_airports(self),
                offer_graph=offer_graph,
            )

        diagnostics = ledger.to_coverage_diagnostics({"coverage_mode": "targeted"})
        self.assertEqual(len(controls), 1)
        self.assertEqual(controls[0]["provider"], "graph")
        self.assertEqual(controls[0]["status"], "graph_derived")
        self.assertTrue(controls[0]["graph_derived"])
        self.assertEqual(controls[0]["source_providers"], ["tutu"])
        self.assertEqual(diagnostics["searched_controls"][0]["provider"], "graph")
        self.assertEqual(
            diagnostics["searched_controls"][0]["evidence_type"],
            "provider_positive",
        )

    def test_policy_control_is_satisfied_by_direct_graph_evidence(self) -> None:
        plan = {
            "origin": "SVX",
            "destination": "CDG",
            "dates": {"depart": "2026-08-16", "return": None},
            "currency": "RUB",
            "coverage_controls": [
                {
                    "type": "city_pair_direct",
                    "direction": "outbound",
                    "origin": "SVX",
                    "destination": "CDG",
                    "date": "2026-08-16",
                    "negative_evidence": "city_pair_direct_not_executable_by_provider",
                }
            ],
        }
        offer_graph = {
            "schema_version": "flight_offer_graph.v1",
            "edges": [
                {
                    "id": "edge-1",
                    "origin": "SVX",
                    "destination": "CDG",
                    "departure_at": "2026-08-16T10:00:00+05:00",
                    "carrier": "SU",
                }
            ],
            "offers": [
                {
                    "id": "direct-graph-offer",
                    "source_type": "provider_full_route",
                    "provider": "tutu",
                    "direction": "outbound",
                    "route": ["SVX", "CDG"],
                    "edge_ids": ["edge-1"],
                }
            ],
        }
        ledger = ProbeExecutionLedger()

        controls = evaluate_graph_coverage_controls(
            plan,
            offer_graph,
            probe_ledger=ledger,
        )

        ledger.finalize_unexecuted()
        diagnostics = ledger.to_coverage_diagnostics(plan)
        self.assertEqual(len(controls), 1)
        self.assertEqual(controls[0]["type"], "city_pair_direct")
        self.assertEqual(controls[0]["source_type"], "graph_derived_policy_control")
        self.assertEqual(diagnostics["searched_controls"][0]["provider"], "graph")
        self.assertEqual(diagnostics["not_executed_controls"], [])

    def test_auto_policy_skips_fallback_providers_when_tutu_is_available(
        self,
    ) -> None:
        plan = {
            "origin": "IST",
            "destination": "LHR",
            "dates": {"depart": "2026-08-16", "return": None},
            "currency": "RUB",
        }
        adapters = {
            "tutu": FakeAggregateAdapter("tutu"),
            "kupibilet": FakeKupibiletAggregateAdapter(),
        }

        def adapter_lookup(name: str, **_: Any) -> FakeAggregateAdapter:
            if name not in adapters:
                raise AssertionError(f"unexpected aggregate adapter {name}")
            return adapters[name]

        with patch(
            "flights_cli.execution.aggregate_control_runner.provider_adapter",
            side_effect=adapter_lookup,
        ):
            controls = run_aggregate_controls(
                aggregate_options(provider_policy="auto"),
                plan,
                store=store_with_airports(self),
            )

        self.assertEqual(
            [control["provider"] for control in controls],
            ["tutu", "kupibilet", "fli"],
        )
        self.assertEqual(
            [control["status"] for control in controls],
            ["ok", "skipped", "skipped"],
        )
        self.assertEqual(
            [control.get("reason") for control in controls],
            [None, "tutu_mcp_available", "tutu_mcp_available"],
        )
        self.assertEqual(len(adapters["tutu"].aggregate_queries), 1)
        self.assertEqual(len(adapters["kupibilet"].aggregate_queries), 0)

    def test_auto_policy_falls_back_when_tutu_is_unavailable(self) -> None:
        plan = {
            "origin": "IST",
            "destination": "LHR",
            "dates": {"depart": "2026-08-16", "return": None},
            "currency": "RUB",
        }
        adapters = {
            "tutu": FailingAggregateAdapter("tutu"),
            "kupibilet": FakeKupibiletAggregateAdapter(),
        }

        def adapter_lookup(name: str, **_: Any) -> FakeAggregateAdapter:
            if name not in adapters:
                raise AssertionError(f"unexpected aggregate adapter {name}")
            return adapters[name]

        with patch(
            "flights_cli.execution.aggregate_control_runner.provider_adapter",
            side_effect=adapter_lookup,
        ):
            controls = run_aggregate_controls(
                aggregate_options(provider_policy="auto"),
                plan,
                store=store_with_airports(self),
            )

        self.assertEqual(
            [(control["provider"], control["status"]) for control in controls],
            [("tutu", "error"), ("kupibilet", "ok"), ("fli", "not_supported")],
        )
        self.assertEqual(len(adapters["tutu"].aggregate_queries), 1)
        self.assertEqual(len(adapters["kupibilet"].aggregate_queries), 1)

    def test_both_policy_is_rejected(self) -> None:
        plan = {
            "origin": "SVX",
            "destination": "CDG",
            "dates": {"depart": "2026-08-16", "return": None},
            "currency": "RUB",
        }

        with self.assertRaises(CliError):
            run_aggregate_controls(
                aggregate_options(provider_policy="both"),
                plan,
                store=store_with_airports(self),
            )

    def test_fli_policy_routes_non_ru_aggregate_to_not_supported(self) -> None:
        plan = {
            "origin": "IST",
            "destination": "LHR",
            "dates": {"depart": "2026-08-16", "return": None},
            "currency": "RUB",
        }

        controls = run_aggregate_controls(
            aggregate_options(provider_policy="fli"),
            plan,
            store=store_with_airports(self),
        )

        self.assertEqual(len(controls), 1)
        self.assertEqual(controls[0]["provider"], "fli")
        self.assertEqual(controls[0]["status"], "not_supported")


if __name__ == "__main__":
    unittest.main()
