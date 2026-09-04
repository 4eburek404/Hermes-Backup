from __future__ import annotations

import unittest
import json
from importlib import resources
from urllib.parse import urljoin

from jsonschema import Draft202012Validator

from flights_cli.contracts.registry import (
    CURRENT_CONTRACTS,
    current_contract,
)
from flights_cli.contracts.validation import packaged_schema_registry


class ContractRegistryTest(unittest.TestCase):
    def test_registry_declares_two_public_contracts_and_two_internal_ones(
        self,
    ) -> None:
        self.assertEqual(
            set(CURRENT_CONTRACTS),
            {
                "search_request",
                "search_result",
                "search_plan",
                "offer_graph",
            },
        )
        self.assertEqual(
            current_contract("search_result")["schema_version"],
            "flight_search_result.v1",
        )
        self.assertEqual(
            current_contract("search_result")["status"], "current_public_contract"
        )
        # Путь в конверте есть только у публичного ответа. План и граф ходят
        # между слоями пайплайна и в конверт не попадают.
        self.assertEqual(
            {
                name
                for name in CURRENT_CONTRACTS
                if "public_path" in current_contract(name)
            },
            {"search_result"},
        )
        for name in ("search_plan", "offer_graph"):
            self.assertEqual(current_contract(name)["status"], "internal_invariant")

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
            for name in sorted(packaged_resources)
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
                resource_id = resolved.split("#", 1)[0]
                self.assertIn(resource_id, schema_ids)
                registry.get_or_retrieve(resource_id)

    def test_canonical_text_path_lives_on_the_result_itself(self) -> None:
        # Обёртки `answer` больше нет: текст лежит рядом с вариантами,
        # а не в отдельной схеме под своей версией.
        result = current_contract("search_result")
        self.assertEqual(result["public_path"], "data")
        self.assertEqual(result["canonical_text_path"], "data.rendered_text")


if __name__ == "__main__":
    unittest.main()
