from __future__ import annotations

import unittest
from dataclasses import replace
from typing import Any
from unittest.mock import patch

from flights_cli.errors import CliError
from flights_cli.execution.search_executor import SearchExecutionState, SearchExecutor
from flights_cli.pipeline.search_plan import SearchPhases, SearchPlan
from flights_cli.ports.providers import ProviderProbeResult
from flights_cli.store import Store
from helpers import build_search_plan, coverage_completeness, live_assembly_args


class FailingAggregateAdapter:
    def __init__(self, error: CliError) -> None:
        self.name = "tutu"
        self.error = error
        self.call_count = 0

    def search_aggregate(self, _query: dict[str, Any]) -> ProviderProbeResult:
        self.call_count += 1
        raise self.error


class EmptyAggregateAdapter:
    def __init__(self, name: str) -> None:
        self.name = name

    def search_aggregate(self, query: dict[str, Any]) -> ProviderProbeResult:
        return ProviderProbeResult(
            probe_id=str(query["probe_id"]),
            probe_type="full_route_aggregate",
            provider=self.name,
            query=query,
            execution_state="searched",
            cache_status="disabled",
            evidence_type="negative_provider_empty",
            result_summary={
                "status": "ok",
                "provider": self.name,
                "offer_count": 0,
            },
        )


class SearchExecutorFailFastTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = Store()
        built_plan = SearchPlan.from_dict(
            build_search_plan(
                live_assembly_args(
                    origin="SVX",
                    destination="AMS",
                    depart_date="2026-08-15",
                    return_date=None,
                    fail_fast=True,
                    no_live_cache=True,
                ),
                self.store,
            )
        )
        self.plan = replace(
            built_plan,
            phases=SearchPhases(primary=built_plan.phases.primary),
        )

    def _capturing_executor(
        self,
    ) -> tuple[SearchExecutor, dict[str, SearchExecutionState]]:
        executor = SearchExecutor(self.store)
        original_initialize = executor.initialize_state
        captured: dict[str, SearchExecutionState] = {}

        def initialize(plan: SearchPlan) -> SearchExecutionState:
            state = original_initialize(plan)
            captured["state"] = state
            return state

        executor.initialize_state = initialize  # type: ignore[method-assign]
        return executor, captured

    def test_primary_fail_fast_records_failure_and_finalizes_remaining_attempts(
        self,
    ) -> None:
        error = CliError("provider down", error_type="provider_unavailable")
        adapter = FailingAggregateAdapter(error)
        executor, captured = self._capturing_executor()

        with patch(
            "flights_cli.execution.offer_query_runner.provider_adapter",
            return_value=adapter,
        ):
            with self.assertRaises(CliError) as raised:
                executor.execute(self.plan)

        self.assertIs(raised.exception, error)
        self.assertEqual(adapter.call_count, 1)
        diagnostics = captured["state"].probe_ledger.to_diagnostics()
        self.assertEqual(len(diagnostics["failed_probes"]), 1)
        self.assertEqual(diagnostics["failed_probes"][0]["phase"], "primary")
        self.assertEqual(
            diagnostics["failed_probes"][0]["error"]["classification"],
            "provider_unavailable",
        )
        self.assertGreater(len(diagnostics["not_executed_probes"]), 0)
        self.assertTrue(
            all(
                probe["execution_state"] == "not_executed"
                for probe in diagnostics["not_executed_probes"]
            )
        )
        self.assertEqual(
            coverage_completeness(diagnostics)["planned_count"],
            coverage_completeness(diagnostics)["terminal_count"],
        )

    def test_success_evidence_is_frozen_after_ledger_finalization(self) -> None:
        executor = SearchExecutor(self.store)

        with patch(
            "flights_cli.execution.offer_query_runner.provider_adapter",
            side_effect=lambda name, **_: EmptyAggregateAdapter(name),
        ):
            evidence = executor.execute(self.plan)

        completeness = coverage_completeness(evidence.probe_ledger)
        self.assertEqual(completeness["planned_count"], completeness["terminal_count"])
        self.assertTrue(completeness["all_planned_probes_have_terminal_state"])


if __name__ == "__main__":
    unittest.main()
