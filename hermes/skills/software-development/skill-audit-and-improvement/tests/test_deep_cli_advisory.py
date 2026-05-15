import importlib.util
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_skill.py"
VALIDATOR_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate_audit_report.py"
spec = importlib.util.spec_from_file_location("audit_skill", SCRIPT_PATH)
audit_skill = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(audit_skill)


def write_skill(repo: Path, name: str, files: dict[str, str] | None = None, body_extra: str = "") -> Path:
    files = dict(files or {})
    skill_dir = repo / "skills" / "software-development" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    default_skill = f"""---
name: {name}
description: Use when testing advisory CLI execution.
---

# {name}

## Overview
Fixture skill.

## When to Use
- Tests.

Do not use for production.

{body_extra}

## Common Pitfalls
1. None.

## Verification Checklist
- [ ] Checked.
"""
    (skill_dir / "SKILL.md").write_text(files.pop("SKILL.md", default_skill), encoding="utf-8")
    for rel, content in files.items():
        path = skill_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    return skill_dir / "SKILL.md"


def make_module_cli(ok_json: str = '{"ok": true, "command": "doctor", "data": {}, "issues": []}', invalid_json: bool = False) -> dict[str, str]:
    doctor_output = "not-json" if invalid_json else ok_json
    return {
        "cli/fixture_cli/__init__.py": "",
        "cli/fixture_cli/__main__.py": f'''
            import argparse
            import sys

            def main(argv=None):
                parser = argparse.ArgumentParser(prog="fixture-cli")
                parser.add_argument("--json", action="store_true")
                parser.add_argument("command", nargs="?")
                args = parser.parse_args(argv)
                if args.command == "doctor":
                    print({doctor_output!r})
                    return 0
                return 0

            if __name__ == "__main__":
                raise SystemExit(main())
        ''',
        "cli/pyproject.toml": '''
            [project]
            name = "fixture-cli"

            [project.scripts]
            fixture-cli = "fixture_cli.__main__:main"
        ''',
    }


class DeepCliAdvisoryTests(unittest.TestCase):
    def make_repo(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Path(tmp.name)
        (repo / "skills").mkdir()
        return repo

    def report_for(self, repo: Path, skill_path: Path, **kwargs) -> dict:
        return audit_skill.audit_skill_report(skill_path, repo, audit_skill.collect_skill_map(repo), **kwargs)

    def command_evidence(self, report: dict, check: str | None = None) -> list[dict]:
        entries = [item for item in report["evidence_manifest"] if item.get("kind") == "command"]
        if check:
            entries = [item for item in entries if item.get("check") == check]
        return entries

    def test_no_deep_cli_keeps_static_mode(self):
        repo = self.make_repo()
        skill_path = write_skill(repo, "static-mode", make_module_cli())

        report = self.report_for(repo, skill_path)

        cli_contract = report["checks"]["cli_contract"]
        self.assertEqual(cli_contract["mode"], "static")
        self.assertFalse(cli_contract["execution_performed"])
        self.assertFalse(self.command_evidence(report))

    def test_deep_cli_no_cli_skill(self):
        repo = self.make_repo()
        skill_path = write_skill(repo, "no-cli", {})

        report = self.report_for(repo, skill_path, deep_cli=True)

        self.assertEqual(report["checks"]["cli_contract"]["status"], "not_applicable")
        self.assertEqual(report["checks"]["cli_contract"]["mode"], "advisory")
        self.assertFalse(self.command_evidence(report))

    def test_deep_cli_does_not_execute_nonlocal_documented_modules(self):
        repo = self.make_repo()
        skill_path = write_skill(
            repo,
            "nonlocal-doc-module",
            make_module_cli(),
            body_extra="Examples mention `python3 -m pip --help` and `python3 -m py_compile --help`, but only local CLI modules are executable audit candidates.",
        )

        report = self.report_for(repo, skill_path, deep_cli=True)

        argv_strings = [" ".join(item["argv"]) for item in self.command_evidence(report)]
        self.assertFalse(any("python3 -m pip" in argv for argv in argv_strings))
        self.assertFalse(any("python3 -m py_compile" in argv for argv in argv_strings))
        self.assertTrue(any("python3 -m fixture_cli" in argv for argv in argv_strings))

    def test_high_confidence_entrypoints_excludes_medium_confidence(self):
        inventory = {
            "entrypoints": [
                {"kind": "python_module", "module": "medium_cli", "confidence": "medium"},
                {"kind": "python_module", "module": "high_cli", "confidence": "high"},
            ]
        }

        entries = audit_skill.high_confidence_entrypoints(inventory)

        self.assertEqual([entry["module"] for entry in entries], ["high_cli"])

    def test_deep_cli_help_success(self):
        repo = self.make_repo()
        skill_path = write_skill(repo, "help-success", make_module_cli())

        report = self.report_for(repo, skill_path, deep_cli=True)

        cli_contract = report["checks"]["cli_contract"]
        help_entries = self.command_evidence(report, "cli_help")
        self.assertEqual(cli_contract["mode"], "advisory")
        self.assertFalse(cli_contract["enforced"])
        self.assertTrue(cli_contract["execution_performed"])
        self.assertTrue(help_entries)
        self.assertTrue(all(item["execution_performed"] for item in help_entries))
        self.assertEqual(cli_contract["help_check"]["status"], "pass")

    def test_deep_cli_doctor_json_success(self):
        repo = self.make_repo()
        skill_path = write_skill(repo, "doctor-json", make_module_cli(), body_extra="Run `python3 -m fixture_cli --json doctor`.")

        report = self.report_for(repo, skill_path, deep_cli=True)

        doctor_entries = self.command_evidence(report, "cli_doctor")
        self.assertEqual(report["checks"]["cli_contract"]["doctor_check"]["status"], "pass")
        self.assertTrue(doctor_entries)
        self.assertTrue(doctor_entries[0]["parsed_json"])
        self.assertTrue(doctor_entries[0]["doctor_json_ok_field"])
        self.assertEqual(doctor_entries[0]["doctor_json_command_field"], "doctor")

    def test_deep_cli_doctor_json_parse_uses_full_stdout_before_truncation(self):
        repo = self.make_repo()
        skill_path = write_skill(repo, "doctor-json-truncated", make_module_cli(ok_json='{"ok": true, "command": "doctor", "data": {"details": "abcdefghijklmnopqrstuvwxyz"}, "issues": []}'), body_extra="Run `python3 -m fixture_cli --json doctor`.")

        report = self.report_for(repo, skill_path, deep_cli=True, max_output_bytes=8)

        doctor_entries = self.command_evidence(report, "cli_doctor")
        self.assertTrue(doctor_entries)
        self.assertTrue(doctor_entries[0]["stdout_truncated"])
        self.assertTrue(doctor_entries[0]["parsed_json"])
        self.assertIsNone(doctor_entries[0]["json_parse_error"])
        self.assertEqual(report["checks"]["cli_contract"]["doctor_check"]["status"], "pass")

    def test_deep_cli_doctor_invalid_json_advisory_warning(self):
        repo = self.make_repo()
        skill_path = write_skill(repo, "doctor-invalid-json", make_module_cli(invalid_json=True), body_extra="Run `python3 -m fixture_cli --json doctor`.")

        report = self.report_for(repo, skill_path, deep_cli=True)

        self.assertEqual(report["checks"]["cli_contract"]["doctor_check"]["status"], "warn")
        doctor_entries = self.command_evidence(report, "cli_doctor")
        self.assertTrue(doctor_entries)
        self.assertFalse(doctor_entries[0]["envelope_validation"]["performed"])
        self.assertEqual(doctor_entries[0]["envelope_validation"]["skipped_reason"], "stdout did not parse as JSON")
        self.assertTrue(any(item["rule_id"] == "CLI_DOCTOR_JSON_PARSE_FAILED" and item["severity"] == "warning" for item in report["findings"]))
        self.assertEqual(audit_skill.determine_exit_code(report), 0)

    def test_valid_doctor_envelope_passes(self):
        result = audit_skill.validate_cli_doctor_envelope({"ok": True, "command": "doctor", "data": {}, "issues": []})

        self.assertTrue(result["performed"])
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["missing_required_fields"], [])
        self.assertEqual(result["field_type_errors"], [])
        self.assertIs(result["ok_value"], True)
        self.assertEqual(result["issues_count"], 0)

    def test_missing_required_fields_warns(self):
        repo = self.make_repo()
        skill_path = write_skill(repo, "doctor-missing-fields", make_module_cli(ok_json='{"ok": true}'), body_extra="Run `python3 -m fixture_cli --json doctor`.")

        report = self.report_for(repo, skill_path, deep_cli=True)

        doctor = self.command_evidence(report, "cli_doctor")[0]
        validation = doctor["envelope_validation"]
        self.assertEqual(validation["status"], "warn")
        self.assertIn("command", validation["missing_required_fields"])
        self.assertIn("data", validation["missing_required_fields"])
        self.assertIn("issues", validation["missing_required_fields"])
        self.assertTrue(any(item["rule_id"] == "CLI_DOCTOR_ENVELOPE_MISSING_REQUIRED_FIELD" and item["severity"] == "warning" for item in report["findings"]))
        self.assertEqual(audit_skill.determine_exit_code(report), 0)

    def test_invalid_field_types_warn(self):
        payload = {"ok": "true", "command": 123, "data": {}, "issues": {}}
        repo = self.make_repo()
        skill_path = write_skill(repo, "doctor-invalid-types", make_module_cli(ok_json=json.dumps(payload)), body_extra="Run `python3 -m fixture_cli --json doctor`.")

        report = self.report_for(repo, skill_path, deep_cli=True)

        validation = self.command_evidence(report, "cli_doctor")[0]["envelope_validation"]
        self.assertEqual(validation["status"], "warn")
        fields = {item["field"] for item in validation["field_type_errors"]}
        self.assertGreaterEqual(fields, {"ok", "command", "issues"})
        self.assertTrue(any(item["rule_id"] == "CLI_DOCTOR_ENVELOPE_FIELD_TYPE_INVALID" and item["severity"] == "warning" for item in report["findings"]))
        self.assertEqual(audit_skill.determine_exit_code(report), 0)

    def test_json_root_array_warns(self):
        repo = self.make_repo()
        skill_path = write_skill(repo, "doctor-root-array", make_module_cli(ok_json="[]"), body_extra="Run `python3 -m fixture_cli --json doctor`.")

        report = self.report_for(repo, skill_path, deep_cli=True)

        doctor = self.command_evidence(report, "cli_doctor")[0]
        self.assertEqual(doctor["json_root_type"], "array")
        self.assertEqual(doctor["envelope_validation"]["status"], "warn")
        self.assertTrue(any(item["rule_id"] == "CLI_DOCTOR_JSON_ROOT_NOT_OBJECT" and item["severity"] == "warning" for item in report["findings"]))
        self.assertEqual(audit_skill.determine_exit_code(report), 0)

    def test_ok_false_valid_shape_nonblocking(self):
        payload = {"ok": False, "command": "doctor", "data": {}, "issues": [{"severity": "warning", "message": "x"}]}
        repo = self.make_repo()
        skill_path = write_skill(repo, "doctor-not-ok", make_module_cli(ok_json=json.dumps(payload)), body_extra="Run `python3 -m fixture_cli --json doctor`.")

        report = self.report_for(repo, skill_path, deep_cli=True)

        validation = self.command_evidence(report, "cli_doctor")[0]["envelope_validation"]
        self.assertEqual(validation["status"], "pass")
        self.assertIs(validation["ok_value"], False)
        self.assertEqual(report["checks"]["cli_contract"]["doctor_check"]["status"], "warn")
        self.assertTrue(any(item["rule_id"] == "CLI_DOCTOR_REPORTED_NOT_OK" for item in report["findings"]))
        self.assertEqual(audit_skill.determine_exit_code(report), 0)

    def test_deep_cli_doctor_valid_envelope_report_schema_valid(self):
        repo = self.make_repo()
        subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        skill_path = write_skill(repo, "schema-valid-envelope", make_module_cli(), body_extra="Run `python3 -m fixture_cli --json doctor`.")
        report_path = repo.parent / "valid-envelope-report.json"

        completed = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--repo", str(repo), "--path", str(skill_path.parent.relative_to(repo)), "--deep-cli", "--json", "--output", str(report_path)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        validation = subprocess.run([sys.executable, str(VALIDATOR_PATH), str(report_path)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(validation.returncode, 0, validation.stderr + validation.stdout)

    def test_deep_cli_doctor_invalid_envelope_report_schema_valid(self):
        repo = self.make_repo()
        subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        skill_path = write_skill(repo, "schema-invalid-envelope", make_module_cli(ok_json='{"ok": true}'), body_extra="Run `python3 -m fixture_cli --json doctor`.")
        report_path = repo.parent / "invalid-envelope-report.json"

        completed = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--repo", str(repo), "--path", str(skill_path.parent.relative_to(repo)), "--deep-cli", "--json", "--output", str(report_path)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["rule_id"] == "CLI_DOCTOR_ENVELOPE_MISSING_REQUIRED_FIELD" for item in report["findings"]))
        validation = subprocess.run([sys.executable, str(VALIDATOR_PATH), str(report_path)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(validation.returncode, 0, validation.stderr + validation.stdout)

    def test_evidence_preview_redacts_secret_like_output(self):
        repo = self.make_repo()
        secret_value = "TOKEN" + "_VALUE"
        api_key_name = "api" + "_key"
        password_name = "pass" + "word"
        files = make_module_cli()
        files["cli/fixture_cli/__main__.py"] = f'''
            import sys

            def main(argv=None):
                argv = list(argv or sys.argv[1:])
                if "--help" in argv:
                    print("{{}}={{}}".format({api_key_name!r}, {secret_value!r}))
                    print("{{}}={{}}".format({password_name!r}, {secret_value!r}))
                    return 0
                if argv == ["--json", "doctor"]:
                    print('{{"ok": true, "command": "doctor", "data": {{}}, "issues": []}}')
                    return 0
                return 0

            if __name__ == "__main__":
                raise SystemExit(main())
        '''
        skill_path = write_skill(repo, "redacts-output", files, body_extra="Run `python3 -m fixture_cli --json doctor`.")

        report = self.report_for(repo, skill_path, deep_cli=True)

        help_ev = self.command_evidence(report, "cli_help")[0]
        self.assertNotIn(secret_value, help_ev["stdout_preview"])
        self.assertIn("[REDACTED]", help_ev["stdout_preview"])
        self.assertTrue(help_ev["output_redaction_applied"])
        self.assertIn("stdout_sha256", help_ev)

    def test_deep_cli_blocks_mutating_candidate(self):
        repo = self.make_repo()
        skill_path = write_skill(repo, "blocks-mutation", {
            "cli/danger_cli.py": '''
                import argparse
                parser = argparse.ArgumentParser()
                parser.add_argument("--apply", action="store_true")
                parser.parse_args()
            ''',
        }, body_extra="Run `python3 cli/danger_cli.py --apply`.")

        report = self.report_for(repo, skill_path, deep_cli=True)

        blocked = [item for item in self.command_evidence(report) if item.get("status") == "blocked"]
        self.assertTrue(blocked)
        self.assertEqual(blocked[0]["blocked_reason"], "mutation_or_side_effect_risk")
        self.assertFalse(blocked[0]["execution_performed"])

    def test_mutating_policy_blocks_equals_flags_and_verbs(self):
        unsafe_argvs = [
            ["tool", "--delete=true"],
            ["tool", "--force=yes"],
            ["tool", "--write=/tmp/output"],
            ["tool", "--deploy=prod"],
            ["python3", "-m", "fixture_cli", "deploy"],
            ["python3", "-m", "fixture_cli", "install"],
            ["python3", "-m", "fixture_cli", "remove"],
            ["python3", "-m", "fixture_cli", "unlink"],
        ]

        for argv in unsafe_argvs:
            with self.subTest(argv=argv):
                self.assertEqual(audit_skill.command_blocked_reason(argv), "mutation_or_side_effect_risk")

    def test_blocked_command_evidence_redacts_secret_argv(self):
        repo = self.make_repo()
        secret_value = "TOKEN" + "_VALUE"
        token_flag = "--" + "token"
        password_flag = "--" + "password"
        auth_flag = "--" + "authorization"
        bearer_word = "Bear" + "er"
        skill_path = write_skill(
            repo,
            "blocked-redacts-argv",
            make_module_cli(),
            body_extra=f"Run `danger --delete=true {token_flag}={secret_value} {password_flag} {secret_value} {auth_flag} {bearer_word} {secret_value}`.",
        )

        report = self.report_for(repo, skill_path, deep_cli=True)

        blocked = [item for item in self.command_evidence(report) if item.get("status") == "blocked"]
        self.assertTrue(blocked)
        serialized = json.dumps(blocked, sort_keys=True)
        self.assertNotIn(secret_value, serialized)
        self.assertIn("[REDACTED]", serialized)

    def test_no_exec_overrides_deep_cli(self):
        repo = self.make_repo()
        skill_path = write_skill(repo, "no-exec", make_module_cli())

        report = self.report_for(repo, skill_path, deep_cli=True, no_exec=True)

        cli_contract = report["checks"]["cli_contract"]
        self.assertFalse(cli_contract["execution_performed"])
        self.assertIn("--no-exec", cli_contract["skipped_executable_checks_reason"])
        self.assertFalse(self.command_evidence(report))

    def test_run_cli_tests_requires_explicit_flag(self):
        repo = self.make_repo()
        files = make_module_cli()
        files["cli/tests/test_smoke.py"] = '''
            import unittest

            class SmokeTest(unittest.TestCase):
                def test_truth(self):
                    self.assertTrue(True)
        '''
        skill_path = write_skill(repo, "cli-tests", files)

        skipped = self.report_for(repo, skill_path, deep_cli=True)
        self.assertEqual(skipped["checks"]["cli_contract"]["tests_check"]["status"], "skipped")
        self.assertFalse(self.command_evidence(skipped, "cli_tests"))

        run = self.report_for(repo, skill_path, deep_cli=True, run_cli_tests=True)
        self.assertEqual(run["checks"]["cli_contract"]["tests_check"]["status"], "pass")
        self.assertTrue(self.command_evidence(run, "cli_tests"))

    def test_report_schema_validates_new_advisory_report(self):
        repo = self.make_repo()
        subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        skill_path = write_skill(repo, "schema-valid", make_module_cli(), body_extra="Run `python3 -m fixture_cli --json doctor`.")
        report_path = repo.parent / "report.json"

        completed = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--repo", str(repo), "--path", str(skill_path.parent.relative_to(repo)), "--deep-cli", "--json", "--output", str(report_path)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        validation = subprocess.run([sys.executable, str(VALIDATOR_PATH), str(report_path)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(validation.returncode, 0, validation.stderr + validation.stdout)


if __name__ == "__main__":
    unittest.main()
