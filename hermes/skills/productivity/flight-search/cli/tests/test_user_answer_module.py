from __future__ import annotations

import unittest

from flights_cli.contracts.registry import current_contract
from flights_cli.reporting import user_answer
from flights_cli.reporting.user_answer import (
    build_user_answer,
    canonical_user_answer_text,
    validate_user_answer,
)
from tests.test_user_answer_contract import report_with_required_caveats


class UserAnswerModuleTests(unittest.TestCase):
    def test_user_answer_module_owns_canonical_builder_names(self) -> None:
        report = report_with_required_caveats()

        answer = user_answer.build_user_answer(report)

        user_answer.validate_user_answer(answer)
        self.assertEqual(answer, build_user_answer(report))
        self.assertEqual(answer["schema_version"], current_contract("user_answer")["schema_version"])
        self.assertEqual(
            user_answer.canonical_user_answer_text(report),
            canonical_user_answer_text(report),
        )
        validate_user_answer(answer)


if __name__ == "__main__":
    unittest.main()
