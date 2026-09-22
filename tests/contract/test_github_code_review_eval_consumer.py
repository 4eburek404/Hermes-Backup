#!/usr/bin/env python3
"""Behavioral migration checks for the github-code-review eval consumer."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from evals.harness.core import Harness


SOURCE_REPO = Path(__file__).resolve().parents[2]
CONSUMER_PATH = SOURCE_REPO / "evals" / "github-code-review" / "consumer.py"


def load_consumer_type():
    spec = importlib.util.spec_from_file_location(
        "github_code_review_eval_consumer",
        CONSUMER_PATH,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("unable to load github-code-review eval consumer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.GithubCodeReviewConsumer


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def run(cmd: list[str], *, cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=True)


class GithubCodeReviewEvalConsumerContract(unittest.TestCase):
    def fake_hermes(self, root: Path) -> list[str]:
        script = root / "fake_hermes.py"
        script.write_text(
            """
import json
import sys

if "--version" in sys.argv:
    print("fake-hermes 1.0")
    raise SystemExit(0)

print(json.dumps({
    "type": "tool_use",
    "name": "terminal",
    "input": {"command": "python -m unittest discover -s tests -v"}
}))
print(json.dumps({
    "type": "result",
    "text": "Synthetic review result"
}))
print("synthetic stderr", file=sys.stderr)
""".strip()
            + "\n",
            encoding="utf-8",
        )
        return [sys.executable, str(script)]

    def make_repo(self, root: Path) -> Path:
        repo = root / "repo"
        skill = repo / "hermes" / "skills" / "github" / "github-code-review" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            "---\nname: github-code-review\n---\n# Synthetic review skill\n",
            encoding="utf-8",
        )
        run(["git", "init", "-q"], cwd=repo)
        run(["git", "config", "user.name", "Eval Test"], cwd=repo)
        run(["git", "config", "user.email", "eval@example.invalid"], cwd=repo)
        run(["git", "add", "."], cwd=repo)
        run(["git", "commit", "-q", "-m", "synthetic repo"], cwd=repo)
        return repo

    def make_eval_root(self, root: Path) -> Path:
        eval_root = root / "eval"
        fixture = eval_root / "fixtures" / "scenario-a"
        prompt = eval_root / "prompt"
        fixture.mkdir(parents=True)
        prompt.mkdir(parents=True)
        (fixture / "value.txt").write_text("base\n", encoding="utf-8")
        (fixture / "review.patch").write_text(
            """diff --git a/value.txt b/value.txt
--- a/value.txt
+++ b/value.txt
@@ -1 +1 @@
-base
+review
""",
            encoding="utf-8",
        )
        (prompt / "scenario-a.txt").write_text(
            "Review the synthetic local diff.\n",
            encoding="utf-8",
        )
        return eval_root

    def manifest(self) -> dict:
        return {
            "name": "github-code-review-agent-level-eval",
            "mode": "recorded",
            "skill": {
                "name": "github-code-review",
                "path": "hermes/skills/github/github-code-review/SKILL.md",
            },
            "skill_versions": {
                "candidate": {"source": "working_tree"},
            },
            "execution": {
                "toolsets": ["terminal", "file", "skills"],
                "max_turns": 30,
                "run_budget": 180,
                "yolo": True,
                "source": "eval",
            },
            "scenarios": {
                "scenario-a": {
                    "fixture_base_sha": "pending",
                    "fixture_review_commit_sha": "pending",
                    "patch": "fixtures/scenario-a/review.patch",
                    "prompt": "prompt/scenario-a.txt",
                    "evaluation": {
                        "trajectory": {
                            "forbid_fixture_mutation": True,
                            "forbidden_command_patterns": [
                                r"git\s+checkout\b",
                                r"git\s+reset\b",
                                r"git\s+clean\b",
                                r"git\s+commit\b",
                            ],
                        }
                    },
                }
            },
        }

    def case(self, manifest: dict, eval_root: Path, versions: list[str]) -> dict:
        scenario = "scenario-a"
        cfg = manifest["scenarios"][scenario]
        return {
            "consumer": manifest["name"],
            "scenarios": [scenario],
            "models": [{"model": "fake-model", "provider": "fake-provider"}],
            "skill_versions": versions,
            "repeats": 1,
            "fixture_version": "scenario-specific",
            "prompt_version": "scenario-specific",
            "runtime_version": "fake-hermes 1.0",
            "mode": "recorded",
            "scenario_metadata": {
                scenario: {
                    "fixture_version": (
                        f'{cfg["fixture_base_sha"]}:{cfg["fixture_review_commit_sha"]}'
                    ),
                    "prompt_version": sha256(eval_root / cfg["prompt"]),
                }
            },
            "rules": {scenario: cfg.get("evaluation", {})},
        }

    def make_consumer(
        self,
        temp_root: Path,
        versions: list[str],
    ):
        consumer_type = load_consumer_type()
        repo_root = self.make_repo(temp_root)
        eval_root = self.make_eval_root(temp_root)
        manifest = self.manifest()
        manifest["skill_versions"] = {
            version: {"source": "working_tree"} for version in versions
        }
        consumer = consumer_type(
            eval_root,
            repo_root,
            manifest,
            hermes_command=self.fake_hermes(temp_root),
        )
        fixture_identity = consumer.inspect_fixture("scenario-a")
        manifest["scenarios"]["scenario-a"].update(
            {
                "fixture_base_sha": fixture_identity["base_sha"],
                "fixture_review_commit_sha": fixture_identity["review_commit_sha"],
            }
        )
        return consumer, manifest, eval_root

    def test_migrated_consumer_preserves_raw_evidence_contract(self) -> None:
        with tempfile.TemporaryDirectory(prefix="github-review-consumer-contract-") as temp:
            temp_root = Path(temp)
            consumer, manifest, eval_root = self.make_consumer(
                temp_root,
                ["candidate"],
            )
            batch = Harness(consumer).run(
                self.case(manifest, eval_root, ["candidate"]),
                temp_root / "batch",
            )
            self.assertEqual(1, len(batch["runs"]))
            run_record = batch["runs"][0]
            self.assertEqual("COMPLETED", run_record["execution_status"])

            run_dir = Path(run_record["evidence_path"]).parent
            for name in (
                "prompt.txt",
                "raw_stream.jsonl",
                "raw_stderr.txt",
                "raw_final_answer.txt",
                "metadata.json",
                "evidence.json",
                "score.json",
            ):
                self.assertTrue((run_dir / name).is_file(), name)

            metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
            required_metadata = {
                "scenario",
                "skill_version",
                "skill_sha256",
                "candidate_skill_sha256",
                "baseline_commit",
                "candidate_commit",
                "fixture_base_sha",
                "fixture_review_commit_sha",
                "hermes_executable",
                "hermes_version",
                "model",
                "provider",
                "toolsets",
                "command",
                "started_at",
                "ended_at",
                "elapsed_seconds",
                "exit_code",
                "pre_snapshot",
                "post_snapshot",
                "restored_snapshot",
                "raw_trace_format",
                "atif_atof_files",
                "atif_atof_available",
                "event_summary",
                "mutation_detected",
            }
            self.assertTrue(required_metadata.issubset(metadata))
            self.assertIsInstance(metadata["hermes_executable"], str)
            self.assertEqual("PASS", run_record["score"]["trajectory"])
            self.assertEqual("UNDEFINED", run_record["score"]["outcome"])

    def test_baseline_candidate_remain_separate_controlled_runs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="github-review-compare-contract-") as temp:
            temp_root = Path(temp)
            versions = ["baseline", "candidate"]
            consumer, manifest, eval_root = self.make_consumer(temp_root, versions)
            batch = Harness(consumer).run(
                self.case(manifest, eval_root, versions),
                temp_root / "batch",
            )
            self.assertEqual(2, len(batch["runs"]))
            self.assertTrue(batch["comparison"]["controlled"])
            self.assertEqual(
                ["skill_version"],
                batch["comparison"]["changed_material_conditions"],
            )
            self.assertEqual(
                {"baseline", "candidate"},
                set(batch["comparison"]["retained_evidence_by_version"]),
            )


if __name__ == "__main__":
    unittest.main()
