from __future__ import annotations

import unittest

from flights_cli.execution.probe_ledger import ProbeExecutionLedger


def control(**overrides: object) -> dict:
    values = {
        "type": "carrier_aggregate",
        "direction": "outbound",
        "origin": "SVX",
        "destination": "CDG",
        "date": "2026-08-16",
        "carrier": "SU",
    }
    values.update(overrides)
    return values


class ProbeExecutionLedgerTests(unittest.TestCase):
    def test_planned_control_without_runtime_event_becomes_not_executed(self) -> None:
        ledger = ProbeExecutionLedger()
        ledger.plan_controls([control()])
        ledger.finalize_unexecuted()

        diagnostics = ledger.to_coverage_diagnostics({"coverage_mode": "targeted", "coverage_limits": {}})

        self.assertEqual(len(diagnostics["not_executed_controls"]), 1)
        self.assertEqual(diagnostics["not_executed_controls"][0]["execution_state"], "not_executed")
        self.assertEqual(diagnostics["completeness"]["planned_count"], diagnostics["completeness"]["terminal_count"])
        self.assertTrue(diagnostics["completeness"]["all_planned_controls_have_terminal_state"])

    def test_failed_aggregate_control_appears_in_failed_controls(self) -> None:
        item = control(type="full_route_aggregate", carrier=None)
        ledger = ProbeExecutionLedger()
        ledger.plan_controls([item])
        ledger.record_failed(item, provider="kupibilet", error={"type": "provider_error", "message": "timeout"})
        ledger.finalize_unexecuted()

        diagnostics = ledger.to_coverage_diagnostics({"coverage_mode": "targeted", "coverage_limits": {}})

        self.assertEqual(len(diagnostics["failed_controls"]), 1)
        self.assertEqual(diagnostics["failed_controls"][0]["execution_state"], "failed")
        self.assertEqual(diagnostics["failed_controls"][0]["provider"], "kupibilet")
        self.assertEqual(diagnostics["not_executed_controls"], [])
        self.assertEqual(diagnostics["completeness"]["planned_count"], diagnostics["completeness"]["terminal_count"])

    def test_duplicate_logical_probe_appears_in_deduped_controls(self) -> None:
        item = control()
        ledger = ProbeExecutionLedger()
        ledger.plan_controls([item])
        ledger.record_searched(item, status="ok", provider="kupibilet", offer_count=0)
        ledger.record_searched(item, status="ok", provider="kupibilet", offer_count=0)
        ledger.finalize_unexecuted()

        diagnostics = ledger.to_coverage_diagnostics({"coverage_mode": "targeted", "coverage_limits": {}})

        self.assertEqual(len(diagnostics["searched_controls"]), 1)
        self.assertEqual(len(diagnostics["deduped_controls"]), 1)
        self.assertEqual(diagnostics["deduped_controls"][0]["execution_state"], "deduped")
        self.assertEqual(diagnostics["completeness"]["planned_count"], diagnostics["completeness"]["terminal_count"])


if __name__ == "__main__":
    unittest.main()
