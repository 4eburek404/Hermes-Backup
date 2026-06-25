import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = ROOT / "scripts" / "audit_skill.py"

spec = importlib.util.spec_from_file_location("audit_skill", AUDIT_SCRIPT)
assert spec is not None
assert spec.loader is not None
audit_skill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_skill)


def make_repo() -> tuple[tempfile.TemporaryDirectory, Path, Path]:
    tmp = tempfile.TemporaryDirectory()
    repo = Path(tmp.name)
    skill_dir = repo / "skills" / "software-development" / "secret-skill"
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: secret-skill
description: Use when testing audit redaction.
---

# secret-skill

## Goal
Test redaction.

## Steps
- Audit the fixture.

## Input
A fixture skill.

## Output
A report.

## Check
Secret-like values are redacted.

## Stop
Stop after audit.

## References
- `references/secret.md`
""",
        encoding="utf-8",
    )
    return tmp, repo, skill_dir


class RedactionTests(unittest.TestCase):
    def test_secret_like_values_are_not_emitted_in_report_json(self):
        tmp, repo, skill_dir = make_repo()
        self.addCleanup(tmp.cleanup)
        value = "sk-" + "live-" + "value"
        key_name = "api" + "_key"
        (skill_dir / "references" / "secret.md").write_text(
            f"Example accident: {key_name} = {value}\n",
            encoding="utf-8",
        )

        report = audit_skill.audit_skill_report(skill_dir / "SKILL.md", repo, audit_skill.collect_skill_map(repo))
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertNotIn(value, encoded)
        findings = [item for item in report["findings"] if item.get("rule_id") == "SECRET_LIKE_VALUE"]
        self.assertTrue(findings)
        self.assertTrue(all(item.get("evidence", {}).get("value") == "[REDACTED]" for item in findings))


if __name__ == "__main__":
    unittest.main()
