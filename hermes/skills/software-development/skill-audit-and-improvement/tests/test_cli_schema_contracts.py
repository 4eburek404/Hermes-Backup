import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "references" / "cli-schema-contracts.md"
DOCTOR_SCHEMA = ROOT / "schemas" / "cli-doctor-envelope.v1.schema.json"


class CliSchemaContractReferenceTests(unittest.TestCase):
    def test_consolidated_reference_keeps_advisory_positioning(self):
        text = REF.read_text(encoding="utf-8")

        self.assertIn("advisory", text.lower())
        self.assertIn("explicit future enforcement flag", text)
        self.assertIn("--no-exec", text)
        self.assertIn("--deep-cli", text)
        self.assertIn("repo.skills_root", text)

    def test_doctor_envelope_schema_remains_central_contract(self):
        schema = json.loads(DOCTOR_SCHEMA.read_text(encoding="utf-8"))

        self.assertEqual(schema.get("title"), "Hermes Skill CLI Doctor Envelope v1")
        self.assertEqual(set(schema.get("required", [])), {"ok", "command", "data", "issues"})
        properties = schema.get("properties", {})
        self.assertEqual(properties.get("ok", {}).get("type"), "boolean")
        self.assertEqual(properties.get("command", {}).get("type"), "string")
        self.assertEqual(properties.get("data", {}).get("type"), "object")
        self.assertEqual(properties.get("issues", {}).get("type"), "array")


if __name__ == "__main__":
    unittest.main()
