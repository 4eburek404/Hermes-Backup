import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate_audit_report.py"
spec = importlib.util.spec_from_file_location("validate_audit_report", SCRIPT_PATH)
validate_audit_report = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(validate_audit_report)


class ValidateAuditReportCompatibilityTests(unittest.TestCase):
    def test_old_report_finding_without_evidence_remains_valid(self):
        report = {
            "schema_version": "1.0.0",
            "tool": {"name": "audit_skill", "version": "0.2.0"},
            "repo": {"root": None, "dirty": None, "changed_files": [], "staged_files": [], "untracked_files": []},
            "target": {"mode": "single", "skill": "example", "path": "skills/example/SKILL.md"},
            "summary": {"blockers": 0, "warnings": 1, "recommendations": 0, "info": 0},
            "findings": [
                {
                    "rule_id": "OLD_WARNING",
                    "severity": "warning",
                    "category": "compat",
                    "message": "old report shape",
                    "location": {"path": "skills/example/SKILL.md"},
                    "fingerprint": "abc123",
                }
            ],
            "checks": [],
            "evidence_manifest": [],
        }
        self.assertIsNone(validate_audit_report.manual_validate(report))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old_report.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(validate_audit_report.main(["validate_audit_report.py", str(path)]), 0)

    def test_step2a_command_evidence_without_envelope_remains_valid(self):
        report = {
            "schema_version": "1.0.0",
            "tool": {"name": "audit_skill", "version": "0.3.0"},
            "repo": {"root": None, "dirty": None, "changed_files": [], "staged_files": [], "untracked_files": []},
            "target": {"mode": "single", "skill": "example", "path": "skills/example/SKILL.md"},
            "summary": {"blockers": 0, "warnings": 0, "recommendations": 0, "info": 0},
            "findings": [],
            "checks": {
                "cli_contract": {
                    "status": "pass",
                    "mode": "advisory",
                    "enforced": False,
                    "execution_performed": True,
                    "doctor_check": {"status": "pass", "commands_attempted": 1, "json_parsed": True},
                }
            },
            "evidence_manifest": [
                {
                    "id": "ev_cli_doctor_001",
                    "kind": "command",
                    "check": "cli_doctor",
                    "status": "pass",
                    "argv": ["python3", "-m", "example", "--json", "doctor"],
                    "cwd": "cli",
                    "exit_code": 0,
                    "duration_ms": 1,
                    "timeout_sec": 10,
                    "stdout_sha256": "abc",
                    "stderr_sha256": "def",
                    "stdout_preview": "{}",
                    "stderr_preview": "",
                    "stdout_truncated": False,
                    "stderr_truncated": False,
                    "parsed_json": True,
                    "json_parse_error": None,
                    "env_policy": "sanitized_minimal",
                    "mutation_policy": "deny",
                    "network_policy": "not_allowed_or_unknown",
                    "execution_performed": True,
                }
            ],
        }
        self.assertIsNone(validate_audit_report.manual_validate(report))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "step2a_report.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(validate_audit_report.main(["validate_audit_report.py", str(path)]), 0)


if __name__ == "__main__":
    unittest.main()
