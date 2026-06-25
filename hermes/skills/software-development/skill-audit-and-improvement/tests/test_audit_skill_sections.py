import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = ROOT / "scripts" / "audit_skill.py"
SKILL_MD = ROOT / "SKILL.md"

spec = importlib.util.spec_from_file_location("audit_skill", AUDIT_SCRIPT)
assert spec is not None
assert spec.loader is not None
audit_skill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_skill)

CANONICAL_SECTIONS = [
    "## Goal",
    "## Steps",
    "## Input",
    "## Output",
    "## Check",
    "## Stop",
    "## References",
]


def canonical_skill(name: str) -> str:
    sections = "\n\n".join(f"{section}\nFixture content for {section}." for section in CANONICAL_SECTIONS)
    return f"""---
name: {name}
description: Use when testing compact skill section canon.
---

# {name}

{sections}
"""


def legacy_skill(name: str) -> str:
    return f"""---
name: {name}
description: Use when testing legacy section rejection.
---

# {name}

## Overview
Legacy overview.

## When to Use
- Legacy trigger.

Do not use for production.

## Common Pitfalls
1. Legacy pitfall.

## Verification Checklist
- [ ] Legacy check.
"""


def make_repo() -> tuple[tempfile.TemporaryDirectory, Path]:
    tmp = tempfile.TemporaryDirectory()
    repo = Path(tmp.name)
    (repo / "skills" / "software-development").mkdir(parents=True)
    return tmp, repo


def write_skill(repo: Path, name: str, content: str) -> Path:
    skill_dir = repo / "skills" / "software-development" / name
    skill_dir.mkdir(parents=True)
    path = skill_dir / "SKILL.md"
    path.write_text(content, encoding="utf-8")
    return path


class AuditSkillSectionCanonTests(unittest.TestCase):
    def report_for(self, repo: Path, skill_path: Path) -> dict:
        return audit_skill.audit_skill_report(skill_path, repo, audit_skill.collect_skill_map(repo))

    def missing_section_findings(self, report: dict) -> list[dict]:
        return [item for item in report["findings"] if item.get("rule_id") == "MISSING_SECTION"]

    def missing_sections(self, report: dict) -> list[str]:
        return [item["message"].split(": ", 1)[1] for item in self.missing_section_findings(report)]

    def test_compact_skill_canonical_sections_pass_section_audit(self):
        tmp, repo = make_repo()
        self.addCleanup(tmp.cleanup)
        skill_path = write_skill(repo, "compact-skill", canonical_skill("compact-skill"))

        report = self.report_for(repo, skill_path)

        self.assertEqual(self.missing_sections(report), [])

    def test_legacy_only_sections_do_not_satisfy_compact_canon(self):
        tmp, repo = make_repo()
        self.addCleanup(tmp.cleanup)
        skill_path = write_skill(repo, "legacy-skill", legacy_skill("legacy-skill"))

        report = self.report_for(repo, skill_path)

        self.assertCountEqual(self.missing_sections(report), CANONICAL_SECTIONS)
        self.assertFalse(report["ok"])
        self.assertEqual(report["summary"]["blockers"], len(CANONICAL_SECTIONS))
        self.assertTrue(all(item.get("severity") == "blocker" for item in self.missing_section_findings(report)))

    def test_public_entrypoint_is_normal_python_source(self):
        source = AUDIT_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("TOOL_VERSION = \"0.3.0\"", source)
        self.assertIn("REQUIRED_SECTIONS = [", source)
        for section in CANONICAL_SECTIONS:
            self.assertIn(f'    "{section}",', source)
        self.assertNotIn("_audit_skill_impl", source)
        self.assertNotIn("exec(", source)
        self.assertNotIn("_REQUIRED_SECTIONS_BLOCK_RE", source)
        self.assertNotIn("CANONICAL_REQUIRED_SECTIONS", source)

    def test_skill_runbook_uses_hermes_skills_layout_for_audit_helper(self):
        text = SKILL_MD.read_text(encoding="utf-8")

        self.assertIn(
            "python3 hermes/skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --skill <skill-name> --json",
            text,
        )
        self.assertNotIn(
            "python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --skill <skill-name> --json",
            text,
        )


if __name__ == "__main__":
    unittest.main()
