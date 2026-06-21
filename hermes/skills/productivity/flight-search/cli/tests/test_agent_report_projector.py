from __future__ import annotations

import unittest

from flights_cli.contracts.registry import current_contract
from flights_cli.reporting.agent_report_projector import (
    AGENT_REPORT_SCHEMA_VERSION,
    project_agent_report,
)
from flights_cli.services.agent_report_contract import validate_agent_report
from tests.test_agent_report_contract import valid_report


class AgentReportProjectorModuleTests(unittest.TestCase):
    def test_projector_uses_logical_name_but_keeps_agent_report_v2_wire_version(self) -> None:
        report = project_agent_report(valid_report())

        self.assertEqual(AGENT_REPORT_SCHEMA_VERSION, current_contract("agent_report")["schema_version"])
        self.assertEqual(report["schema_version"], "agent_report.v2")
        self.assertIn("user_answer", report)
        self.assertIn("diagnostics", report)

    def test_direct_flights_are_projected_into_evidence_and_pass_schema(self) -> None:
        flat = valid_report()
        sentinel = [
            {"direction": "outbound", "line": "SU6418 09:00–12:00 | без пересадки"},
            {"direction": "return", "line": "SU6419 14:00–17:00 | без пересадки"},
        ]
        flat["direct_flights"] = sentinel

        report = project_agent_report(flat)

        # Projector must carry direct_flights into the machine-facing evidence block,
        # not silently drop it (regression for 3fa0521 follow-up #1).
        self.assertEqual(report["evidence"]["direct_flights"], sentinel)
        # And the schema must allow the key — otherwise exposing it via the projector
        # would flip a silent drop into a hard validation crash.
        validate_agent_report(report)

    def test_direct_flights_default_to_empty_list_when_absent(self) -> None:
        flat = valid_report()
        flat.pop("direct_flights", None)

        report = project_agent_report(flat)

        self.assertEqual(report["evidence"]["direct_flights"], [])
        validate_agent_report(report)


if __name__ == "__main__":
    unittest.main()
