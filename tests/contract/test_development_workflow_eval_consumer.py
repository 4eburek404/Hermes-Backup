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
    evidence["workflow_events"] = [
        {"kind": "current_behavior_observed", "index": 1},
        {"kind": "target_check_changed", "index": 2},
        {"kind": "target_check_failed", "index": 3},
        {"kind": "production_changed", "index": 4},
        {"kind": "target_check_passed", "index": 5},
        {"kind": "preserved_behavior_observed", "index": 6},
    ]

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


def test_missing_red_evidence_does_not_pass_feature_trajectory() -> None:
    subject = consumer()
    evidence = grounded_evidence()
    evidence["scenario"] = "feature-shout"
    evidence["workflow_events"] = [
        {"kind": "current_behavior_observed"},
        {"kind": "target_check_changed"},
        {"kind": "production_changed"},
        {"kind": "target_check_passed"},
        {"kind": "preserved_behavior_observed"},
    ]

    result = subject.evaluate_dimension_diagnostic(
        "trajectory", evidence, {"target_failure_signal": "100"}
    )

    assert result["status"] == "FAIL"
    assert "RED" in result["reason"]


def test_saved_unforced_boundary_baseline_does_not_prove_red_before_fix() -> None:
    subject = consumer()
    run = ROOT / "evals" / "development-workflow" / "runs" / "20261001T045300Z" / (
        "bug-boundary--gpt-5.6-luna--openai-codex--baseline--r1"
    )
    evidence = json.loads((run / "evidence.json").read_text(encoding="utf-8"))
    metadata = json.loads((run / "metadata.json").read_text(encoding="utf-8"))
    score = json.loads((run / "score.json").read_text(encoding="utf-8"))["score"]
    raw_events = [
        json.loads(line)
        for line in (run / "raw_stream.jsonl").read_text(encoding="utf-8").splitlines()
        if line.lstrip().startswith("{")
    ]
    skill_views = [event for event in raw_events if event.get("type") == "tool_use" and event.get("name") == "skill_view"]

    assert "--skills" not in metadata["command"]
    assert skill_views == []
    assert score["trajectory"] == "PASS"
    assert subject.evaluate_dimension_diagnostic("trajectory", evidence, {})["status"] == "FAIL"


def test_equivalent_red_green_trajectory_is_not_bound_to_command_wording() -> None:
    subject = consumer()
    evidence = grounded_evidence()
    evidence["scenario"] = "bug-boundary"
    evidence["workflow_events"] = [
        {"kind": "current_behavior_observed"},
        {"kind": "target_check_changed"},
        {"kind": "target_check_failed", "output": "expected 0 at 100; observed 10"},
        {"kind": "production_changed"},
        {"kind": "target_check_passed"},
        {"kind": "preserved_behavior_observed"},
    ]

    result = subject.evaluate_dimension_diagnostic(
        "trajectory", evidence, {"target_failure_signal": "100"}
    )

    assert result["status"] == "PASS", result


def test_refactor_trajectory_requires_observed_green_before_and_after_change() -> None:
    subject = consumer()
    evidence = grounded_evidence()
    evidence["scenario"] = "refactor-preserve"
    rules = {"requires_red": False, "current_probe_count": 2, "preserved_probe_count": 2}
    evidence["workflow_events"] = [
        {"kind": "current_behavior_observed", "index": 1, "probe_index": 0},
        {"kind": "current_behavior_observed", "index": 2, "probe_index": 1},
        {"kind": "target_check_passed", "index": 3},
        {"kind": "production_changed", "index": 4},
        {"kind": "target_check_passed", "index": 5},
        {"kind": "preserved_behavior_observed", "index": 6, "probe_index": 0},
        {"kind": "preserved_behavior_observed", "index": 7, "probe_index": 1},
    ]

    result = subject.evaluate_dimension_diagnostic("trajectory", evidence, rules)
    assert result["status"] == "PASS", result

    evidence["workflow_events"] = [
        event for event in evidence["workflow_events"]
        if not (event["kind"] == "target_check_passed" and event["index"] == 3)
    ]
    missing_pre_green = subject.evaluate_dimension_diagnostic("trajectory", evidence, rules)
    assert missing_pre_green["status"] == "FAIL"
    assert "GREEN before refactor" in missing_pre_green["reason"]


def test_controlled_owner_command_is_recorded_but_routing_is_not_outcome() -> None:
    subject = consumer()
    manifest = json.loads(
        (ROOT / "evals" / "development-workflow" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["execution"]["skill_behavior"]["owner_skill"] == "spec-driven-development"
    assert manifest["execution"]["skill_behavior"]["force_owner_skill"] is True
    assert manifest["execution"]["natural_routing"]["force_owner_skill"] is False
    evidence = grounded_evidence()
    evidence["skill_views"] = []
    assert subject.evaluate_dimension_diagnostic("outcome", evidence, {})["status"] == "PASS"


def test_hermes_invocation_forces_owner_only_in_skill_behavior_mode(monkeypatch, tmp_path) -> None:
    module = load_consumer_module()
    manifest = json.loads(
        (ROOT / "evals" / "development-workflow" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    scenario = manifest["scenarios"]["feature-shout"]
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setenv("TMPDIR", str(scratch))

    def invoke(mode: str) -> list[str]:
        captured: dict[str, list[str]] = {}
        subject = module.DevelopmentWorkflowConsumer(
            ROOT / "evals" / "development-workflow", ROOT, manifest, ["hermes"]
        )

        def fake_skill_root(version, root):
            skills = root / "skills"
            skills.mkdir(parents=True)
            return skills, [{"resolved_commit": "test-source"}]

        def fake_run(command, **kwargs):
            captured["command"] = command
            return subprocess.CompletedProcess(command, 0, '{"type":"result","text":"done"}\n', ""), False

        subject._build_skill_root = fake_skill_root
        monkeypatch.setattr(module, "run_with_timeout", fake_run)
        fixture_version = module.canonical_sha256({
            "fixture_files": scenario["fixture_files"],
            "equivalent_implementation_files": scenario.get("equivalent_implementation_files", {}),
        })
        spec = module.RunSpec(
            "feature-shout", "test-model", "test-provider", "baseline", 1,
            fixture_version, module.canonical_sha256(scenario["prompt"]), "test-runtime", mode,
        )
        run_dir = tmp_path / mode
        run_dir.mkdir()
        prepared = subject.prepare(spec, run_dir, {})
        subject.execute(spec, run_dir, prepared, {})
        return captured["command"]

    controlled = invoke("skill-behavior")
    audit = invoke("natural-routing")

    assert controlled[controlled.index("--skills") + 1] == "spec-driven-development"
    assert "--skills" not in audit
    assert list(scratch.iterdir()) == []
    assert not (tmp_path / "skill-behavior" / "fixture-repo").exists()
    assert (tmp_path / "skill-behavior" / "final.diff").exists()


def test_fixture_setup_failure_removes_only_its_temporary_repository(monkeypatch, tmp_path) -> None:
    module = load_consumer_module()
    manifest = json.loads(
        (ROOT / "evals" / "development-workflow" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    scenario = manifest["scenarios"]["feature-shout"]
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setenv("TMPDIR", str(scratch))
    subject = module.DevelopmentWorkflowConsumer(
        ROOT / "evals" / "development-workflow", ROOT, manifest, ["hermes"]
    )
    spec = module.RunSpec(
        "feature-shout", "test-model", "test-provider", "baseline", 1,
        "intentionally-wrong", module.canonical_sha256(scenario["prompt"]),
        "test-runtime", "skill-behavior",
    )
    run_dir = tmp_path / "setup-failure"
    run_dir.mkdir()

    try:
        subject.prepare(spec, run_dir, {})
    except RuntimeError as exc:
        assert "fixture drift" in str(exc)
    else:
        raise AssertionError("fixture drift was not detected")

    assert list(scratch.iterdir()) == []


def test_equivalent_tool_trace_extracts_behavior_red_change_green_without_command_names(tmp_path) -> None:
    subject = consumer()
    fixture = tmp_path / "project"
    fixture.mkdir()
    source = fixture / "src" / "shipping.py"
    check = fixture / "checks" / "boundary.spec"
    events = [
        {"type": "tool_use", "name": "terminal", "input": {"command": "./observe-edge"}},
        {"type": "tool_result", "name": "terminal", "output": json.dumps({"output": "10\n", "exit_code": 0})},
        {"type": "tool_use", "name": "patch", "input": {"patch": "- expect(100, 10)\n+ expect(100, 0)"}},
        {"type": "tool_result", "name": "patch", "output": json.dumps({"files_modified": [str(check)]})},
        {"type": "tool_use", "name": "terminal", "input": {"command": "./verify-contract"}},
        {"type": "tool_result", "name": "terminal", "output": json.dumps({"output": "AssertionError: expected 0 at 100, received 10", "exit_code": 1})},
        {"type": "tool_use", "name": "patch", "input": {"patch": "change shipping calculation"}},
        {"type": "tool_result", "name": "patch", "output": json.dumps({"files_modified": [str(source)]})},
        {"type": "tool_use", "name": "terminal", "input": {"command": "./verify-contract"}},
        {"type": "tool_result", "name": "terminal", "output": json.dumps({"output": "2 passed", "exit_code": 0})},
        {"type": "tool_use", "name": "terminal", "input": {"command": "./check-neighbor-a"}},
        {"type": "tool_result", "name": "terminal", "output": json.dumps({"output": "10\n", "exit_code": 0})},
        {"type": "tool_use", "name": "terminal", "input": {"command": "./check-neighbor-b"}},
        {"type": "tool_result", "name": "terminal", "output": json.dumps({"output": "0\n", "exit_code": 0})},
    ]
    cfg = {
        "current_behavior_probes": [{"exit_code": 0, "stdout": "10\n"}],
        "target_check_signals": ["100", "0"],
        "preserved_behavior_probes": [
            {"exit_code": 0, "stdout": "10\n"},
            {"exit_code": 0, "stdout": "0\n"},
        ],
    }
    summary = subject.event_summary("\n".join(json.dumps(event) for event in events), cfg, fixture)
    evidence = grounded_evidence()
    evidence["workflow_events"] = summary["workflow_events"]

    result = subject.evaluate_dimension_diagnostic(
        "trajectory", evidence, {"requires_red": True, "target_failure_signal": "100", "preserved_probe_count": 2}
    )

    assert result["status"] == "PASS", result


def test_trace_uses_passing_executable_contracts_for_pre_and_post_behavior() -> None:
    subject = consumer()
    import tempfile

    with tempfile.TemporaryDirectory(prefix="bdd-workflow-contract-") as temp:
        fixture = Path(temp) / "project"
        check = fixture / "checks" / "public-behavior.feature"
        production = fixture / "app.py"
        check.parent.mkdir(parents=True)
        expected = "50.00" + chr(10)
        check.write_text(f'regular "50" => {json.dumps(expected)}', encoding="utf-8")
        production.write_text("implementation", encoding="utf-8")
        events = [
            {"type": "tool_use", "name": "terminal", "input": {"command": "./verify-before"}},
            {"type": "tool_result", "name": "terminal", "output": json.dumps({"output": "1 passed", "exit_code": 0})},
            {"type": "tool_use", "name": "patch", "input": {"patch": "modify implementation"}},
            {"type": "tool_result", "name": "patch", "output": json.dumps({"files_modified": [str(production)]})},
            {"type": "tool_use", "name": "terminal", "input": {"command": "./verify-after"}},
            {"type": "tool_result", "name": "terminal", "output": json.dumps({"output": "1 passed", "exit_code": 0})},
        ]
        cfg = {
            "current_behavior_probes": [{"exit_code": 0, "stdout": expected, "input_signals": ["50"]}],
            "preserved_behavior_probes": [{"exit_code": 0, "stdout": expected, "input_signals": ["50"]}],
        }
        summary = subject.event_summary(chr(10).join(json.dumps(event) for event in events), cfg, fixture)

    observed = {item["kind"] for item in summary["workflow_events"]}
    assert "current_behavior_observed" in observed
    assert "preserved_behavior_observed" in observed


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
    prior_consumer = sys.modules.get("consumer")
    try:
        runner = runpy.run_path(
            str(runner_path / "run_eval.py"),
            run_name="development_workflow_eval_test",
        )
    finally:
        sys.path.remove(str(runner_path))
        if prior_consumer is None:
            sys.modules.pop("consumer", None)
        else:
            sys.modules["consumer"] = prior_consumer
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
