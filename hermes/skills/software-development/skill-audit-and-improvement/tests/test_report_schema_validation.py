import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = ROOT / "scripts" / "audit_skill.py"
VALIDATE_SCRIPT = ROOT / "scripts" / "validate_audit_report.py"

spec = importlib.util.spec_from_file_location("audit_skill", AUDIT_SCRIPT)
assert spec is not None
assert spec.loader is not None
audit_skill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_skill)

validate_spec = importlib.util.spec_from_file_location("validate_audit_report", VALIDATE_SCRIPT)
assert validate_spec is not None
assert validate_spec.loader is not None
validate_audit_report = importlib.util.module_from_spec(validate_spec)
validate_spec.loader.exec_module(validate_audit_report)


class ReportSchemaValidationTests(unittest.TestCase):
    def minimal_report(self) -> dict:
        return {
            "schema_version": "1.0.0",
            "tool": {"name": "audit_skill", "version": "0.3.0"},
            "repo": {
                "root": None,
                "branch": None,
                "commit": None,
                "dirty": None,
                "changed_files": [],
                "staged_files": [],
                "untracked_files": [],
            },
            "target": {"mode": "single", "skill": "example", "path": "skills/example/SKILL.md"},
            "summary": {"blockers": 0, "warnings": 0, "recommendations": 0, "info": 0},
            "findings": [],
            "checks": [],
            "evidence_manifest": [],
        }

    def assert_cli_validator_accepts(self, report: dict) -> None:
        self.assertIsNone(validate_audit_report.manual_validate(report))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(validate_audit_report.main(["validate_audit_report.py", str(path)]), 0)

    def test_old_report_without_skills_root_remains_valid(self):
        self.assert_cli_validator_accepts(self.minimal_report())

    def test_new_report_with_skills_root_remains_valid(self):
        report = self.minimal_report()
        report["repo"]["skills_root"] = "/repo/hermes/skills"

        self.assert_cli_validator_accepts(report)

    def test_skills_root_may_be_null_for_error_reports(self):
        report = self.minimal_report()
        report["target"] = {"mode": "error", "skill": None, "path": None}
        report["repo"]["skills_root"] = None

        self.assert_cli_validator_accepts(report)

    def test_skills_root_rejects_non_string_non_null_values(self):
        report = self.minimal_report()
        report["repo"]["skills_root"] = 123

        self.assertIn("repo.skills_root", validate_audit_report.manual_validate(report) or "")


if __name__ == "__main__":
    unittest.main()
