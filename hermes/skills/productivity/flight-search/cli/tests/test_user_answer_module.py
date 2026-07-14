from __future__ import annotations

import unittest

from flights_cli.contracts.registry import current_contract
from flights_cli.reporting.user_answer import (
    build_user_answer,
    render_user_answer,
    validate_user_answer,
)
from tests.fixtures.result_fixtures import (
    answer_input_from_fixture,
    report_with_required_caveats,
)


class UserAnswerModuleTests(unittest.TestCase):
    def test_build_user_answer_produces_valid_deterministic_output(self) -> None:
        report = report_with_required_caveats()
        answer_input = answer_input_from_fixture(report)
        answer = build_user_answer(answer_input)

        validate_user_answer(answer)
        self.assertEqual(
            answer["schema_version"], current_contract("user_answer")["schema_version"]
        )
        self.assertEqual(
            answer["rendered_text"],
            render_user_answer(answer, answer_input.route),
        )


if __name__ == "__main__":
    unittest.main()
