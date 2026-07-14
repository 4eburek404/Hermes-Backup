from __future__ import annotations

import unittest
import json
from importlib import resources
from urllib.parse import urljoin

from jsonschema import Draft202012Validator

from flights_cli.commands.common import packaged_schema_registry
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
                "user_answer",
                "search_request",
                "search_result",
                "route_trace",
                "search_plan",
                "offer_graph",
            },
        )
        self.assertEqual(
            current_contract("search_result")["schema_version"],
            "flight_search_result.v9",
        )
        self.assertEqual(
            current_contract("route_trace")["schema_version"],
            "flight_route_trace_diagnostic.v4",
        )
        self.assertEqual(
            current_contract("user_answer")["schema_version"],
            "flight_search_user_answer.v11",
        )
        self.assertEqual(
            current_contract("search_result")["status"], "current_public_contract"
        )
        self.assertEqual(
            current_contract("search_plan")["public_path"],
            "data.plan",
        )
        self.assertEqual(
            current_contract("offer_graph")["public_path"],
            "data.decision.offer_graph",
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

    def test_registry_has_unique_ids_resolvable_refs_and_no_orphans(self) -> None:
        root = resources.files("flights_cli.contracts")
        active_resources = {
            current_contract(name)["schema_resource"] for name in CURRENT_CONTRACTS
        }
        packaged_resources = {
            item.name for item in root.iterdir() if item.name.endswith(".schema.json")
        }
        self.assertEqual(packaged_resources, active_resources)
        schemas = [
            json.loads(root.joinpath(name).read_text(encoding="utf-8"))
            for name in sorted(active_resources)
        ]
        schema_ids = [schema["$id"] for schema in schemas]
        self.assertEqual(len(schema_ids), len(set(schema_ids)))
        registry = packaged_schema_registry()

        def references(value: object):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == "$ref" and isinstance(item, str):
                        yield item
                    yield from references(item)
            elif isinstance(value, list):
                for item in value:
                    yield from references(item)

        for schema in schemas:
            Draft202012Validator.check_schema(schema)
            for reference in references(schema):
                if reference.startswith("#"):
                    continue
                resolved = urljoin(schema["$id"], reference)
                self.assertIn(resolved, schema_ids)
                registry.get_or_retrieve(resolved)

    def test_canonical_text_path_is_single_user_answer_path(self) -> None:
        user_answer = current_contract("user_answer")
        self.assertEqual(user_answer["public_path"], "data.answer")
        self.assertEqual(
            user_answer["canonical_text_path"],
            "data.answer.rendered_text",
        )


if __name__ == "__main__":
    unittest.main()
