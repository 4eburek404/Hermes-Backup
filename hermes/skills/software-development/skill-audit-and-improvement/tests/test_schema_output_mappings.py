import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "audit_skill.py"
VALIDATE_SCRIPT = ROOT / "scripts" / "validate_audit_report.py"
spec = importlib.util.spec_from_file_location("audit_skill", SCRIPT_PATH)
audit_skill = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(audit_skill)

validate_spec = importlib.util.spec_from_file_location("validate_audit_report", VALIDATE_SCRIPT)
validate_audit_report = importlib.util.module_from_spec(validate_spec)
assert validate_spec.loader is not None
validate_spec.loader.exec_module(validate_audit_report)


class SchemaOutputMappingTests(unittest.TestCase):
    def make_skill(self, files: dict[str, str]) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        skill_dir = Path(tmp.name)
        for rel, content in files.items():
            path = skill_dir / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return skill_dir

    def schema_items(self, *paths: str) -> list[dict]:
        return [{"path": path, "filename": Path(path).name} for path in paths]

    def make_repo(self, skill_name: str, files: dict[str, str]) -> tuple[Path, Path]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Path(tmp.name)
        (repo / "skills").mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        skill_dir = repo / "skills" / "software-development" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        default_skill = f"""---
name: {skill_name}
description: Use when testing schema output mapping reports.
---

# {skill_name}

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
        return repo, skill_dir

    def run_audit_script(self, repo: Path, skill_dir: Path) -> tuple[dict, Path]:
        report_path = repo.parent / "audit-report.json"
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--repo",
                str(repo),
                "--path",
                str(skill_dir),
                "--json",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertIn(proc.returncode, {0, 1}, proc.stderr)
        report = json.loads(proc.stdout)
        report_path.write_text(proc.stdout, encoding="utf-8")
        return report, report_path

    def assert_report_validates(self, report: dict, report_path: Path) -> None:
        self.assertIsNone(validate_audit_report.manual_validate(report))
        self.assertEqual(validate_audit_report.main(["validate_audit_report.py", str(report_path)]), 0)

    def test_docs_explicit_cli_output_mapping(self):
        schema_path = "cli/pkg/contracts/agent_report.v1.schema.json"
        skill_dir = self.make_skill({
            schema_path: json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}),
            "SKILL.md": "Run `python3 -m flights_cli --json route live-assemble SVX LED --agent-brief`.\n"
            "--agent-brief emits data.agent_report validated against agent_report.v1.schema.json.\n",
        })

        mappings = audit_skill.detect_schema_output_mappings(skill_dir, self.schema_items(schema_path))

        self.assertEqual(len(mappings), 1)
        mapping = mappings[0]
        self.assertEqual(mapping["schema_path"], schema_path)
        self.assertEqual(mapping["mapping_kind"], "docs_explicit")
        self.assertEqual(mapping["confidence"], "high")
        self.assertEqual(mapping["scope"], "cli_output")
        self.assertIn("agent_report", mapping["output_name"])
        self.assertIsNotNone(mapping["command_hint"])
        self.assertTrue(any(ev["path"] == "SKILL.md" for ev in mapping["evidence"]))

    def test_agent_report_docs_cli_output_mapping_wins(self):
        agent_schema_path = "cli/flights_cli/contracts/agent_report.v1.schema.json"
        user_answer_schema_path = "cli/flights_cli/contracts/flight_search_user_answer.v1.schema.json"
        skill_dir = self.make_skill({
            agent_schema_path: json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}),
            user_answer_schema_path: json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}),
            "cli/README.md": (
                "Run `python3 -m flights_cli --json route live-assemble SVX LED --agent-brief`.\n"
                "The --agent-brief emits only data.agent_report validated against agent_report.v1.schema.json.\n"
            ),
            "cli/flights_cli/reporting/final_answer_contract.py": """
USER_ANSWER_SCHEMA_RESOURCE = "flight_search_user_answer.v1.schema.json"

def build_user_answer_contract(agent_report):
    return {"answer": agent_report.get("summary"), "schema_version": "flight_search_user_answer.v1"}

def validate_user_answer_contract(payload):
    return payload
""",
        })

        mappings = audit_skill.detect_schema_output_mappings(
            skill_dir,
            self.schema_items(agent_schema_path, user_answer_schema_path),
        )
        agent_mapping = next(mapping for mapping in mappings if mapping["schema_path"] == agent_schema_path)

        self.assertEqual(agent_mapping["mapping_kind"], "docs_explicit")
        self.assertEqual(agent_mapping["scope"], "cli_output")
        self.assertEqual(agent_mapping["confidence"], "high")
        self.assertIn("data.agent_report", agent_mapping["output_name"])
        self.assertIsNotNone(agent_mapping["command_hint"])
        self.assertIn("--agent-brief", agent_mapping["command_hint"])
        self.assertTrue(any(ev["path"] == "cli/README.md" for ev in agent_mapping["evidence"]))
        self.assertFalse(any(
            ev["path"] == "cli/flights_cli/reporting/final_answer_contract.py"
            for ev in agent_mapping["evidence"]
        ))

    def test_schema_version_prefix_does_not_create_docs_mapping_for_wrong_schema(self):
        schema_path = "cli/flights_cli/contracts/agent_report.v1.schema.json"
        skill_dir = self.make_skill({
            schema_path: json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}),
            "cli/README.md": (
                "Run `python3 -m flights_cli --json route live-assemble SVX LED --agent-brief`.\n"
                "The --agent-brief emits data.agent_report validated against agent_report.v10.schema.json.\n"
            ),
        })

        mappings = audit_skill.detect_schema_output_mappings(skill_dir, self.schema_items(schema_path))

        self.assertEqual(mappings, [])

    def test_agent_report_not_mapped_to_user_answer_builder_by_parameter_name(self):
        schema_path = "cli/flights_cli/contracts/agent_report.v1.schema.json"
        final_answer_path = "cli/flights_cli/reporting/final_answer_contract.py"
        skill_dir = self.make_skill({
            schema_path: json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}),
            final_answer_path: """
def build_user_answer_contract(agent_report):
    title = agent_report.get("summary", {}).get("title")
    return {"title": title}

def validate_user_answer_contract(payload):
    return payload
""",
        })

        mappings = audit_skill.detect_schema_output_mappings(skill_dir, self.schema_items(schema_path))
        high_final_answer_mappings = [
            mapping
            for mapping in mappings
            if mapping["schema_path"] == schema_path
            and mapping["mapping_kind"] == "code_explicit"
            and mapping["confidence"] == "high"
            and mapping["scope"] == "final_answer_contract"
        ]

        self.assertEqual(high_final_answer_mappings, [])
        self.assertFalse(any(
            mapping["schema_path"] == schema_path
            and mapping["confidence"] == "high"
            and any(ev["path"] == final_answer_path for ev in mapping["evidence"])
            for mapping in mappings
        ))

    def test_code_explicit_final_answer_mapping(self):
        schema_path = "cli/pkg/contracts/flight_search_user_answer.v1.schema.json"
        skill_dir = self.make_skill({
            schema_path: json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}),
            "cli/pkg/answer_contract.py": """
USER_ANSWER_SCHEMA_RESOURCE = "flight_search_user_answer.v1.schema.json"
USER_ANSWER_SCHEMA_VERSION = "v1"

def build_user_answer_contract(result):
    return {"schema_version": USER_ANSWER_SCHEMA_VERSION, "answer": result}

def validate_user_answer_contract(payload):
    return payload
""",
        })

        mappings = audit_skill.detect_schema_output_mappings(skill_dir, self.schema_items(schema_path))

        self.assertEqual(len(mappings), 1)
        mapping = mappings[0]
        self.assertEqual(mapping["mapping_kind"], "code_explicit")
        self.assertEqual(mapping["confidence"], "high")
        self.assertEqual(mapping["scope"], "final_answer_contract")
        self.assertIn("user_answer", mapping["output_name"])
        self.assertIsNone(mapping["command_hint"])
        self.assertTrue(any(ev["path"] == "cli/pkg/answer_contract.py" for ev in mapping["evidence"]))

    def test_user_answer_final_answer_mapping_still_detected(self):
        schema_path = "cli/flights_cli/contracts/flight_search_user_answer.v1.schema.json"
        skill_dir = self.make_skill({
            schema_path: json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}),
            "cli/flights_cli/reporting/final_answer_contract.py": """
USER_ANSWER_SCHEMA_RESOURCE = "flight_search_user_answer.v1.schema.json"
USER_ANSWER_SCHEMA_VERSION = "flight_search_user_answer.v1"

def build_user_answer_contract(agent_report):
    return {"schema_version": USER_ANSWER_SCHEMA_VERSION, "answer": agent_report}

def validate_user_answer_contract(payload):
    return payload
""",
        })

        mappings = audit_skill.detect_schema_output_mappings(skill_dir, self.schema_items(schema_path))

        self.assertEqual(len(mappings), 1)
        mapping = mappings[0]
        self.assertEqual(mapping["schema_path"], schema_path)
        self.assertEqual(mapping["mapping_kind"], "code_explicit")
        self.assertEqual(mapping["confidence"], "high")
        self.assertEqual(mapping["scope"], "final_answer_contract")

    def test_generic_agent_report_parameter_is_not_exact_schema_identity(self):
        self.assertFalse(
            audit_skill.has_exact_schema_identity(
                'def build_user_answer_contract(agent_report):\n    return agent_report["summary"]',
                "agent_report.v1.schema.json",
                "agent_report.v1",
            )
        )
        self.assertTrue(
            audit_skill.has_exact_schema_identity(
                'AGENT_REPORT_SCHEMA_RESOURCE = "agent_report.v1.schema.json"',
                "agent_report.v1.schema.json",
                "agent_report.v1",
            )
        )
        self.assertTrue(
            audit_skill.has_exact_schema_identity(
                'AGENT_REPORT_SCHEMA_VERSION = "agent_report.v1"',
                "agent_report.v1.schema.json",
                "agent_report.v1",
            )
        )
        self.assertFalse(
            audit_skill.has_exact_schema_identity(
                'OUTPUT_SCHEMA_VERSION = "output"',
                "output.schema.json",
                "output",
            )
        )
        self.assertTrue(
            audit_skill.has_exact_schema_identity(
                'OUTPUT_SCHEMA_RESOURCE = "output.schema.json"',
                "output.schema.json",
                "output",
            )
        )

    def test_tests_explicit_mapping(self):
        schema_path = "cli/pkg/contracts/agent_report.v1.schema.json"
        skill_dir = self.make_skill({
            schema_path: json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}),
            "tests/test_agent_report_contract.py": """
def test_agent_report_contract():
    schema_file = "agent_report.v1.schema.json"
    payload = build_agent_report_contract({"ok": True})
    assert payload["schema_version"] == "v1"
    validate_agent_report_contract(payload, schema_file)
    assert "agent_report" in payload
""",
        })

        mappings = audit_skill.detect_schema_output_mappings(skill_dir, self.schema_items(schema_path))

        self.assertEqual(len(mappings), 1)
        mapping = mappings[0]
        self.assertIn(mapping["mapping_kind"], {"tests_explicit", "code_explicit"})
        self.assertEqual(mapping["confidence"], "high")
        self.assertTrue(any(ev["path"] == "tests/test_agent_report_contract.py" for ev in mapping["evidence"]))

    def test_report_contract_audit_report_mapping(self):
        schema_path = "schemas/audit-report.schema.json"
        skill_dir = self.make_skill({
            schema_path: json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}),
            "scripts/validate_audit_report.py": "SCHEMA_PATH = Path(__file__).parents[1] / 'schemas' / 'audit-report.schema.json'\n",
            "scripts/audit_skill.py": "parser.add_argument('--json', action='store_true')  # emits audit report\n",
        })

        mappings = audit_skill.detect_schema_output_mappings(skill_dir, self.schema_items(schema_path))

        self.assertEqual(len(mappings), 1)
        mapping = mappings[0]
        self.assertEqual(mapping["mapping_kind"], "report_contract")
        self.assertEqual(mapping["confidence"], "high")
        self.assertEqual(mapping["scope"], "report_contract")
        self.assertTrue(any(ev["path"] == "scripts/validate_audit_report.py" for ev in mapping["evidence"]))

    def test_generic_words_do_not_create_mapping(self):
        schema_path = "cli/pkg/contracts/output.v1.schema.json"
        skill_dir = self.make_skill({
            schema_path: json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}),
            "SKILL.md": "The tool emits JSON. A schema, contract, doctor report, and output may exist later.\n",
        })

        mappings = audit_skill.detect_schema_output_mappings(skill_dir, self.schema_items(schema_path))

        self.assertEqual(mappings, [])

    def test_unversioned_generic_schema_name_does_not_create_docs_mapping(self):
        schema_path = "cli/pkg/contracts/output.schema.json"
        skill_dir = self.make_skill({
            schema_path: json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}),
            "SKILL.md": "The tool emits JSON. A schema, contract, doctor report, and output may exist later.\n",
        })

        mappings = audit_skill.detect_schema_output_mappings(skill_dir, self.schema_items(schema_path))

        self.assertEqual(mappings, [])

    def test_vendor_directory_is_ignored(self):
        schema_path = "cli/pkg/contracts/agent_report.v1.schema.json"
        skill_dir = self.make_skill({
            schema_path: json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}),
            "vendor/third_party/README.md": (
                "The --agent-brief emits data.agent_report "
                "validated against agent_report.v1.schema.json.\n"
            ),
        })

        mappings = audit_skill.detect_schema_output_mappings(skill_dir, self.schema_items(schema_path))

        self.assertFalse(any(
            mapping.get("confidence") == "high" and any(
                ev.get("path", "").startswith("vendor/")
                for ev in mapping.get("evidence", [])
            )
            for mapping in mappings
        ))
        self.assertTrue(all(
            not ev.get("path", "").startswith("vendor/")
            for mapping in mappings
            for ev in mapping.get("evidence", [])
        ))

    def test_no_schema_files_returns_empty(self):
        skill_dir = self.make_skill({"SKILL.md": "No schemas here.\n"})

        mappings = audit_skill.detect_schema_output_mappings(skill_dir, [])

        self.assertEqual(mappings, [])

    def test_evidence_snippets_are_bounded_and_redacted(self):
        schema_path = "cli/pkg/contracts/agent_report.v1.schema.json"
        secret_value = "TOKEN" + "_VALUE" + "_1234567890"
        secret_key = "api" + "_key"
        long_tail = "x" * 500
        skill_dir = self.make_skill({
            schema_path: json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}),
            "SKILL.md": (
                f"--agent-brief emits data.agent_report validated against agent_report.v1.schema.json "
                f"{secret_key}={secret_value} {long_tail}\n"
            ),
        })

        mappings = audit_skill.detect_schema_output_mappings(skill_dir, self.schema_items(schema_path))
        snippets = [ev["snippet"] for mapping in mappings for ev in mapping["evidence"]]

        self.assertTrue(snippets)
        self.assertTrue(all(len(snippet) <= 200 for snippet in snippets))
        self.assertFalse(any(secret_value in snippet for snippet in snippets))
        self.assertTrue(any("[REDACTED]" in snippet for snippet in snippets))

    def test_cli_secret_flag_values_are_redacted_in_mapping_report_fields(self):
        schema_path = "cli/pkg/contracts/agent_report.v1.schema.json"
        secret_value = "TOKEN" + "_VALUE" + "_1234567890"
        skill_dir = self.make_skill({
            schema_path: json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}),
            "SKILL.md": (
                "Run `python3 -m flights_cli --json route --api-key "
                f"{secret_value} --agent-brief`. "
                "The --agent-brief emits data.agent_report validated against agent_report.v1.schema.json.\n"
            ),
        })

        mappings = audit_skill.detect_schema_output_mappings(skill_dir, self.schema_items(schema_path))
        snippets = [ev["snippet"] for mapping in mappings for ev in mapping["evidence"]]
        command_hints = [mapping["command_hint"] for mapping in mappings if mapping.get("command_hint")]

        self.assertTrue(snippets)
        self.assertTrue(command_hints)
        self.assertFalse(any(secret_value in snippet for snippet in snippets))
        self.assertFalse(any(secret_value in hint for hint in command_hints))
        self.assertTrue(any("[REDACTED]" in snippet for snippet in snippets))
        self.assertTrue(any("[REDACTED]" in hint for hint in command_hints))

    def test_report_includes_schema_output_mappings_for_docs_explicit_fixture(self):
        schema_path = "cli/pkg/contracts/agent_report.v1.schema.json"
        repo, skill_dir = self.make_repo("schema-output-docs", {
            "SKILL.md": """---
name: schema-output-docs
description: Use when testing schema output mapping reports.
---

# schema-output-docs

## Overview
Run `python3 -m flights_cli --json route live-assemble SVX LED --agent-brief`.
The --agent-brief emits data.agent_report validated against agent_report.v1.schema.json.

## When to Use
- Tests.

Do not use for production.

## Common Pitfalls
1. None.

## Verification Checklist
- [ ] Checked.
""",
            schema_path: json.dumps({
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "https://example.local/agent_report.v1.schema.json",
                "type": "object",
            }),
        })

        report, report_path = self.run_audit_script(repo, skill_dir)
        mappings = report["checks"]["schema_contract"]["schema_output_mappings"]
        summary = report["checks"]["schema_contract"]["schema_output_mappings_summary"]

        self.assertEqual(len(mappings), 1)
        mapping = mappings[0]
        self.assertEqual(mapping["mapping_kind"], "docs_explicit")
        self.assertEqual(mapping["confidence"], "high")
        self.assertEqual(mapping["scope"], "cli_output")
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["high"], 1)
        self.assertEqual(summary["by_scope"]["cli_output"], 1)
        self.assertTrue(any(item.get("rule_id") == "SCHEMA_OUTPUT_MAPPING_DETECTED" for item in report["findings"]))
        self.assert_report_validates(report, report_path)

    def test_report_has_empty_schema_output_mappings_without_schemas(self):
        repo, skill_dir = self.make_repo("schema-output-none", {})

        report, report_path = self.run_audit_script(repo, skill_dir)
        schema_contract = report["checks"]["schema_contract"]

        self.assertEqual(schema_contract["schema_output_mappings"], [])
        self.assertEqual(schema_contract["schema_output_mappings_summary"]["total"], 0)
        self.assertFalse(any(item.get("rule_id") == "SCHEMA_OUTPUT_MAPPING_DETECTED" for item in report["findings"]))
        self.assert_report_validates(report, report_path)

    def test_old_reports_remain_valid(self):
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
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "old-report.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            self.assert_report_validates(report, report_path)

    def test_mapping_evidence_is_bounded_redacted_in_report(self):
        schema_path = "cli/pkg/contracts/agent_report.v1.schema.json"
        secret_value = "TOKEN" + "_VALUE" + "_1234567890"
        secret_key = "api" + "_key"
        repo, skill_dir = self.make_repo("schema-output-redaction", {
            "SKILL.md": """---
name: schema-output-redaction
description: Use when testing schema output mapping reports.
---

# schema-output-redaction

## Overview
--agent-brief emits data.agent_report validated against agent_report.v1.schema.json SECRET_PLACEHOLDER

## When to Use
- Tests.

Do not use for production.

## Common Pitfalls
1. None.

## Verification Checklist
- [ ] Checked.
""".replace("SECRET_PLACEHOLDER", f"{secret_key}={secret_value} " + "x" * 500),
            schema_path: json.dumps({
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "https://example.local/agent_report.v1.schema.json",
                "type": "object",
            }),
        })

        report, report_path = self.run_audit_script(repo, skill_dir)
        snippets = [
            ev["snippet"]
            for mapping in report["checks"]["schema_contract"]["schema_output_mappings"]
            for ev in mapping["evidence"]
        ]
        self.assertTrue(snippets)
        self.assertTrue(all(len(snippet) <= 200 for snippet in snippets))
        self.assertFalse(any(secret_value in snippet for snippet in snippets))
        self.assertTrue(any("[REDACTED]" in snippet for snippet in snippets))
        self.assert_report_validates(report, report_path)


if __name__ == "__main__":
    unittest.main()
