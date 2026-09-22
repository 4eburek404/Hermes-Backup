#!/usr/bin/env python3
"""Executable contract for common harness skill sources."""
from __future__ import annotations

import importlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any


SUBJECT_MODULE = "evals.harness.skill_source_contract_subject"
SKILL_PATH = Path("hermes/skills/travel/sample-skill")


def load_subject() -> Any:
    try:
        module = importlib.import_module(SUBJECT_MODULE)
    except ModuleNotFoundError as exc:
        raise AssertionError(
            "skill-source contract subject is absent; implement "
            "evals/harness/skill_source_contract_subject.py as a test adapter"
        ) from exc
    subject_type = getattr(module, "SkillSourceContractSubject", None)
    if subject_type is None:
        raise AssertionError(
            "skill-source contract subject must expose SkillSourceContractSubject"
        )
    return subject_type()


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def make_repo(root: Path) -> Path:
    repo = root / "repo"
    skill = repo / SKILL_PATH
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_text("baseline skill\n", encoding="utf-8")
    (skill / "scripts" / "tool.py").write_text(
        "print('baseline')\n",
        encoding="utf-8",
    )

    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Eval Contract")
    git(repo, "config", "user.email", "eval@example.invalid")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "baseline")
    git(repo, "branch", "base")

    git(repo, "checkout", "-q", "-b", "candidate")
    (skill / "SKILL.md").write_text("candidate skill\n", encoding="utf-8")
    (skill / "scripts" / "tool.py").write_text(
        "print('candidate')\n",
        encoding="utf-8",
    )
    (skill / "references").mkdir()
    (skill / "references" / "notes.md").write_text(
        "candidate reference\n",
        encoding="utf-8",
    )
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "candidate")
    git(repo, "checkout", "-q", "base")
    return repo


class SkillSourceContract(unittest.TestCase):
    def test_git_ref_materializes_complete_external_skill_without_checkout_change(self) -> None:
        subject = load_subject()
        with tempfile.TemporaryDirectory(prefix="skill-source-contract-") as temp:
            root = Path(temp)
            repo = make_repo(root)
            head_before = git(repo, "rev-parse", "HEAD")
            status_before = git(repo, "status", "--porcelain=v1", "--branch")

            destination = root / "materialized"
            identity = subject.materialize(
                repo,
                SKILL_PATH,
                {"source": "git", "ref": "candidate"},
                destination,
            )

            self.assertEqual(
                "candidate skill\n",
                (destination / "SKILL.md").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                "print('candidate')\n",
                (destination / "scripts" / "tool.py").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                "candidate reference\n",
                (destination / "references" / "notes.md").read_text(encoding="utf-8"),
            )
            self.assertEqual(head_before, git(repo, "rev-parse", "HEAD"))
            self.assertEqual(
                status_before,
                git(repo, "status", "--porcelain=v1", "--branch"),
            )
            self.assertEqual("git", identity["source"])
            self.assertEqual("candidate", identity["requested_ref"])
            self.assertEqual(
                git(repo, "rev-parse", "candidate"),
                identity["resolved_commit"],
            )
            self.assertRegex(identity["content_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(SKILL_PATH.as_posix(), identity["skill_path"])

    def test_working_tree_uses_local_skill_state_and_records_dirty_identity(self) -> None:
        subject = load_subject()
        with tempfile.TemporaryDirectory(prefix="skill-source-contract-") as temp:
            root = Path(temp)
            repo = make_repo(root)
            skill = repo / SKILL_PATH
            (skill / "SKILL.md").write_text(
                "working tree skill\n",
                encoding="utf-8",
            )
            (skill / "local.txt").write_text("uncommitted\n", encoding="utf-8")

            destination = root / "materialized"
            identity = subject.materialize(
                repo,
                SKILL_PATH,
                {"source": "working_tree"},
                destination,
            )

            self.assertEqual(
                "working tree skill\n",
                (destination / "SKILL.md").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                "uncommitted\n",
                (destination / "local.txt").read_text(encoding="utf-8"),
            )
            self.assertEqual("working_tree", identity["source"])
            self.assertEqual(git(repo, "rev-parse", "HEAD"), identity["resolved_commit"])
            self.assertTrue(identity["working_tree_dirty"])
            self.assertRegex(identity["content_sha256"], r"^[0-9a-f]{64}$")

    def test_invalid_git_ref_is_a_source_failure_and_does_not_move_head(self) -> None:
        subject = load_subject()
        with tempfile.TemporaryDirectory(prefix="skill-source-contract-") as temp:
            root = Path(temp)
            repo = make_repo(root)
            head_before = git(repo, "rev-parse", "HEAD")

            with self.assertRaises(Exception):
                subject.materialize(
                    repo,
                    SKILL_PATH,
                    {"source": "git", "ref": "does-not-exist"},
                    root / "materialized",
                )

            self.assertEqual(head_before, git(repo, "rev-parse", "HEAD"))


if __name__ == "__main__":
    unittest.main()
