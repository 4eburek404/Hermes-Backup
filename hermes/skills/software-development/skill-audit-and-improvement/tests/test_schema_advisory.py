import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = ROOT / "scripts" / "audit_skill.py"
VALIDATE_SCRIPT = ROOT / "scripts" / "validate_audit_report.py"

spec = importlib.util.spec_from_file_location("audit_skill", AUDIT_SCRIPT)
audit_skill = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(audit_skill)

validate_spec = importlib.util.spec_from_file_location("validate_audit_report", VALIDATE_SCRIPT)
validate_audit_report = importlib.util.module_from_spec(validate_spec)
assert validate_spec.loader is not None
validate_spec.loader.exec_module(validate_audit_report)


def write_skill(repo: Path, name: str, files: dict[str, str]) -> Path:
    skill_dir = repo / "skills" / "software-development" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    default_skill = f"""---
name: {name}
description: Use when testing advisory schema audit.
---

# {name}

## Overview
Fixture skill.

## When to Use
- Tests.

Do not use for production.

## Common Pitfalls
1. None.

## Verification Checklist
- [ ] Checked.
"""
    (skill_dir / "SKILL.md").write_text(files.pop("SKILL.md", default_skill), encoding="utf-8")
    for rel, content in files.items():
        path = skill_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return skill_dir / "SKILL.md"


class SchemaAdvisoryAuditTests(unittest.TestCase):
    def make_repo(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Path(tmp.name)
        (repo / "skills").mkdir()
        return repo

    def report_for(self, repo: Path, skill_path: Path) -> dict:
        return audit_skill.audit_skill_report(skill_path, repo, audit_skill.collect_skill_map(repo))

    def assert_report_validates(self, report: dict) -> None:
        self.assertIsNone(validate_audit_report.manual_validate(report))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(validate_audit_report.main(["validate_audit_report.py", str(path)]), 0)

    def finding(self, report: dict, code: str):
        return [item for item in report["findings"] if item.get("rule_id") == code]

    def test_schema_file_valid_json_with_dialect_and_id(self):
        repo = self.make_repo()
        schema = json.dumps({
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://example.local/example.v1.schema.json",
            "title": "Example",
            "type": "object",
            "required": ["ok", "items"],
            "properties": {"ok": {"type": "boolean"}, "items": {"type": "array"}},
            "additionalProperties": False,
        })
        skill_path = write_skill(repo, "schema-valid", {
            "cli/pkg/contracts/example.v1.schema.json": schema,
            "cli/pkg/__main__.py": "def main():\n    return 0\n",
        })

        report = self.report_for(repo, skill_path)
        item = report["checks"]["schema_contract"]["schemas"][0]

        self.assertTrue(item["json_valid"])
        self.assertEqual(item["dialect"], "draft2020-12")
        self.assertTrue(item["has_schema_keyword"])
        self.assertTrue(item["has_id_keyword"])
        self.assertEqual(item["version_hint"], "v1")
        self.assertEqual(item["additional_properties_policy"], "closed")
        self.assert_report_validates(report)

    def test_schema_file_invalid_json_warns(self):
        repo = self.make_repo()
        skill_path = write_skill(repo, "schema-invalid", {
            "schemas/broken.schema.json": "{not valid json",
        })

        report = self.report_for(repo, skill_path)

        self.assertTrue(any(item["severity"] == "warning" for item in self.finding(report, "SCHEMA_FILE_INVALID_JSON")))
        self.assertEqual(report["checks"]["schema_contract"]["status"], "warn")
        self.assert_report_validates(report)

    def test_schema_missing_schema_keyword_advisory(self):
        repo = self.make_repo()
        skill_path = write_skill(repo, "schema-missing-dialect", {
            "schemas/example.schema.json": json.dumps({"$id": "example", "type": "object"}),
        })

        report = self.report_for(repo, skill_path)

        self.assertTrue(self.finding(report, "SCHEMA_DIALECT_MISSING"))
        self.assertFalse(any(item["severity"] == "blocker" for item in self.finding(report, "SCHEMA_DIALECT_MISSING")))
        self.assert_report_validates(report)

    def test_schema_missing_id_keyword_advisory(self):
        repo = self.make_repo()
        skill_path = write_skill(repo, "schema-missing-id", {
            "schemas/example.schema.json": json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}),
        })

        report = self.report_for(repo, skill_path)

        self.assertTrue(self.finding(report, "SCHEMA_ID_MISSING"))
        self.assertFalse(any(item["severity"] == "blocker" for item in self.finding(report, "SCHEMA_ID_MISSING")))
        self.assert_report_validates(report)

    def test_schema_decision_not_applicable_for_no_cli_no_json(self):
        repo = self.make_repo()
        skill_path = write_skill(repo, "schema-na", {})

        report = self.report_for(repo, skill_path)

        self.assertEqual(report["checks"]["schema_contract"]["decision"]["level"], "not_applicable")
        self.assertEqual(report["checks"]["schema_contract"]["status"], "not_applicable")
        self.assert_report_validates(report)

    def test_schema_decision_recommended_for_json_claim_no_schema(self):
        repo = self.make_repo()
        skill_path = write_skill(repo, "schema-recommended", {
            "cli/tool.py": "# Supports --json output with ok and issues fields\n",
        })

        report = self.report_for(repo, skill_path)

        self.assertEqual(report["checks"]["schema_contract"]["decision"]["level"], "recommended")
        self.assertTrue(any(item["severity"] == "warning" for item in self.finding(report, "SCHEMA_RECOMMENDED_BUT_MISSING_ADVISORY")))
        self.assert_report_validates(report)

    def test_schema_decision_required_for_machine_consumer_claim(self):
        repo = self.make_repo()
        skill_path = write_skill(repo, "schema-required", {
            "SKILL.md": """---
name: schema-required
description: Use when testing required schema decisions.
---

# schema-required

## Overview
This skill emits an agent report for CI and a golden JSON baseline consumed by another tool.

## When to Use
- Tests.

Do not use for production.

## Common Pitfalls
1. None.

## Verification Checklist
- [ ] Checked.
""",
        })

        report = self.report_for(repo, skill_path)

        self.assertEqual(report["checks"]["schema_contract"]["decision"]["level"], "required")
        self.assertTrue(any(item["severity"] == "warning" for item in self.finding(report, "SCHEMA_REQUIRED_BUT_MISSING_ADVISORY")))
        self.assert_report_validates(report)

    def test_schema_present_but_not_referenced_by_tests(self):
        repo = self.make_repo()
        schema = json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "example", "type": "object", "properties": {"ok": {"type": "boolean"}}})
        skill_path = write_skill(repo, "schema-unreferenced-tests", {
            "SKILL.md": """---
name: schema-unreferenced-tests
description: Use when testing required schema refs.
---

# schema-unreferenced-tests

## Overview
The CLI exposes --json output consumed by a machine consumer in CI.

## When to Use
- Tests.

Do not use for production.

## Common Pitfalls
1. None.

## Verification Checklist
- [ ] Checked.
""",
            "cli/pkg/contracts/example.v1.schema.json": schema,
            "cli/pkg/__main__.py": "def main():\n    return 0\n",
        })

        report = self.report_for(repo, skill_path)

        self.assertTrue(self.finding(report, "SCHEMA_NOT_REFERENCED_BY_TESTS"))
        self.assert_report_validates(report)

    def test_schema_referenced_by_docs_and_tests_detected(self):
        repo = self.make_repo()
        schema = json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "example", "type": "object"})
        skill_path = write_skill(repo, "schema-referenced", {
            "cli/pkg/contracts/example.v1.schema.json": schema,
            "references/contract.md": "Use cli/pkg/contracts/example.v1.schema.json for --json output.\n",
            "tests/test_contract.py": "SCHEMA = 'example.v1.schema.json'\n",
        })

        report = self.report_for(repo, skill_path)
        item = [schema for schema in report["checks"]["schema_contract"]["schemas"] if schema["filename"] == "example.v1.schema.json"][0]

        self.assertTrue(item["referenced_by_docs"])
        self.assertTrue(item["referenced_by_tests"])
        self.assert_report_validates(report)

    def test_schema_too_open_for_required_machine_contract(self):
        repo = self.make_repo()
        schema = json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "example", "type": "object", "properties": {"ok": {"type": "boolean"}}, "additionalProperties": True})
        skill_path = write_skill(repo, "schema-too-open", {
            "SKILL.md": """---
name: schema-too-open
description: Use when testing open schemas.
---

# schema-too-open

## Overview
The CLI produces structured output consumed by another tool and compared to a golden JSON baseline.

## When to Use
- Tests.

Do not use for production.

## Common Pitfalls
1. None.

## Verification Checklist
- [ ] Checked.
""",
            "schemas/example.schema.json": schema,
        })

        report = self.report_for(repo, skill_path)

        self.assertTrue(self.finding(report, "SCHEMA_TOO_OPEN_FOR_MACHINE_CONTRACT"))
        self.assertFalse(any(item["severity"] == "blocker" for item in self.finding(report, "SCHEMA_TOO_OPEN_FOR_MACHINE_CONTRACT")))
        self.assert_report_validates(report)

    def test_old_reports_remain_valid(self):
        report = {
            "schema_version": "1.0.0",
            "tool": {"name": "audit_skill", "version": "0.2.0"},
            "repo": {"root": None, "dirty": None, "changed_files": [], "staged_files": [], "untracked_files": []},
            "target": {"mode": "single", "skill": "example", "path": "skills/example/SKILL.md"},
            "summary": {"blockers": 0, "warnings": 0, "recommendations": 0, "info": 0},
            "findings": [],
            "checks": {"items": [], "cli_contract": {"status": "pass", "mode": "static", "enforced": False, "execution_performed": False}},
            "evidence_manifest": [],
        }
        self.assert_report_validates(report)

    def test_deep_cli_step2b_report_still_valid(self):
        report = {
            "schema_version": "1.0.0",
            "tool": {"name": "audit_skill", "version": "0.3.0"},
            "repo": {"root": None, "dirty": None, "changed_files": [], "staged_files": [], "untracked_files": []},
            "target": {"mode": "single", "skill": "example", "path": "skills/example/SKILL.md"},
            "summary": {"blockers": 0, "warnings": 0, "recommendations": 0, "info": 1},
            "findings": [{"rule_id": "CLI_DOCTOR_ENVELOPE_VALID", "severity": "info", "category": "cli_contract", "message": "valid", "location": {"path": "cli"}, "fingerprint": "abc"}],
            "checks": {
                "cli_contract": {
                    "status": "pass",
                    "mode": "advisory",
                    "enforced": False,
                    "execution_performed": True,
                    "doctor_check": {"status": "pass", "commands_attempted": 1, "json_parsed": True, "envelope_validation": {"performed": True, "status": "pass", "schema_name": "cli-doctor-envelope.v1"}},
                },
                "schema_contract": {"status": "not_applicable", "mode": "static", "enforced": False, "validation_performed": False},
            },
            "evidence_manifest": [],
        }
        self.assert_report_validates(report)


if __name__ == "__main__":
    unittest.main()
