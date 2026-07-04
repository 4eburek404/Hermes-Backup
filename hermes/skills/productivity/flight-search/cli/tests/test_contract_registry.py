from __future__ import annotations

import unittest
from importlib import resources

from flights_cli.contracts.registry import (
    CURRENT_CONTRACTS,
    current_contract,
)


class ContractRegistryTest(unittest.TestCase):
    def test_registry_declares_current_public_and_route_diagnostic_contracts(
        self,
    ) -> None:
        self.assertEqual(
            set(CURRENT_CONTRACTS),
            {
                "agent_report",
                "user_answer",
                "search_request",
                "search_result",
                "search_plan",
                "offer_graph",
            },
        )
        self.assertEqual(
            current_contract("agent_report")["schema_version"], "agent_report.v4"
        )
        self.assertEqual(
            current_contract("search_result")["schema_version"],
            "flight_search_result.v3",
        )
        self.assertEqual(
            current_contract("user_answer")["schema_version"],
            "flight_search_user_answer.v6",
        )
        self.assertEqual(
            current_contract("search_result")["status"], "current_public_contract"
        )
        self.assertEqual(
            current_contract("search_plan")["public_path"],
            "data.route_result.live_search.diagnostics.search_plan",
        )
        self.assertEqual(
            current_contract("offer_graph")["public_path"],
            "data.route_result.live_search.offer_graph",
        )

    def test_current_schema_resources_are_packaged(self) -> None:
        for name in CURRENT_CONTRACTS:
            contract = current_contract(name)
            resource = contract.get("schema_resource")
            if not resource:
                continue
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


if __name__ == "__main__":
    unittest.main()
