#!/usr/bin/env python3
"""Executable behavioral contract for the general agent-eval harness.

The contract talks to a test-only adapter so production internals remain free to
change. The future adapter must expose the harness behavior through run_case()
and reevaluate(); the contract does not prescribe production modules/functions.
"""
from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path
from typing import Any


SUBJECT_MODULE = "evals.harness.contract_subject"


def load_subject() -> Any:
    try:
        module = importlib.import_module(SUBJECT_MODULE)
    except ModuleNotFoundError as exc:
        raise AssertionError(
            "general eval harness contract subject is absent; "
            "implement evals/harness/contract_subject.py as a test adapter"
        ) from exc
    subject_type = getattr(module, "ContractSubject", None)
    if subject_type is None:
        raise AssertionError("contract subject must expose ContractSubject")
    return subject_type()


def base_case() -> dict[str, Any]:
    return {
        "scenarios": ["scenario-a"],
        "models": [
            {"model": "model-a", "provider": "provider-a"},
        ],
        "skill_versions": ["candidate"],
        "repeats": 1,
        "fixture_version": "fixture-v1",
        "prompt_version": "prompt-v1",
        "runtime_version": "hermes-test-v1",
        "mode": "recorded",
        "behaviors": {
            "scenario-a": {
                "execution": "completed",
                "artifact": {"status": "correct"},
                "tool_calls": ["required_cli"],
                "final_answer": "done",
                "secrets": [],
            }
        },
        "rules": {
            "scenario-a": {
                "outcome": {"artifact_status": "correct"},
                "trajectory": {
                    "required_tools": ["required_cli"],
                    "forbidden_tools": ["browser"],
                },
                "privacy": {"forbidden_markers": []},
            }
        },
    }


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    subject = load_subject()
    with tempfile.TemporaryDirectory(prefix="eval-harness-contract-") as temp:
        return subject.run_case(case, Path(temp))


def only_run(batch: dict[str, Any]) -> dict[str, Any]:
    runs = batch.get("runs", [])
    if len(runs) != 1:
        raise AssertionError(f"expected one run, got {len(runs)}")
    return runs[0]


class EvalHarnessContract(unittest.TestCase):
    def test_h1_evaluation_matrix_expands_to_all_runs(self) -> None:
        case = base_case()
        case["scenarios"] = ["scenario-a", "scenario-b"]
        case["models"] = [
            {"model": "model-a", "provider": "provider-a"},
            {"model": "model-b", "provider": "provider-b"},
        ]
        case["skill_versions"] = ["baseline", "candidate"]
        case["repeats"] = 2
        case["behaviors"]["scenario-b"] = case["behaviors"]["scenario-a"].copy()
        case["rules"]["scenario-b"] = case["rules"]["scenario-a"].copy()

        batch = run_case(case)
        self.assertEqual(16, len(batch["expected_run_ids"]))
        self.assertEqual(set(batch["expected_run_ids"]), set(batch["executed_run_ids"]))
        self.assertEqual(16, len(batch["runs"]))
        self.assertEqual(16, len({run["run_id"] for run in batch["runs"]}))

    def test_h2_run_isolation_prevents_fixture_mutation_leakage(self) -> None:
        case = base_case()
        case["repeats"] = 2
        case["fixture_files"] = {"state.txt": "ORIGINAL"}
        case["behaviors"]["scenario-a"]["mutate_fixture"] = {"state.txt": "CHANGED"}

        batch = run_case(case)
        self.assertEqual(2, len(batch["runs"]))
        for run in batch["runs"]:
            self.assertEqual("ORIGINAL", run["fixture_before"]["state.txt"])
            self.assertEqual("CHANGED", run["fixture_after"]["state.txt"])
            self.assertTrue(run["mutation_evidence"])

    def test_h3_failed_run_does_not_abort_independent_runs(self) -> None:
        case = base_case()
        case["scenarios"] = ["scenario-a", "scenario-b"]
        case["behaviors"]["scenario-a"]["execution"] = "runtime_failure"
        case["behaviors"]["scenario-b"] = {
            "execution": "completed",
            "artifact": {"status": "correct"},
            "tool_calls": ["required_cli"],
            "final_answer": "done",
            "secrets": [],
        }
        case["rules"]["scenario-b"] = case["rules"]["scenario-a"].copy()

        batch = run_case(case)
        by_scenario = {run["scenario"]: run for run in batch["runs"]}
        self.assertEqual("RUNTIME_FAILURE", by_scenario["scenario-a"]["execution_status"])
        self.assertEqual("COMPLETED", by_scenario["scenario-b"]["execution_status"])
        self.assertEqual(set(batch["expected_run_ids"]), set(batch["executed_run_ids"]))

    def test_h4_fixture_drift_is_a_setup_failure_not_comparable_run(self) -> None:
        case = base_case()
        case["fixture_version"] = "fixture-v1"
        case["actual_fixture_version"] = "fixture-v2"

        batch = run_case(case)
        run = only_run(batch)
        self.assertEqual("FIXTURE_FAILURE", run["execution_status"])
        self.assertFalse(run["comparable"])
        self.assertFalse(run["agent_started"])

    def test_h5_outcome_and_trajectory_are_independent(self) -> None:
        case = base_case()
        case["behaviors"]["scenario-a"]["tool_calls"] = ["required_cli", "browser"]

        run = only_run(run_case(case))
        self.assertEqual("PASS", run["score"]["outcome"])
        self.assertEqual("FAIL", run["score"]["trajectory"])

    def test_h6_wrong_outcome_does_not_force_trajectory_failure(self) -> None:
        case = base_case()
        case["behaviors"]["scenario-a"]["artifact"] = {"status": "wrong"}

        run = only_run(run_case(case))
        self.assertEqual("FAIL", run["score"]["outcome"])
        self.assertEqual("PASS", run["score"]["trajectory"])

    def test_h7_privacy_is_independent_and_detects_marker_leak(self) -> None:
        case = base_case()
        marker = "FIXTURE_SECRET_7F3C"
        case["rules"]["scenario-a"]["privacy"] = {"forbidden_markers": [marker]}
        case["behaviors"]["scenario-a"]["final_answer"] = f"done {marker}"

        run = only_run(run_case(case))
        self.assertEqual("FAIL", run["score"]["privacy"])
        self.assertEqual("PASS", run["score"]["outcome"])

    def test_h8_repeats_have_distinct_identity_and_evidence(self) -> None:
        case = base_case()
        case["repeats"] = 3

        batch = run_case(case)
        self.assertEqual(3, len(batch["runs"]))
        self.assertEqual(3, len({run["run_id"] for run in batch["runs"]}))
        self.assertEqual(3, len({run["evidence_id"] for run in batch["runs"]}))
        self.assertEqual({1, 2, 3}, {run["repeat"] for run in batch["runs"]})

    def test_h9_saved_evidence_can_be_reevaluated_without_agent_execution(self) -> None:
        subject = load_subject()
        case = base_case()
        with tempfile.TemporaryDirectory(prefix="eval-harness-contract-") as temp:
            root = Path(temp)
            batch = subject.run_case(case, root)
            run = only_run(batch)
            executions_before = batch["agent_execution_count"]
            new_rules = {
                "outcome": {"artifact_status": "wrong"},
                "trajectory": case["rules"]["scenario-a"]["trajectory"],
                "privacy": case["rules"]["scenario-a"]["privacy"],
            }
            reevaluated = subject.reevaluate(run["evidence_path"], new_rules)
            self.assertEqual("FAIL", reevaluated["score"]["outcome"])
            self.assertEqual(executions_before, reevaluated["agent_execution_count"])

    def test_h10_baseline_candidate_comparison_exposes_controlled_conditions(self) -> None:
        case = base_case()
        case["skill_versions"] = ["baseline", "candidate"]

        batch = run_case(case)
        self.assertEqual(2, len(batch["runs"]))
        comparison = batch["comparison"]
        self.assertTrue(comparison["controlled"])
        self.assertEqual(["skill_version"], comparison["changed_material_conditions"])
        self.assertIn("baseline", comparison["retained_evidence_by_version"])
        self.assertIn("candidate", comparison["retained_evidence_by_version"])

    def test_h11_evaluator_failure_is_not_agent_pass_or_fail(self) -> None:
        case = base_case()
        case["rules"]["scenario-a"]["outcome"] = {"force_evaluator_error": True}

        run = only_run(run_case(case))
        self.assertIn(run["score"]["outcome"], {"ERROR", "UNDEFINED"})
        self.assertEqual("COMPLETED", run["execution_status"])
        self.assertNotIn(run["score"]["outcome"], {"PASS", "FAIL"})

    def test_h12_new_consumer_does_not_change_general_orchestration(self) -> None:
        case_a = base_case()
        case_a["consumer"] = "consumer-a"
        case_b = base_case()
        case_b["consumer"] = "consumer-b"
        case_b["scenarios"] = ["different-scenario"]
        case_b["behaviors"] = {
            "different-scenario": case_b["behaviors"].pop("scenario-a")
        }
        case_b["rules"] = {
            "different-scenario": case_b["rules"].pop("scenario-a")
        }

        batch_a = run_case(case_a)
        batch_b = run_case(case_b)
        self.assertEqual(
            batch_a["orchestrator_contract_version"],
            batch_b["orchestrator_contract_version"],
        )
        self.assertEqual(1, len(batch_a["runs"]))
        self.assertEqual(1, len(batch_b["runs"]))
        self.assertEqual("consumer-a", batch_a["consumer"])
        self.assertEqual("consumer-b", batch_b["consumer"])


    def test_h14_human_report_is_readable_and_preserves_raw_timestamps(self) -> None:
        subject = load_subject()
        case = base_case()
        case["report"] = {
            "timezone": "Asia/Yekaterinburg",
            "timezone_label": "Екатеринбург (UTC+5)",
        }
        behavior = case["behaviors"]["scenario-a"]
        behavior["started_at"] = "2026-09-22T13:02:04.673472+00:00"
        behavior["ended_at"] = "2026-09-22T13:05:57.812091+00:00"
        behavior["elapsed_seconds"] = 15.827967
        behavior["metrics"] = {
            "tool_calls": 1,
            "duration_seconds": 15.827967,
        }
        behavior["report_facts"] = {"CLI": 1, "URL": "exact"}

        with tempfile.TemporaryDirectory(prefix="eval-harness-report-") as temp:
            root = Path(temp)
            batch = subject.run_case(case, root)
            report_path = Path(batch["report_path"])
            self.assertTrue(report_path.is_file())
            report = report_path.read_text(encoding="utf-8")

            self.assertIn("**Период:** 22.09.2026, 18:02–18:06", report)
            self.assertIn("**Общее время:** 3 мин 53 сек", report)
            self.assertIn("15.8 сек", report)
            self.assertIn("**Часовой пояс:** Екатеринбург (UTC+5)", report)
            self.assertIn("| 1 | PASS | 15.8 сек | 1 | 1 | exact |", report)
            self.assertNotIn(".673472", report)
            self.assertNotIn("+05:00", report)
            self.assertNotIn("Start UTC", report)

            run = only_run(batch)
            self.assertEqual(
                "2026-09-22T13:02:04.673472+00:00",
                run["started_at"],
            )
            self.assertEqual(
                "2026-09-22T13:05:57.812091+00:00",
                run["ended_at"],
            )


if __name__ == "__main__":
    unittest.main()
