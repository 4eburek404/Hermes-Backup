from __future__ import annotations

import unittest

from flights_cli.contracts.registry import DIAGNOSTIC_PROJECTIONS
from flights_cli.reporting.projections.human_answer_mirror import build_human_answer_mirror
from flights_cli.reporting.projections.itinerary_display import build_itinerary_display
from flights_cli.reporting.projections.summary_lines import build_summary_lines
from tests.test_agent_report_contract import valid_report
from tests.test_user_answer_contract import report_with_required_caveats


class DiagnosticProjectionModuleTests(unittest.TestCase):
    def test_projection_modules_use_diagnostic_names(self) -> None:
        report = report_with_required_caveats()

        human_answer = build_human_answer_mirror(report)
        display = build_itinerary_display(report)
        summary_lines = build_summary_lines(report)

        self.assertEqual(DIAGNOSTIC_PROJECTIONS["human_answer_mirror"]["status"], "diagnostic_projection")
        self.assertIn("text", human_answer)
        self.assertEqual(display["format_version"], "flight_display.v1")
        self.assertIsInstance(summary_lines, list)

    def test_diagnostic_projections_are_not_canonical_answer_paths(self) -> None:
        projection_paths = {item["path"] for item in DIAGNOSTIC_PROJECTIONS.values()}

        self.assertIn("data.agent_report.diagnostics.human_answer", projection_paths)
        self.assertIn("data.agent_report.diagnostics.display", projection_paths)
        self.assertIn("data.agent_report.diagnostics.answer_lines", projection_paths)
        self.assertNotIn("data.agent_report.user_answer.rendered_text", projection_paths)

    def test_legacy_projection_module_aliases_delegate_to_new_names(self) -> None:
        from flights_cli.reporting.answer_line_renderer import build_answer_lines
        from flights_cli.reporting.flight_display import build_flight_display
        from flights_cli.reporting.projections.human_answer_mirror import build_human_answer_mirror

        report = valid_report()

        self.assertEqual(build_answer_lines(report), build_summary_lines(report))
        self.assertEqual(build_flight_display(report), build_itinerary_display(report))
        self.assertEqual(build_human_answer_mirror(report), build_human_answer_mirror(report))


if __name__ == "__main__":
    unittest.main()
