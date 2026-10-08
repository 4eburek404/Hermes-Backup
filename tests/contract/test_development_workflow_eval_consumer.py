from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


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


def write_fake_hermes(path: Path) -> Path:
    path.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
import uuid

if "--oneshot" in sys.argv:
    print(json.dumps({"type": "result", "text": "done"}), flush=True)
    raise SystemExit(0)

if not (sys.stdin.isatty() and sys.stdout.isatty()):
    raise SystemExit("ordinary chat did not receive a TTY")

prompt_path = sys.argv[sys.argv.index("--query-file") + 1]
prompt = open(prompt_path, encoding="utf-8").read()
from hermes_state import SessionDB
db = SessionDB()
session_id = uuid.uuid4().hex
db.create_session(session_id, "eval", model="test-model", cwd=os.getcwd())
call_id = "read-skill"
db.append_message(session_id, "user", content=prompt)
db.append_message(
    session_id,
    "assistant",
    content="",
    tool_calls=[{
        "id": call_id,
        "type": "function",
        "function": {
            "name": "read_file",
            "arguments": json.dumps({
                "path": "/tmp/hermes-home/skills/development/behavior-driven-development/SKILL.md"
            }),
        },
    }],
)
db.append_message(
    session_id,
    "tool",
    content=json.dumps({"content": "# Behavior-driven development"}),
    tool_name="read_file",
    tool_call_id=call_id,
)
db.append_message(session_id, "assistant", content="done")
print("normal session ready", flush=True)
os.read(0, 1)
db.end_session(session_id, "cli_close")
db.close()
""",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


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
    fixture = json.loads(
        (
            ROOT
            / "evals"
            / "development-workflow"
            / "fixtures"
            / "regressions"
            / "unforced-boundary-missing-red.json"
        ).read_text(encoding="utf-8")
    )

    assert "--skills" not in fixture["metadata"]["command"]
    assert fixture["raw_trace_summary"]["skill_views"] == []
    assert fixture["historical_score"]["trajectory"] == "PASS"

    result = subject.evaluate_dimension_diagnostic(
        "trajectory", fixture["evidence"], {}
    )

    assert result["status"] == "FAIL"
    assert "RED" in result["reason"]

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

    assert manifest["execution"]["skill_behavior"]["owner_skills"]["candidate"] == "behavior-driven-development"
    assert manifest["execution"]["skill_behavior"]["force_owner_skill"] is True
    assert manifest["execution"]["natural_routing"]["force_owner_skill"] is False
    evidence = grounded_evidence()
    evidence["skill_views"] = []
    assert subject.evaluate_dimension_diagnostic("outcome", evidence, {})["status"] == "PASS"


def test_hermes_invocation_forces_owner_only_in_skill_behavior_mode(monkeypatch, tmp_path) -> None:
    module = load_consumer_module()
    manifest = json.loads(
        (ROOT / "evals" / "development-workflow" / "manifest.json").read_text(
            encoding="utf-8")
    )
    manifest["execution"]["eval_timeout_seconds"] = 3
    scenario = manifest["scenarios"]["feature-shout"]
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setenv("TMPDIR", str(scratch))
    fake_hermes = write_fake_hermes(tmp_path / "fake-hermes")

    def invoke(mode: str):
        captured: dict[str, Any] = {}
        subject = module.DevelopmentWorkflowConsumer(
            ROOT / "evals" / "development-workflow", ROOT, manifest, [str(fake_hermes)]
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
            "feature-shout", "test-model", "test-provider", "candidate", 1,
            fixture_version, module.canonical_sha256(scenario["prompt"]), "test-runtime", mode,
        )
        run_dir = tmp_path / mode
        run_dir.mkdir()
        prepared = subject.prepare(spec, run_dir, {})
        subject.execute(spec, run_dir, prepared, {})
        captured["metadata"] = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
        captured.setdefault("command", captured["metadata"]["command"])
        return captured

    controlled = invoke("skill-behavior")
    audit = invoke("natural-routing")

    assert controlled["command"][controlled["command"].index("--skills") + 1] == "behavior-driven-development"
    assert "--skills" not in audit["command"]
    assert "--oneshot" not in audit["command"]
    assert "--quiet" not in audit["command"]
    assert "--format" not in audit["command"]
    assert controlled["metadata"]["evaluation_mode"] == "skill-behavior"
    assert controlled["metadata"]["forced_owner_skill"] == "behavior-driven-development"
    assert controlled["metadata"]["fixture_sha256"] == module.canonical_sha256({
        "fixture_files": scenario["fixture_files"],
        "equivalent_implementation_files": scenario.get("equivalent_implementation_files", {}),
    })
    assert audit["metadata"]["forced_owner_skill"] is None
    assert list(scratch.iterdir()) == []
    assert not (tmp_path / "skill-behavior" / "fixture-repo").exists()
    assert (tmp_path / "skill-behavior" / "final.diff").exists()


def test_versioned_skill_behavior_uses_each_owner_under_identical_conditions(
    monkeypatch, tmp_path
) -> None:
    module = load_consumer_module()
    manifest = json.loads(
        (ROOT / "evals" / "development-workflow" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    manifest["execution"]["skill_behavior"]["owner_skills"] = {
        "baseline": "spec-driven-development",
        "candidate": "behavior-driven-development",
    }
    scenario = manifest["scenarios"]["feature-shout"]
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setenv("TMPDIR", str(scratch))
    subject = module.DevelopmentWorkflowConsumer(
        ROOT / "evals" / "development-workflow",
        ROOT,
        manifest,
        ["fake-hermes"],
    )
    identities = {
        "baseline": "baseline-source-ref",
        "candidate": "candidate-working-tree",
    }

    def materialize(version, root):
        skills = root / "skills"
        skills.mkdir()
        return skills, [{"resolved_source": identities[version]}]

    subject._build_skill_root = materialize

    def run_agent(command, **kwargs):
        result = {"type": "result", "text": "done"}
        output = json.dumps(result) + "\n"
        return subprocess.CompletedProcess(command, 0, output, ""), False

    monkeypatch.setattr(module, "run_with_timeout", run_agent)
    fixture_version = module.canonical_sha256(
        {
            "fixture_files": scenario["fixture_files"],
            "equivalent_implementation_files": scenario.get(
                "equivalent_implementation_files", {}
            ),
        }
    )
    prompt_version = module.canonical_sha256(scenario["prompt"])
    runs = {}
    for version in ("baseline", "candidate"):
        spec = module.RunSpec(
            "feature-shout",
            "gpt-6-luna",
            "openai-codex",
            version,
            1,
            fixture_version,
            prompt_version,
            "same-hermes-runtime",
            "skill-behavior",
        )
        run_dir = tmp_path / version
        run_dir.mkdir()
        prepared = subject.prepare(spec, run_dir, {})
        runs[version] = subject.execute(spec, run_dir, prepared, {})

    baseline, candidate = runs["baseline"], runs["candidate"]
    def selected_owner(run):
        command = run["command"]
        return command[command.index("--skills") + 1]

    assert selected_owner(baseline) == "spec-driven-development"
    assert selected_owner(candidate) == "behavior-driven-development"
    assert baseline["forced_owner_skill"] == "spec-driven-development"
    assert candidate["forced_owner_skill"] == "behavior-driven-development"
    assert baseline["skill_sources"] == [{"resolved_source": identities["baseline"]}]
    assert candidate["skill_sources"] == [{"resolved_source": identities["candidate"]}]
    for field in (
        "evaluation_mode",
        "model",
        "provider",
        "fixture_sha256",
        "prompt_sha256",
    ):
        assert baseline[field] == candidate[field]

    evidence = grounded_evidence()
    evidence["scenario"] = "feature-shout"
    evidence["workflow_events"] = [
        {"kind": "current_behavior_observed", "index": 1},
        {"kind": "target_check_changed", "index": 2},
        {"kind": "target_check_failed", "index": 3},
        {"kind": "production_changed", "index": 4},
        {"kind": "target_check_passed", "index": 5},
        {"kind": "preserved_behavior_observed", "index": 6},
    ]
    verdicts = []
    for owner in ("spec-driven-development", "behavior-driven-development"):
        owner_evidence = {**evidence, "forced_owner_skill": owner}
        verdicts.append(
            (
                subject.evaluate_dimension_diagnostic("outcome", owner_evidence, {}),
                subject.evaluate_dimension_diagnostic("trajectory", owner_evidence, {}),
            )
        )
    assert verdicts[0] == verdicts[1]
    assert verdicts[0][0]["status"] == "PASS"
    assert verdicts[0][1]["status"] == "PASS"


def test_versioned_owner_sources_leave_all_non_owner_skills_identical(tmp_path) -> None:
    module = load_consumer_module()
    manifest = json.loads(
        (ROOT / "evals" / "development-workflow" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    owner_paths = {
        "baseline": "hermes/skills/software-development/spec-driven-development",
        "candidate": "hermes/skills/software-development/behavior-driven-development",
    }
    for version in owner_paths:
        manifest["skill_versions"][version]["skill_paths"] = [owner_paths[version]]
    subject = module.DevelopmentWorkflowConsumer(
        ROOT / "evals" / "development-workflow", ROOT, manifest
    )

    skill_roots = {}
    identities = {}
    for version in owner_paths:
        build_root = tmp_path / version
        build_root.mkdir()
        skill_roots[version], identities[version] = subject._build_skill_root(
            version, build_root
        )

    def files(root):
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }

    baseline_files = files(skill_roots["baseline"])
    candidate_files = files(skill_roots["candidate"])
    changed_paths = {
        path
        for path in baseline_files.keys() | candidate_files.keys()
        if baseline_files.get(path) != candidate_files.get(path)
    }

    assert changed_paths
    assert all(
        path.startswith("software-development/spec-driven-development/")
        for path in changed_paths
    ), sorted(changed_paths)
    assert identities["baseline"][0]["resolved_commit"] == (
        "ddab90073d5b00e44c0b2987217eef6ae14f67fb"
    )
    assert identities["baseline"][0]["skill_path"] == owner_paths["baseline"]
    assert identities["candidate"][0]["source"] == "working_tree"
    assert identities["candidate"][0]["skill_path"] == owner_paths["candidate"]


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


def test_unidentified_commands_do_not_prove_probe_inputs_from_matching_output(tmp_path) -> None:
    subject = consumer()
    fixture = tmp_path / "project"
    fixture.mkdir()
    source = fixture / "src" / "shipping.py"
    check = fixture / "checks" / "boundary.spec"
    events = [
        {"type": "tool_use", "name": "terminal", "input": {"command": "python3 shipping.py 100"}},
        {"type": "tool_result", "name": "terminal", "output": json.dumps({"output": "10\n", "exit_code": 0})},
        {"type": "tool_use", "name": "patch", "input": {"patch": "- expect(100, 10)\n+ expect(100, 0)"}},
        {"type": "tool_result", "name": "patch", "output": json.dumps({"files_modified": [str(check)]})},
        {"type": "tool_use", "name": "terminal", "input": {"command": "./verify-contract"}},
        {"type": "tool_result", "name": "terminal", "output": json.dumps({"output": "AssertionError: expected 0 at 100, received 10", "exit_code": 1})},
        {"type": "tool_use", "name": "patch", "input": {"patch": "change shipping calculation"}},
        {"type": "tool_result", "name": "patch", "output": json.dumps({"files_modified": [str(source)]})},
        {"type": "tool_use", "name": "terminal", "input": {"command": "./verify-contract"}},
        {"type": "tool_result", "name": "terminal", "output": json.dumps({"output": "2 passed", "exit_code": 0})},
        {"type": "tool_use", "name": "terminal", "input": {"command": "python3 shipping.py 99.99"}},
        {"type": "tool_result", "name": "terminal", "output": json.dumps({"output": "10\n", "exit_code": 0})},
        {"type": "tool_use", "name": "terminal", "input": {"command": "python3 shipping.py 100.01"}},
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

    assert result["status"] == "FAIL", result
    assert "current observable behavior is UNCONFIRMED" in result["reason"]


def test_matching_file_text_does_not_confirm_program_execution_or_arguments() -> None:
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
    assert "current_behavior_observed" not in observed
    assert "preserved_behavior_observed" not in observed



def test_outcome_fails_when_tests_reject_behavior_equivalent_implementation() -> None:
    subject = consumer()
    evidence = grounded_evidence()
    evidence["equivalent_test_result"]["exit_code"] = 1

    result = subject.evaluate_dimension_diagnostic("outcome", evidence, {})

    assert result["status"] == "FAIL"
    assert "behavior-equivalent implementation" in result["reason"]


def test_feature_shout_equivalent_implementation_preserves_no_argument_behavior() -> None:
    manifest = json.loads(
        (ROOT / "evals" / "development-workflow" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    scenario = manifest["scenarios"]["feature-shout"]

    with tempfile.TemporaryDirectory(prefix="bdd-feature-no-arg-") as temp:
        root = Path(temp)
        for relative, content in scenario["fixture_files"].items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        current = subprocess.run(
            ["python3", "app.py"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        assert current.returncode == 0, current.stderr
        assert current.stdout == "Hello, World!\n"

        for relative, content in scenario.get(
            "equivalent_implementation_files", {}
        ).items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        equivalent = subprocess.run(
            ["python3", "app.py"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        assert equivalent.returncode == 0, equivalent.stderr
        assert equivalent.stdout == current.stdout == "Hello, World!\n"


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

            for relative, content in scenario.get(
                "equivalent_implementation_files", {}
            ).items():
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


def test_all_skill_eval_luna_defaults_use_gpt_6_luna() -> None:
    manifests = sorted((ROOT / "evals").glob("*/manifest.json"))
    luna_models = [
        (path, item["model"])
        for path in manifests
        for item in json.loads(path.read_text(encoding="utf-8")).get("models", [])
        if item.get("provider") == "openai-codex"
        and "luna" in item.get("model", "").lower()
    ]

    assert luna_models
    assert all(model == "gpt-6-luna" for _, model in luna_models), luna_models


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
    sys.modules["consumer"] = load_consumer_module()
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

    prepared = None
    try:
        with tempfile.TemporaryDirectory(prefix="bdd-fingerprint-") as temp:
            run_dir = Path(temp) / "run"
            run_dir.mkdir()
            prepared = subject.prepare(spec, run_dir, case)
            assert prepared["actual_fixture_version"] == spec.fixture_version
    finally:
        if prepared is not None:
            shutil.rmtree(prepared["fixture_parent"], ignore_errors=True)


def test_mechanical_trajectory_allows_minimal_change_without_test_ceremony() -> None:
    subject = consumer()
    evidence = grounded_evidence()
    evidence["workflow_events"] = [
        {"kind": "current_behavior_observed", "index": 1, "probe_index": 0},
        {"kind": "target_check_passed", "index": 2},
        {"kind": "production_changed", "index": 3},
        {"kind": "target_check_passed", "index": 4},
        {"kind": "preserved_behavior_observed", "index": 5, "probe_index": 0},
    ]

    result = subject.evaluate_dimension_diagnostic(
        "trajectory", evidence,
        {"mechanical": True, "preserved_probe_count": 1},
    )

    assert result["status"] == "PASS", result


def test_mechanical_trajectory_rejects_regression_edits_artificial_red_and_missing_check() -> None:
    subject = consumer()
    base = grounded_evidence()
    base["workflow_events"] = [
        {"kind": "current_behavior_observed", "index": 1, "probe_index": 0},
        {"kind": "production_changed", "index": 2},
        {"kind": "target_check_passed", "index": 3},
        {"kind": "preserved_behavior_observed", "index": 4, "probe_index": 0},
    ]
    rules = {"mechanical": True, "preserved_probe_count": 1}

    for invalid_event, expected_reason in [
        ({"kind": "verification_changed", "index": 2}, "unnecessary regression"),
        ({"kind": "verification_failed", "index": 2}, "artificial RED"),
    ]:
        evidence = {**base, "workflow_events": [*base["workflow_events"], invalid_event]}
        result = subject.evaluate_dimension_diagnostic("trajectory", evidence, rules)
        assert result["status"] == "FAIL"
        assert expected_reason in result["reason"]

    missing_check = {
        **base,
        "workflow_events": [
            event for event in base["workflow_events"]
            if event["kind"] != "target_check_passed"
        ],
    }
    result = subject.evaluate_dimension_diagnostic("trajectory", missing_check, rules)
    assert result["status"] == "FAIL"
    assert "verification after mechanical change" in result["reason"]

    missing_current = {
        **base,
        "workflow_events": [
            event for event in base["workflow_events"]
            if event["kind"] != "current_behavior_observed"
        ],
    }
    result = subject.evaluate_dimension_diagnostic("trajectory", missing_current, rules)
    assert result["status"] == "FAIL"
    assert "current observable behavior" in result["reason"]


def test_mechanical_scenario_is_registered_as_a_no_red_behavior_contract() -> None:
    import runpy

    manifest = json.loads(
        (ROOT / "evals" / "development-workflow" / "manifest.json").read_text(encoding="utf-8")
    )
    scenario = manifest["scenarios"]["mechanical-rename"]
    assert scenario["mechanical"] is True
    assert len(scenario["current_behavior_probes"]) == 1
    assert scenario["current_behavior_probes"] == scenario["preserved_behavior_probes"]
    assert scenario["protected_paths"] == ["notes.txt"]
    import sys
    runner_path = ROOT / "evals" / "development-workflow"
    sys.path.insert(0, str(runner_path))
    try:
        runner = runpy.run_path(str(runner_path / "run_eval.py"), run_name="mechanical_eval_test")
    finally:
        sys.path.remove(str(runner_path))
    case = runner["build_case"](manifest, ["mechanical-rename"], ["candidate"], manifest["models"], 1, "test")
    rules = case["rules"]["mechanical-rename"]["trajectory"]
    assert rules["mechanical"] is True
    assert rules["requires_red"] is False


def review_evidence() -> dict:
    return {
        "scenario": "review-only",
        "execution_status": "COMPLETED",
        "final_answer": (
            "Finding: shipping.py: the new threshold charges 10 at an order total "
            "of 100, although the documented rule makes shipping free at 100. "
            "Confirmed by running the program: output was 10."
        ),
        "pre_snapshot": {"head": "abc", "status_porcelain": " M shipping.py", "file_sha256": {"shipping.py": "1"}},
        "post_snapshot": {"head": "abc", "status_porcelain": " M shipping.py", "file_sha256": {"shipping.py": "1"}},
        "repository_changed": False,
        "protected_paths_unchanged": {"notes.txt": True},
        "review_evidence": [
            {"kind": "change_inspected", "output": "diff --git a/shipping.py b/shipping.py"},
            {"kind": "change_inspected", "output": "Shipping contract: orders of 100 or more ship free."},
            {"kind": "check_observed", "command": "python3 shipping.py 100", "output": "10\n", "exit_code": 0},
        ],
        "mutation_events": [],
        "tool_calls": ["git diff", "python3 shipping.py 100"],
    }


def test_review_scenario_registers_review_owner_and_dirty_fixture() -> None:
    manifest = json.loads(
        (ROOT / "evals" / "development-workflow" / "manifest.json").read_text(encoding="utf-8")
    )
    scenario = manifest["scenarios"]["review-only"]
    assert scenario["review_only"] is True
    assert scenario["owner_skill"] == "github-code-review"
    assert scenario["preexisting_changes"]
    assert scenario["protected_paths"] == ["notes.txt"]
    assert "fix" not in scenario["prompt"].lower()


def test_review_preexisting_change_is_included_in_fixture_baseline_hash() -> None:
    import runpy
    import sys

    from evals.harness.core import build_matrix

    manifest = json.loads(
        (ROOT / "evals" / "development-workflow" / "manifest.json").read_text(encoding="utf-8")
    )
    scenario = manifest["scenarios"]["review-only"]
    runner_path = ROOT / "evals" / "development-workflow"
    sys.path.insert(0, str(runner_path))
    try:
        runner = runpy.run_path(str(runner_path / "run_eval.py"), run_name="review_eval_contract")
    finally:
        sys.path.remove(str(runner_path))
    case = runner["build_case"](
        manifest, ["review-only"], ["candidate"], manifest["models"], 1, "test"
    )
    spec = build_matrix(case)[0]
    subject = load_consumer_module().DevelopmentWorkflowConsumer(
        ROOT / "evals" / "development-workflow", ROOT, manifest, ["hermes"]
    )
    with tempfile.TemporaryDirectory(prefix="review-fixture-contract-") as temp:
        run_dir = Path(temp) / "run"
        run_dir.mkdir()
        prepared = subject.prepare(spec, run_dir, case)
        try:
            fixture = prepared["fixture"]
            assert prepared["pre_snapshot"]["status_porcelain"] == "M shipping.py"
            assert prepared["actual_fixture_version"] == spec.fixture_version
            assert "100 or more ship free" in (fixture / "README.md").read_text(encoding="utf-8")
            assert "return 10 if total <= Decimal(\"100\")" in subject._git(fixture, "diff")
            probe = subject._probe(fixture, scenario["behavior_probes"][0])
            assert probe["actual_exit_code"] == 0
            assert probe["actual_stdout"] == "10\n"
            tests = subprocess.run(scenario["test_command"], cwd=fixture, capture_output=True, text=True, check=False)
            assert tests.returncode == 0, (tests.stdout, tests.stderr)
            assert (fixture / "notes.txt").read_text(encoding="utf-8") == scenario["fixture_files"]["notes.txt"]
        finally:
            shutil.rmtree(prepared["fixture_parent"], ignore_errors=True)


def test_review_evidence_requires_documented_expectation_and_observed_behavior() -> None:
    evidence = review_evidence()
    evidence["review_evidence"] = [item for item in evidence["review_evidence"] if "free" not in item["output"].lower()]
    result = consumer().evaluate_dimension_diagnostic(
        "outcome", evidence, {"review_only": True}
    )
    assert result["status"] == "FAIL"


def test_review_scenario_isolation_does_not_change_existing_owner_default() -> None:
    manifest = json.loads(
        (ROOT / "evals" / "development-workflow" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["execution"]["skill_behavior"]["owner_skills"]["candidate"] == "behavior-driven-development"


def test_review_only_correct_finding_without_mutation_passes() -> None:
    result = consumer().evaluate_dimension_diagnostic(
        "outcome", review_evidence(), {"review_only": True}
    )
    assert result["status"] == "PASS", result

    trajectory = consumer().evaluate_dimension_diagnostic(
        "trajectory", review_evidence(), {"review_only": True}
    )
    assert trajectory["status"] == "PASS", trajectory


def test_review_outcome_fails_when_expected_finding_is_missing() -> None:
    evidence = review_evidence()
    evidence["final_answer"] = "Review completed. No findings."
    result = consumer().evaluate_dimension_diagnostic(
        "outcome", evidence, {"review_only": True}
    )
    assert result["status"] == "FAIL"


def test_review_trace_extracts_readonly_evidence_from_recorded_tool_events(tmp_path) -> None:
    subject = consumer()
    events = [
        {"type": "tool_use", "name": "terminal", "input": {"command": "git status --short && git diff"}},
        {"type": "tool_result", "name": "terminal", "output": json.dumps({"output": "diff --git a/shipping.py b/shipping.py", "exit_code": 0})},
        {"type": "tool_use", "name": "read_file", "input": {"path": "README.md"}},
        {"type": "tool_result", "name": "read_file", "output": json.dumps({"content": "1|Shipping contract: orders of 100 or more ship free."})},
        {"type": "tool_use", "name": "terminal", "input": {"command": "set +e; pytest -q; python3 shipping.py 100"}},
        {"type": "tool_result", "name": "terminal", "output": json.dumps({"output": chr(10).join(["2 passed", "10", ""]), "exit_code": 0})},
    ]
    summary = subject.event_summary(
        chr(10).join(json.dumps(event) for event in events),
        {"review_only": True},
        tmp_path,
    )
    evidence = {
        **review_evidence(),
        "review_evidence": summary["review_evidence"],
        "mutation_events": summary["mutation_events"],
        "tool_calls": summary["tool_calls"],
    }
    outcome = subject.evaluate_dimension_diagnostic("outcome", evidence, {"review_only": True})
    trajectory = subject.evaluate_dimension_diagnostic("trajectory", evidence, {"review_only": True})
    assert outcome["status"] == "PASS", (summary, outcome)
    assert trajectory["status"] == "PASS", (summary, trajectory)


def test_review_oracle_accepts_supported_russian_finding() -> None:
    evidence = review_evidence()
    evidence["final_answer"] = (
        "В shipping.py неверно считается доставка: при сумме 100 вместо бесплатной доставки "
        "списывается 10. Проверка вывела 10, README указывает бесплатную доставку от 100."
    )
    assert consumer().evaluate_dimension_diagnostic(
        "outcome", evidence, {"review_only": True}
    )["status"] == "PASS"


def test_review_trajectory_fails_when_production_file_changes() -> None:
    evidence = review_evidence()
    evidence["post_snapshot"] = {"head": "abc", "status_porcelain": " M shipping.py\n M app.py", "file_sha256": {"shipping.py": "1", "app.py": "2"}}
    result = consumer().evaluate_dimension_diagnostic(
        "trajectory", evidence, {"review_only": True}
    )
    assert result["status"] == "FAIL"


def test_review_trajectory_fails_when_test_or_spec_changes() -> None:
    evidence = review_evidence()
    evidence["mutation_events"] = [{"path": "tests/test_shipping.py"}]
    result = consumer().evaluate_dimension_diagnostic(
        "trajectory", evidence, {"review_only": True}
    )
    assert result["status"] == "FAIL"


def test_review_trajectory_fails_when_finding_is_fixed() -> None:
    evidence = review_evidence()
    evidence["repository_changed"] = True
    evidence["post_snapshot"] = {"head": "abc", "status_porcelain": " M shipping.py", "file_sha256": {"shipping.py": "2"}}
    evidence["mutation_events"] = [{"path": "shipping.py"}]
    result = consumer().evaluate_dimension_diagnostic(
        "trajectory", evidence, {"review_only": True}
    )
    assert result["status"] == "FAIL"


def test_review_trajectory_fails_on_delivery_or_destructive_action() -> None:
    for command in ("git commit -am review", "git push origin HEAD", "git reset --hard", "git clean -fd"):
        evidence = review_evidence()
        evidence["tool_calls"] = [command]
        result = consumer().evaluate_dimension_diagnostic(
            "trajectory", evidence, {"review_only": True}
        )
        assert result["status"] == "FAIL", (command, result)

def test_event_summary_distinguishes_skill_view_calls_from_observed_skill_reads() -> None:
    subject = consumer()
    events = [
        {
            "type": "tool_use",
            "name": "skill_view",
            "input": {"name": "github/github-code-review"},
        },
        {
            "type": "tool_result",
            "name": "skill_view",
            "output": json.dumps({"content": "# Code review skill"}),
        },
        {
            "type": "tool_use",
            "name": "read_file",
            "input": {
                "path": "/tmp/hermes-home/skills/development/behavior-driven-development/SKILL.md"
            },
        },
        {
            "type": "tool_result",
            "name": "read_file",
            "output": json.dumps({"content": "# Behavior-driven development"}),
        },
        {
            "type": "tool_use",
            "name": "terminal",
            "input": {
                "command": (
                    "sed -n '1,80p' "
                    "/tmp/hermes-home/skills/development/test-driven-development/SKILL.md"
                )
            },
        },
        {
            "type": "tool_result",
            "name": "terminal",
            "output": json.dumps({"output": "# Test-driven development\n", "exit_code": 0}),
        },
        {
            "type": "tool_use",
            "name": "read_file",
            "input": {"path": "/tmp/project/README.md"},
        },
        {
            "type": "tool_result",
            "name": "read_file",
            "output": json.dumps({"content": "ordinary project file"}),
        },
    ]

    summary = subject.event_summary(
        chr(10).join(json.dumps(event) for event in events)
    )

    assert summary["skill_views"] == [{"name": "github/github-code-review"}]
    assert summary["skill_reads"] == [
        {"skill": "github/github-code-review", "via": "skill_view", "index": 1},
        {
            "skill": "development/behavior-driven-development",
            "via": "read_file",
            "index": 3,
        },
        {
            "skill": "development/test-driven-development",
            "via": "terminal",
            "index": 5,
        },
    ]


def test_natural_run_evidence_preserves_observed_skill_reads(
    monkeypatch, tmp_path
) -> None:
    module = load_consumer_module()
    manifest = json.loads(
        (ROOT / "evals" / "development-workflow" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    manifest["execution"]["eval_timeout_seconds"] = 3
    scenario = manifest["scenarios"]["feature-shout"]
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setenv("TMPDIR", str(scratch))

    subject = module.DevelopmentWorkflowConsumer(
        ROOT / "evals" / "development-workflow",
        ROOT,
        manifest,
        [str(write_fake_hermes(tmp_path / "fake-hermes"))],
    )

    def fake_skill_root(version, root):
        skills = root / "skills"
        skills.mkdir(parents=True)
        return skills, [{"resolved_commit": "test-source"}]

    subject._build_skill_root = fake_skill_root
    fixture_version = module.canonical_sha256(
        {
            "fixture_files": scenario["fixture_files"],
            "equivalent_implementation_files": scenario.get(
                "equivalent_implementation_files", {}
            ),
        }
    )
    spec = module.RunSpec(
        "feature-shout",
        "test-model",
        "test-provider",
        "baseline",
        1,
        fixture_version,
        module.canonical_sha256(scenario["prompt"]),
        "test-runtime",
        "natural-routing",
    )
    run_dir = tmp_path / "natural-routing"
    run_dir.mkdir()

    prepared = subject.prepare(spec, run_dir, {})
    evidence = subject.execute(spec, run_dir, prepared, {})

    assert "--skills" not in evidence["command"]
    assert "--oneshot" not in evidence["command"]
    assert "--quiet" not in evidence["command"]
    assert "--format" not in evidence["command"]
    assert evidence["execution_policy"] == "ordinary-interactive"
    assert evidence["completion_observed"] is True
    assert evidence["skill_views"] == []
    assert evidence["skill_reads"] == [
        {
            "skill": "development/behavior-driven-development",
            "via": "read_file",
            "index": 1,
        }
    ]
    assert evidence["event_summary"]["skill_reads"] == evidence["skill_reads"]
    assert Path(evidence["raw_session_path"]).is_file()
    assert not (run_dir / "raw_stream.jsonl").exists()


def test_routing_diagnostics_preserve_observed_reads_without_acceptance_verdict() -> None:
    evidence = {
        "skill_reads": [
            {"skill": "ponytail", "via": "skill_view", "index": 2},
            {"skill": "test-driven-development", "via": "skill_view", "index": 5},
            {"skill": "behavior-driven-development", "via": "skill_view", "index": 9},
        ],
        "event_summary": {
            "workflow_events": [
                {"kind": "production_changed", "index": 8},
            ],
        },
    }

    result = consumer().routing_diagnostics(evidence)

    assert result == {
        "first_production_index": 8,
        "skill_reads": evidence["skill_reads"],
        "skill_reads_before_production": evidence["skill_reads"][:2],
    }
    assert "status" not in result
    assert "reason" not in result

