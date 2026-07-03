from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from flights_cli.execution.aggregate_control_runner import (
    AggregateControlOptions,
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

    def test_auto_policy_uses_tutu_then_kupibilet_and_marks_fli_unsupported(
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
            ["ok", "ok", "not_supported"],
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
