from __future__ import annotations

import unittest

from flights_cli.contracts.registry import current_contract
from flights_cli.reporting import user_answer
from flights_cli.reporting.user_answer import (
    build_user_answer,
    validate_user_answer,
)
from tests.fixtures.result_fixtures import (
    answer_input_from_fixture,
    report_with_required_caveats,
)


class UserAnswerModuleTests(unittest.TestCase):
    def test_user_answer_module_owns_canonical_builder_names(self) -> None:
        report = report_with_required_caveats()

        answer_input = answer_input_from_fixture(report)

        answer = user_answer.build_user_answer(answer_input)

        user_answer.validate_user_answer(answer)
        self.assertEqual(answer, build_user_answer(answer_input))
        self.assertEqual(
            answer["schema_version"], current_contract("user_answer")["schema_version"]
        )
        validate_user_answer(answer)

    def test_user_answer_has_one_semantic_validator_and_one_pure_renderer(self) -> None:
        self.assertTrue(callable(user_answer.user_answer_contract_semantic_errors))
        self.assertTrue(callable(user_answer.render_user_answer))


if __name__ == "__main__":
    unittest.main()
