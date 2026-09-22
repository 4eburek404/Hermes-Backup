#!/usr/bin/env python3
"""Behavioral migration checks for the github-code-review eval consumer."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from evals.harness.core import Harness


REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_ROOT = REPO_ROOT / "evals" / "github-code-review"


def load_consumer_type():
    module_path = EVAL_ROOT / "consumer.py"
    spec = importlib.util.spec_from_file_location("github_code_review_eval_consumer", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError("unable to load github-code-review eval consumer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.GithubCodeReviewConsumer


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


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

    def manifest(self) -> dict:
        return json.loads((EVAL_ROOT / "manifest.json").read_text(encoding="utf-8"))

    def case(self, manifest: dict, versions: list[str]) -> dict:
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
                    "prompt_version": sha256(EVAL_ROOT / cfg["prompt"]),
                }
            },
            "rules": {scenario: cfg.get("evaluation", {})},
        }

    def test_migrated_consumer_preserves_raw_evidence_contract(self) -> None:
        manifest = self.manifest()
        manifest["skill_versions"] = {
            "candidate": {"source": "working_tree"}
        }
        consumer_type = load_consumer_type()

        with tempfile.TemporaryDirectory(prefix="github-review-consumer-contract-") as temp:
            temp_root = Path(temp)
            consumer = consumer_type(
                EVAL_ROOT,
                REPO_ROOT,
                manifest,
                hermes_command=self.fake_hermes(temp_root),
            )
            batch = Harness(consumer).run(
                self.case(manifest, ["candidate"]),
                temp_root / "batch",
            )
            self.assertEqual(1, len(batch["runs"]))
            run = batch["runs"][0]
            self.assertEqual("COMPLETED", run["execution_status"])

            run_dir = Path(run["evidence_path"]).parent
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
            self.assertEqual("PASS", run["score"]["trajectory"])
            self.assertEqual("UNDEFINED", run["score"]["outcome"])

    def test_baseline_candidate_remain_separate_controlled_runs(self) -> None:
        manifest = self.manifest()
        manifest["skill_versions"] = {
            "baseline": {"source": "working_tree"},
            "candidate": {"source": "working_tree"},
        }
        consumer_type = load_consumer_type()

        with tempfile.TemporaryDirectory(prefix="github-review-compare-contract-") as temp:
            temp_root = Path(temp)
            consumer = consumer_type(
                EVAL_ROOT,
                REPO_ROOT,
                manifest,
                hermes_command=self.fake_hermes(temp_root),
            )
            batch = Harness(consumer).run(
                self.case(manifest, ["baseline", "candidate"]),
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
