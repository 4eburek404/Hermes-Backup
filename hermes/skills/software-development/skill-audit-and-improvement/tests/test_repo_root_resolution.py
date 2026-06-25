import importlib.util
import json
import subprocess
import sys
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


COMPACT_SKILL = """---
name: compact-skill
description: Use when testing repository root resolution.
---

# compact-skill

## Goal
Exercise repo root resolution.

## Steps
- Run the audit.

## Input
A fixture skill.

## Output
A JSON report.

## Check
The report resolves this skill.

## Stop
Stop after the fixture is audited.

## References
- `references/example.md`
"""


def init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def write_skill(repo: Path, prefix: tuple[str, ...]) -> Path:
    skill_dir = repo.joinpath(*prefix, "software-development", "compact-skill")
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(COMPACT_SKILL, encoding="utf-8")
    return skill_path


class RepoRootResolutionTests(unittest.TestCase):
    def make_repo(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Path(tmp.name)
        init_git_repo(repo)
        return tmp, repo

    def run_cli(self, repo_arg: Path) -> tuple[int, dict]:
        proc = subprocess.run(
            [sys.executable, str(AUDIT_SCRIPT), "--repo", str(repo_arg), "--skill", "compact-skill", "--json"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        try:
            report = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:  # pragma: no cover - failure aid
            self.fail(f"stdout was not JSON: {exc}\nstdout={proc.stdout}\nstderr={proc.stderr}")
        return proc.returncode, report

    def test_direct_skills_layout_resolves_repo_skills_root(self):
        _, repo = self.make_repo()
        write_skill(repo, ("skills",))

        code, report = self.run_cli(repo)

        self.assertEqual(code, 0, report)
        self.assertEqual(report["repo"]["root"], str(repo.resolve()))
        self.assertEqual(report["repo"]["skills_root"], str((repo / "skills").resolve()))
        self.assertEqual(report["target"]["skill"], "compact-skill")

    def test_hermes_nested_skills_layout_resolves_from_repo_root(self):
        _, repo = self.make_repo()
        write_skill(repo, ("hermes", "skills"))

        code, report = self.run_cli(repo)

        self.assertEqual(code, 0, report)
        self.assertEqual(report["repo"]["root"], str(repo.resolve()))
        self.assertEqual(report["repo"]["skills_root"], str((repo / "hermes" / "skills").resolve()))
        self.assertEqual(report["target"]["skill"], "compact-skill")

    def test_hermes_nested_skills_layout_resolves_from_hermes_subdir_arg(self):
        _, repo = self.make_repo()
        write_skill(repo, ("hermes", "skills"))

        code, report = self.run_cli(repo / "hermes")

        self.assertEqual(code, 0, report)
        self.assertEqual(report["repo"]["root"], str(repo.resolve()))
        self.assertEqual(report["repo"]["skills_root"], str((repo / "hermes" / "skills").resolve()))
        self.assertEqual(report["target"]["skill"], "compact-skill")

    def test_invalid_repo_without_supported_skills_root_keeps_error_envelope(self):
        _, repo = self.make_repo()

        code, report = self.run_cli(repo)

        self.assertEqual(code, 2)
        self.assertEqual(report["error"]["code"], "INVALID_REPO")
        self.assertIn("skills", report["error"]["message"])
        self.assertIsNone(report["repo"].get("skills_root"))


if __name__ == "__main__":
    unittest.main()
