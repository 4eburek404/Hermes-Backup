from __future__ import annotations

import argparse
import unittest
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from flights_cli.execution.aggregate_control_runner import run_aggregate_controls
from flights_cli.execution.probe_ledger import ProbeExecutionLedger
from flights_cli.ports.providers import ProviderProbeResult


def args(**overrides: object) -> argparse.Namespace:
    values = {
        "aggregate_control_limit": 3,
        "aggregate_control_carrier": None,
        "only_carrier": [],
        "provider_policy": "fli",
        "live_cache_ttl_seconds": 0,
        "no_live_cache": True,
        "timeout": 10,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


@dataclass
class FakeAdapter:
    name: str = "fli"

    def search_aggregate(self, query: dict[str, Any]) -> ProviderProbeResult:
        return ProviderProbeResult(
            probe_id=str(query["probe_id"]),
            probe_type="full_route_aggregate",
            provider="fli",
            query=query,
            execution_state="not_supported",
            cache_status="unknown",
            evidence_type="not_supported",
            result_summary={"reason": "aggregate_probe_not_supported"},
            errors=[{"type": "not_supported", "message": "aggregate_probe_not_supported"}],
        )


class AggregateControlRunnerTests(unittest.TestCase):
    def test_not_supported_provider_aggregate_is_terminal_ledger_bucket(self) -> None:
        plan = {
            "origin": "SVX",
            "destination": "CDG",
            "dates": {"depart": "2026-08-16", "return": None},
            "currency": "RUB",
        }
        ledger = ProbeExecutionLedger()

        with patch("flights_cli.execution.aggregate_control_runner.provider_adapter", return_value=FakeAdapter()):
            controls = run_aggregate_controls(args(), plan, probe_ledger=ledger)

        diagnostics = ledger.to_coverage_diagnostics({"coverage_mode": "targeted", "coverage_limits": {}})
        self.assertEqual(len(controls), 1)
        self.assertEqual(controls[0]["status"], "not_supported")
        self.assertEqual(controls[0]["provider"], "fli")
        self.assertEqual([item["type"] for item in diagnostics["not_supported_controls"]], ["full_route_aggregate"])
        self.assertEqual(diagnostics["not_executed_controls"], [])
        self.assertEqual(diagnostics["completeness"]["planned_count"], diagnostics["completeness"]["terminal_count"])
        self.assertTrue(diagnostics["completeness"]["all_planned_controls_have_terminal_state"])


if __name__ == "__main__":
    unittest.main()
