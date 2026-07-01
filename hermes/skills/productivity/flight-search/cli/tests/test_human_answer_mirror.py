from __future__ import annotations

import unittest

from flights_cli.errors import CliError
from flights_cli.output import render_agent_report_human
from flights_cli.reporting.projections.human_answer_mirror import (
    build_human_answer_mirror,
)
from flights_cli.reporting.user_answer import validate_user_answer
from flights_cli.services.agent_report import build_agent_report
from flights_cli.services.agent_report_contract import validate_agent_report
from tests.test_agent_report_contract import valid_report
from tests.test_provider_aggregate_candidates import report_payload


class HumanAnswerMirrorTests(unittest.TestCase):
    def test_human_answer_projection_only_mirrors_canonical_user_answer(self) -> None:
        report = valid_report()
        report["user_answer"]["rendered_text"] = "CANONICAL USER ANSWER"
        report["display"]["text"] = "STALE DISPLAY"
        report["answer_lines"] = ["STALE ANSWER LINE"]

        mirror = build_human_answer_mirror(report)

        self.assertEqual(mirror["format_version"], "flight_human_answer.v1")
        self.assertEqual(mirror["text"], "CANONICAL USER ANSWER")
        self.assertEqual(mirror["sections"], [])

    def test_human_answer_projection_does_not_render_without_user_answer(self) -> None:
        report = valid_report()
        report.pop("user_answer", None)
        report["display"]["text"] = "STALE DISPLAY"
        report["answer_lines"] = ["STALE ANSWER LINE"]

        mirror = build_human_answer_mirror(report)

        self.assertEqual(mirror["text"], "")
        self.assertEqual(mirror["sections"], [])

    def test_agent_report_attaches_canonical_user_answer_and_cli_human_render_uses_it(
        self,
    ) -> None:
        report = build_agent_report(report_payload())

        validate_agent_report(report)
        validate_user_answer(report["user_answer"])
        text = report["user_answer"]["rendered_text"]
        self.assertEqual(report["diagnostics"]["human_answer"]["text"], text)
        self.assertNotIn("agent report:", render_agent_report_human(report))
        self.assertEqual(render_agent_report_human(report), text)

    def test_cli_human_render_prefers_canonical_v3_user_answer_over_legacy_projections(
        self,
    ) -> None:
        report = valid_report()
        canonical_text = report["user_answer"]["rendered_text"]
        report["human_answer"]["text"] = "STALE HUMAN ANSWER"
        report["display"]["text"] = "STALE DISPLAY"
        report["answer_lines"] = ["STALE ANSWER LINE"]

        self.assertEqual(render_agent_report_human(report), canonical_text)
        self.assertNotEqual(render_agent_report_human(report), "STALE HUMAN ANSWER")

    def test_cli_human_render_rejects_invalid_user_answer_instead_of_diagnostics_fallback(
        self,
    ) -> None:
        report = valid_report()
        report["user_answer"] = {"schema_version": "flight_search_user_answer.v4"}
        report["human_answer"]["text"] = "STALE HUMAN ANSWER"
        report["display"]["text"] = "STALE DISPLAY"
        report["answer_lines"] = ["STALE ANSWER LINE"]

        with self.assertRaises(CliError) as ctx:
            render_agent_report_human(report)

        self.assertEqual(ctx.exception.error_type, "contract_error")

    def test_cli_human_render_rejects_legacy_v2_user_answer(self) -> None:
        report = valid_report()
        report["user_answer"]["schema_version"] = "flight_search_user_answer.v2"
        report["user_answer"]["rendered_text"] = "LEGACY V2 USER ANSWER"

        with self.assertRaises(CliError):
            render_agent_report_human(report)


if __name__ == "__main__":
    unittest.main()
