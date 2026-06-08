from __future__ import annotations

import unittest

from flights_cli.contracts.registry import current_contract
from flights_cli.reporting import user_answer
from flights_cli.reporting.final_answer_contract import (
    build_user_answer_contract,
    canonical_rendered_text,
    validate_user_answer_contract,
)
from tests.test_final_answer_contract import report_with_required_caveats


class UserAnswerModuleTests(unittest.TestCase):
    def test_user_answer_module_owns_canonical_builder_names(self) -> None:
        report = report_with_required_caveats()

        answer = user_answer.build_user_answer(report)

        user_answer.validate_user_answer(answer)
        self.assertEqual(answer, build_user_answer_contract(report))
        self.assertEqual(answer["schema_version"], current_contract("user_answer")["schema_version"])
        self.assertEqual(
            user_answer.canonical_user_answer_text(report),
            canonical_rendered_text(report),
        )

    def test_legacy_contract_names_are_compatibility_aliases(self) -> None:
        self.assertIs(user_answer.build_user_answer_contract, user_answer.build_user_answer)
        self.assertIs(user_answer.validate_user_answer_contract, user_answer.validate_user_answer)
        self.assertIs(user_answer.canonical_rendered_text, user_answer.canonical_user_answer_text)
        self.assertIs(build_user_answer_contract, user_answer.build_user_answer)
        self.assertIs(validate_user_answer_contract, user_answer.validate_user_answer)


if __name__ == "__main__":
    unittest.main()
