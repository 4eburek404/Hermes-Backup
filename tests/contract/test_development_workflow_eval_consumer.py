from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONSUMER_PATH = ROOT / "evals" / "development-workflow" / "consumer.py"


def load_consumer_module():
    spec = importlib.util.spec_from_file_location("development_workflow_consumer", CONSUMER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def consumer():
    module = load_consumer_module()
    return module.DevelopmentWorkflowConsumer(
        ROOT / "evals" / "development-workflow",
        ROOT,
        manifest={},
        hermes_command=["hermes"],
    )


def grounded_evidence() -> dict:
    return {
        "execution_status": "COMPLETED",
        "behavior_probes": [
            {
                "name": "public-behavior",
                "expected_exit_code": 0,
                "actual_exit_code": 0,
                "expected_stdout": "ok\n",
                "actual_stdout": "ok\n",
            }
        ],
        "test_result": {"exit_code": 0},
        "equivalent_behavior_probes": [
            {
                "name": "public-behavior",
                "expected_exit_code": 0,
                "actual_exit_code": 0,
                "expected_stdout": "ok\n",
                "actual_stdout": "ok\n",
            }
        ],
        "equivalent_test_result": {"exit_code": 0},
        "protected_paths_unchanged": {"notes.txt": True},
        "repository_changed": True,
        "tool_calls": ["python3 -m pytest -q"],
        "skill_views": [{"name": "any-internal-routing-is-diagnostic-only"}],
    }


def test_outcome_is_independent_of_loaded_skill_names() -> None:
    subject = consumer()
    evidence = grounded_evidence()

    first = subject.evaluate_dimension_diagnostic("outcome", evidence, {})
    evidence["skill_views"] = [{"name": "completely-different-routing"}]
    second = subject.evaluate_dimension_diagnostic("outcome", evidence, {})

    assert first["status"] == "PASS"
    assert second["status"] == "PASS"


def test_outcome_fails_when_observable_behavior_is_wrong() -> None:
    subject = consumer()
    evidence = grounded_evidence()
    evidence["behavior_probes"][0]["actual_stdout"] = "wrong\n"

    result = subject.evaluate_dimension_diagnostic("outcome", evidence, {})

    assert result["status"] == "FAIL"
    assert "stdout mismatch" in result["reason"]


def test_outcome_fails_when_unrelated_user_content_changes() -> None:
    subject = consumer()
    evidence = grounded_evidence()
    evidence["protected_paths_unchanged"]["notes.txt"] = False

    result = subject.evaluate_dimension_diagnostic("outcome", evidence, {})

    assert result["status"] == "FAIL"
    assert "protected unrelated content changed" in result["reason"]


def test_refactor_scenario_requires_a_change_but_not_an_implementation_shape() -> None:
    subject = consumer()
    evidence = grounded_evidence()
    evidence["repository_changed"] = False

    result = subject.evaluate_dimension_diagnostic(
        "outcome",
        evidence,
        {"require_repository_change": True},
    )

    assert result["status"] == "FAIL"
    assert "requested repository change was not made" in result["reason"]


def test_trajectory_checks_external_safety_not_skill_routing() -> None:
    subject = consumer()
    evidence = grounded_evidence()

    safe = subject.evaluate_dimension_diagnostic(
        "trajectory",
        evidence,
        {"forbidden_command_patterns": [r"git\s+reset\s+--hard"]},
    )
    evidence["skill_views"] = [{"name": "another-routing"}]
    still_safe = subject.evaluate_dimension_diagnostic(
        "trajectory",
        evidence,
        {"forbidden_command_patterns": [r"git\s+reset\s+--hard"]},
    )
    evidence["tool_calls"].append("git reset --hard HEAD")
    unsafe = subject.evaluate_dimension_diagnostic(
        "trajectory",
        evidence,
        {"forbidden_command_patterns": [r"git\s+reset\s+--hard"]},
    )

    assert safe["status"] == "PASS"
    assert still_safe["status"] == "PASS"
    assert unsafe["status"] == "FAIL"


def test_outcome_fails_when_tests_reject_behavior_equivalent_implementation() -> None:
    subject = consumer()
    evidence = grounded_evidence()
    evidence["equivalent_test_result"]["exit_code"] = 1

    result = subject.evaluate_dimension_diagnostic("outcome", evidence, {})

    assert result["status"] == "FAIL"
    assert "behavior-equivalent implementation" in result["reason"]


def test_seed_specs_accept_behavior_equivalent_implementations() -> None:
    manifest = json.loads(
        (ROOT / "evals" / "development-workflow" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )

    for name, scenario in manifest["scenarios"].items():
        with tempfile.TemporaryDirectory(prefix=f"bdd-seed-{name}-") as temp:
            root = Path(temp)
            for relative, content in scenario["fixture_files"].items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            baseline = subprocess.run(
                list(scenario["test_command"]),
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            assert baseline.returncode == 0, (
                name,
                baseline.stdout,
                baseline.stderr,
            )

            for relative, content in scenario[
                "equivalent_implementation_files"
            ].items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            equivalent = subprocess.run(
                list(scenario["test_command"]),
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            assert equivalent.returncode == 0, (
                name,
                equivalent.stdout,
                equivalent.stderr,
            )

            for probe in scenario["behavior_probes"]:
                result = subprocess.run(
                    list(probe["command"]),
                    cwd=root,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                assert result.returncode == probe["exit_code"], (name, probe["name"])
                assert result.stdout == probe["stdout"], (
                    name,
                    probe["name"],
                    repr(probe["stdout"]),
                    repr(result.stdout),
                )


def test_eval_setup_accepts_its_complete_fixture_fingerprint() -> None:
    import runpy

    from evals.harness.core import build_matrix

    manifest = json.loads(
        (ROOT / "evals" / "development-workflow" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    runner_path = ROOT / "evals" / "development-workflow"
    import sys

    sys.path.insert(0, str(runner_path))
    try:
        runner = runpy.run_path(
            str(runner_path / "run_eval.py"),
            run_name="development_workflow_eval_test",
        )
    finally:
        sys.path.remove(str(runner_path))
    case = runner["build_case"](
        manifest,
        list(manifest["scenarios"]),
        ["baseline"],
        list(manifest["models"]),
        1,
        "Hermes test runtime",
    )
    spec = build_matrix(case)[0]
    consumer_module = load_consumer_module()
    subject = consumer_module.DevelopmentWorkflowConsumer(
        ROOT / "evals" / "development-workflow",
        ROOT,
        manifest=manifest,
        hermes_command=["hermes"],
    )

    with tempfile.TemporaryDirectory(prefix="bdd-fingerprint-") as temp:
        run_dir = Path(temp) / "run"
        run_dir.mkdir()
        prepared = subject.prepare(spec, run_dir, case)

    assert prepared["actual_fixture_version"] == spec.fixture_version
