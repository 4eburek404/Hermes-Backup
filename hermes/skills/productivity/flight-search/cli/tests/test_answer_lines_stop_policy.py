from __future__ import annotations

import copy
import unittest

from flights_cli.reporting.answer_line_renderer import build_answer_lines
from flights_cli.reporting.final_answer_contract import build_user_answer_contract, validate_user_answer_contract
from flights_cli.services.agent_report_contract import validate_agent_report
from tests.test_agent_report_contract import valid_option, valid_report
from flights_cli.errors import CliError


class AnswerLinesStopPolicyTests(unittest.TestCase):
    def test_answer_lines_do_not_tease_suppressed_garbage_routes(self) -> None:
        report = valid_report()
        report["stop_policy"] = {
            "name": "business_default",
            "preferred_max_connections": 1,
            "fallback_max_connections": 2,
            "hard_max_connections": 2,
            "two_stop_allowed_only_if_no_preferred": True,
            "three_plus_reportable": False,
        }
        report["stop_policy_diagnostics"] = {
            "policy": "business_default",
            "used_two_stop_fallback": False,
            "three_plus_suppressed_count": 7,
            "two_stop_suppressed_because_preferred_exists": 2,
            "garbage_options_hidden_from_answer": True,
        }
        report["answer_lines"] = build_answer_lines(report)
        text = "\n".join(report["answer_lines"])

        self.assertIn("three_plus_suppressed=7", text)
        self.assertNotIn("крайне дешевые", text.lower())
        self.assertNotIn("Ереван и Милан", text)
        self.assertNotIn("сложные маршруты", text.lower())

    def test_agent_report_rejects_three_plus_user_facing_option(self) -> None:
        report = valid_report()
        bad = copy.deepcopy(valid_option())
        bad["id"] = "bad-three-plus"
        bad["stop_tier"] = "T3_THREE_PLUS"
        bad["max_connections_per_journey"] = 3
        report["priority_options"] = [bad]
        report["answer_lines"].append("Priority control: bad-three-plus.")

        with self.assertRaises(CliError):
            validate_agent_report(report)

    def test_user_answer_rejects_two_stop_without_fallback_status(self) -> None:
        report = valid_report()
        two_stop = copy.deepcopy(valid_option())
        two_stop["id"] = "two-stop"
        two_stop["stop_tier"] = "T2_TWO_STOP"
        two_stop["max_connections_per_journey"] = 2
        report["priority_options"] = [two_stop]
        report["stop_policy"] = {
            "name": "business_default",
            "preferred_max_connections": 1,
            "fallback_max_connections": 2,
            "hard_max_connections": 2,
            "two_stop_allowed_only_if_no_preferred": True,
            "three_plus_reportable": False,
        }
        report["stop_policy_diagnostics"] = {"policy": "business_default", "used_two_stop_fallback": False}
        answer = build_user_answer_contract(report)

        with self.assertRaises(CliError):
            validate_user_answer_contract(answer)


if __name__ == "__main__":
    unittest.main()
