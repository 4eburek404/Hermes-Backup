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

CANONICAL_BODY = """
## Goal
Test support-file regressions.

## Steps
- Audit the fixture.

## Input
A fixture skill.

## Output
A report.

## Check
Findings match expected support-file behavior.

## Stop
Stop after audit.

## References
- `references/notes.md`
"""


def make_repo() -> tuple[tempfile.TemporaryDirectory, Path, Path]:
    tmp = tempfile.TemporaryDirectory()
    repo = Path(tmp.name)
    skill_dir = repo / "skills" / "software-development" / "regression-skill"
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: regression-skill
description: Use when testing audit support-file regressions.
---

# regression-skill
"""
        + CANONICAL_BODY,
        encoding="utf-8",
    )
    return tmp, repo, skill_dir


class AuditSupportRegressionTests(unittest.TestCase):
    def report_for(self, repo: Path, skill_dir: Path) -> dict:
        return audit_skill.audit_skill_report(skill_dir / "SKILL.md", repo, audit_skill.collect_skill_map(repo))

    def finding_codes(self, report: dict) -> list[str]:
        return [item.get("rule_id") for item in report["findings"]]

    def test_markdown_placeholder_links_are_not_broken_links(self):
        tmp, repo, skill_dir = make_repo()
        self.addCleanup(tmp.cleanup)
        (skill_dir / "references" / "notes.md").write_text(
            "Placeholder links: [todo](TODO), [angle](<replace-with-real-url>), [ellipsis](...).\n",
            encoding="utf-8",
        )

        report = self.report_for(repo, skill_dir)

        self.assertNotIn("BROKEN_MARKDOWN_LINK", self.finding_codes(report))

    def test_generated_artifacts_are_blockers(self):
        tmp, repo, skill_dir = make_repo()
        self.addCleanup(tmp.cleanup)
        cache_dir = skill_dir / "scripts" / "__pycache__"
        cache_dir.mkdir(parents=True)
        (cache_dir / "audit.cpython-311.pyc").write_bytes(b"compiled")
        (skill_dir / "references" / "notes.md").write_text("No placeholder links here.\n", encoding="utf-8")

        report = self.report_for(repo, skill_dir)

        generated = [item for item in report["findings"] if item.get("rule_id") == "GENERATED_ARTIFACT"]
        self.assertTrue(generated)
        self.assertTrue(all(item.get("severity") == "blocker" for item in generated))


if __name__ == "__main__":
    unittest.main()
