from __future__ import annotations

import unittest
from importlib import resources

from flights_cli.contracts.registry import (
    CURRENT_CONTRACTS,
    DIAGNOSTIC_PROJECTIONS,
    REJECTED_CONTRACT_NAMES,
    current_contract,
)


class ContractRegistryTest(unittest.TestCase):
    def test_registry_declares_current_and_planned_contracts(self) -> None:
        self.assertEqual(
            set(CURRENT_CONTRACTS),
            {"agent_report", "user_answer", "search_request", "search_result"},
        )
        self.assertEqual(
            current_contract("agent_report")["schema_version"], "agent_report.v2"
        )
        self.assertEqual(
            current_contract("user_answer")["schema_version"],
            "flight_search_user_answer.v3",
        )
        self.assertEqual(
            current_contract("search_request")["status"], "planned_new_root_input"
        )
        self.assertEqual(
            current_contract("search_result")["status"], "planned_new_root_output"
        )

    def test_current_schema_resources_are_packaged(self) -> None:
        for name in ("agent_report", "user_answer"):
            contract = current_contract(name)
            resource = contract["schema_resource"]
            self.assertTrue(
                resources.files("flights_cli.contracts").joinpath(resource).is_file()
            )

    def test_canonical_text_path_is_single_user_answer_path(self) -> None:
        user_answer = current_contract("user_answer")
        self.assertEqual(user_answer["public_path"], "data.agent_report.user_answer")
        self.assertEqual(
            user_answer["canonical_text_path"],
            "data.agent_report.user_answer.rendered_text",
        )

    def test_rejected_final_answer_names_are_not_registered(self) -> None:
        self.assertNotIn("final_answer", CURRENT_CONTRACTS)
        self.assertNotIn("user_output", CURRENT_CONTRACTS)
        self.assertIn("user_output", REJECTED_CONTRACT_NAMES)
        self.assertIn("flight_search_final_answer", REJECTED_CONTRACT_NAMES)

    def test_human_answer_mirror_is_diagnostic_not_canonical(self) -> None:
        projection = DIAGNOSTIC_PROJECTIONS["human_answer_mirror"]
        self.assertEqual(
            projection["path"], "data.agent_report.diagnostics.human_answer"
        )
        self.assertEqual(projection["status"], "diagnostic_mirror_only")
        self.assertEqual(
            projection["must_equal"], "data.agent_report.user_answer.rendered_text"
        )
        self.assertNotEqual(
            projection["path"], current_contract("user_answer")["canonical_text_path"]
        )


if __name__ == "__main__":
    unittest.main()
