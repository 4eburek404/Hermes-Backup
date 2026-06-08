from __future__ import annotations

import unittest

from flights_cli.contracts.registry import current_contract
from flights_cli.reporting.agent_report_projector import (
    AGENT_REPORT_SCHEMA_VERSION,
    build_agent_report_v2,
    project_agent_report,
)
from tests.test_agent_report_contract import valid_report


class AgentReportProjectorModuleTests(unittest.TestCase):
    def test_projector_uses_logical_name_but_keeps_agent_report_v2_wire_version(self) -> None:
        report = project_agent_report(valid_report())

        self.assertEqual(AGENT_REPORT_SCHEMA_VERSION, current_contract("agent_report")["schema_version"])
        self.assertEqual(report["schema_version"], "agent_report.v2")
        self.assertIn("user_answer", report)
        self.assertIn("diagnostics", report)

    def test_legacy_build_agent_report_v2_alias_matches_projector(self) -> None:
        flat_report = valid_report()

        self.assertEqual(build_agent_report_v2(flat_report), project_agent_report(flat_report))


if __name__ == "__main__":
    unittest.main()
