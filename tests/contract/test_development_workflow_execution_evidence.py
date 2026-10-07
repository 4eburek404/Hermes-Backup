from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
CONSUMER_PATH = ROOT / "evals/development-workflow/consumer.py"


def consumer():
    spec = importlib.util.spec_from_file_location("development_workflow_consumer_evidence", CONSUMER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.DevelopmentWorkflowConsumer(ROOT / "evals/development-workflow", ROOT, {}, ["hermes"])


def tool_events(command: str, output: str, exit_code: int = 0) -> list[dict]:
    return [
        {"type": "tool_use", "name": "terminal", "input": {"command": command}},
        {"type": "tool_result", "name": "terminal", "output": json.dumps({"output": output, "exit_code": exit_code})},
    ]


def probes():
    return [
        {"exit_code": 0, "stdout": "HELLO, ALICE!\n", "input_signals": ["Alice", "--shout"]},
        {"exit_code": 0, "stdout": "Hello, Alice!\n", "input_signals": ["Alice"]},
        {"exit_code": 0, "stdout": "Hello, World!\n", "input_signals": []},
        {"exit_code": 0, "stdout": "Hello, World!\n", "input_signals": ["World"]},
    ]


def observed(events, tmp_path, cfg=None):
    (tmp_path / "app.py").write_text("print('fixture')\n", encoding="utf-8")
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "tests/test_app.py").write_text("assert True\n", encoding="utf-8")
    cfg = cfg or {
        "current_behavior_probes": probes(),
        "preserved_behavior_probes": [],
        "behavior_probes": [
            {"command": ["python3", "app.py", *item["input_signals"]],
             "exit_code": item["exit_code"], "stdout": item["stdout"]}
            for item in probes()
        ],
    }
    return consumer().event_summary(events, cfg, tmp_path)["workflow_events"]


def ids(facts, kind="current_behavior_observed"):
    return {item["probe_index"] for item in facts if item["kind"] == kind}


def test_standalone_runs_are_attributed_but_chain_stdout_is_not(tmp_path):
    import subprocess

    separate = tool_events("python3 app.py Alice --shout", "HELLO, ALICE!\n")
    separate += tool_events("python3 app.py Alice", "Hello, Alice!\n")
    separate += tool_events("python3 app.py", "Hello, World!\n")
    assert ids(observed(separate, tmp_path)) == {0, 1, 2}

    # This implementation is deliberately adversarial: only the first process
    # writes the three lines, while the later two successful processes are silent.
    (tmp_path / "app.py").write_text(
        "import sys\n"
        "if sys.argv[1:] == ['Alice', '--shout']:\n"
        "    print('HELLO, ALICE!\\nHello, Alice!\\nHello, World!')\n",
        encoding="utf-8",
    )
    command = "python3 app.py Alice --shout && python3 app.py Alice && python3 app.py"
    first = subprocess.run(
        ["python3", "app.py", "Alice", "--shout"], cwd=tmp_path,
        text=True, capture_output=True, check=False,
    )
    second = subprocess.run(
        ["python3", "app.py", "Alice"], cwd=tmp_path,
        text=True, capture_output=True, check=False,
    )
    third = subprocess.run(
        ["python3", "app.py"], cwd=tmp_path,
        text=True, capture_output=True, check=False,
    )
    assert [first.returncode, second.returncode, third.returncode] == [0, 0, 0]
    assert first.stdout == "HELLO, ALICE!\nHello, Alice!\nHello, World!\n"
    assert second.stdout == third.stdout == ""

    composite = subprocess.run(
        command, cwd=tmp_path, shell=True, text=True, capture_output=True, check=False,
    )
    assert composite.returncode == 0
    assert composite.stdout == first.stdout
    aggregated_trace = tool_events(command, composite.stdout, composite.returncode)
    assert ids(observed(aggregated_trace, tmp_path)) == set()


def test_default_invocation_is_distinct_from_explicit_world(tmp_path):
    default = observed(tool_events("python3 app.py", "Hello, World!\n"), tmp_path)
    explicit = observed(tool_events("python3 app.py World", "Hello, World!\n"), tmp_path)
    assert 2 in ids(default) and 3 not in ids(default)
    assert 3 in ids(explicit) and 2 not in ids(explicit)


def test_real_manifest_recognizes_no_argument_probe_and_rejects_extra_inputs(tmp_path):
    manifest = json.loads((ROOT / "evals/development-workflow/manifest.json").read_text())
    cfg = manifest["scenarios"]["feature-shout"]
    default = observed(tool_events("python3 app.py", "Hello, World!\n"), tmp_path, cfg)
    explicit = observed(tool_events("python3 app.py World", "Hello, World!\n"), tmp_path, cfg)
    extra = observed(tool_events("python3 app.py Alice World", "Hello, Alice!\n"), tmp_path, cfg)
    assert 1 in ids(default)
    assert 1 not in ids(explicit)
    assert 0 not in ids(extra)


def test_real_manifest_does_not_assign_chain_stdout_to_expected_runs(tmp_path):
    manifest = json.loads((ROOT / "evals/development-workflow/manifest.json").read_text())
    cfg = manifest["scenarios"]["feature-shout"]
    command = "python3 app.py Alice --shout && python3 app.py Alice && python3 app.py"
    output = "HELLO, ALICE!\nHello, Alice!\nHello, World!\n"
    events = tool_events(command, output) + [
        {"type": "tool_use", "name": "write_file", "input": {"path": str(tmp_path / "app.py"), "content": "changed\\n"}},
        {"type": "tool_result", "name": "write_file", "output": json.dumps({"success": True})},
    ] + tool_events(command, output)
    facts = observed(events, tmp_path, cfg)
    # The prior expectation treated output-line order as per-process boundaries.
    # That assumption is not evidenced by a single shell result.
    observations = [item for item in facts if item["kind"] in {
        "current_behavior_observed", "preserved_behavior_observed"
    }]
    assert observations == []
    assert any(item["kind"] == "production_changed" for item in facts)


def test_other_command_cannot_supply_the_app_output(tmp_path):
    import subprocess

    (tmp_path / "app.py").write_text("pass\n", encoding="utf-8")
    command = "python3 app.py Alice && echo 'Hello, Alice!'"
    result = subprocess.run(command, cwd=tmp_path, shell=True, text=True, capture_output=True, check=False)
    assert result.returncode == 0
    assert result.stdout == "Hello, Alice!\n"
    manifest = json.loads((ROOT / "evals/development-workflow/manifest.json").read_text())
    cfg = manifest["scenarios"]["feature-shout"]
    assert ids(observed(tool_events(command, result.stdout, result.returncode), tmp_path, cfg)) == set()


def test_text_echoed_or_read_or_claimed_is_not_execution_evidence(tmp_path):
    for command, output in (
        ("echo 'python3 app.py Alice'", "Hello, Alice!\n"),
        ("echo 'Hello, Alice!'", "Hello, Alice!\n"),
        ("cat app.py", "Hello, Alice!\n"),
    ):
        assert ids(observed(tool_events(command, output), tmp_path)) == set()
    events = [{"type": "result", "text": "python3 app.py Alice printed Hello, Alice!"}]
    assert ids(observed(events, tmp_path)) == set()


def test_conditional_nonexecution_and_ambiguous_output_remain_unconfirmed(tmp_path):
    not_run = tool_events("false && python3 app.py Alice", "", 1)
    ambiguous = tool_events(
        "python3 app.py Alice; python3 app.py Alice",
        "Hello, Alice!\n",
        0,
    )
    assert ids(observed(not_run, tmp_path)) == set()
    assert ids(observed(ambiguous, tmp_path)) == set()


def test_extra_arguments_do_not_satisfy_a_probe_with_different_inputs(tmp_path):
    facts = observed(tool_events("python3 app.py Alice World", "Hello, Alice!\n"), tmp_path)
    assert ids(facts) == set()


def test_semicolon_does_not_share_aggregate_status_with_earlier_command(tmp_path):
    facts = observed(tool_events("python3 app.py Alice; true", "Hello, Alice!\n"), tmp_path)
    assert ids(facts) == set()


def test_harness_reevaluate_reextracts_raw_trace_without_mutating_saved_evidence(tmp_path):
    from evals.harness.core import Harness

    source = tmp_path / "evidence.json"
    original = {
        "execution_status": "COMPLETED",
        "agent_execution_count": 1,
        "scenario": "feature-shout",
        "workflow_events": [
            {"kind": "preserved_behavior_observed", "index": 99, "probe_index": 0},
            {"kind": "target_check_passed", "index": 100},
        ],
        "tool_calls": [],
    }
    source.write_text(json.dumps(original), encoding="utf-8")
    events = [
        {"type": "tool_use", "name": "write_file", "input": {"path": str(tmp_path / "tests/test_app.py"), "content": "HELLO, ALICE! --shout\n"}},
        {"type": "tool_result", "name": "write_file", "output": json.dumps({"success": True})},
        {"type": "tool_use", "name": "write_file", "input": {"path": str(tmp_path / "app.py"), "content": "changed\n"}},
        {"type": "tool_result", "name": "write_file", "output": json.dumps({"success": True})},
    ] + tool_events("python3 -m pytest -q", "2 passed\n", 0)
    events += tool_events("python3 -m pytest -q", "2 passed\n", 0)
    events += tool_events("python3 app.py Alice", "Hello, Alice!\n", 0)
    trace = tmp_path / "raw.jsonl"
    trace.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
    trace_before = trace.read_bytes()
    evidence_before = source.read_bytes()
    cfg = {
        "current_behavior_probes": [probes()[1]],
        "preserved_behavior_probes": [probes()[1]],
        "behavior_probes": [{"command": ["python3", "app.py", "Alice"],
                             "exit_code": 0, "stdout": "Hello, Alice!\n"}],
    }
    trajectory_rules = {"requires_red": True, "current_probe_count": 1,
                        "preserved_probe_count": 1, "target_failure_signal": "expected failure"}
    reevaluated = Harness(consumer()).reevaluate(
        source, {"trajectory": trajectory_rules}, raw_trace_path=trace,
        scenario_cfg=cfg, fixture_path=tmp_path
    )
    assert reevaluated["reevaluated_from_raw_trace"] is True
    kinds = [item["kind"] for item in reevaluated["workflow_events"]]
    assert kinds.index("target_check_changed") < kinds.index("production_changed")
    assert "target_check_passed" in kinds
    assert "preserved_behavior_observed" in kinds
    assert [item["index"] for item in reevaluated["workflow_events"]] == sorted(
        item["index"] for item in reevaluated["workflow_events"]
    )
    trajectory = reevaluated["diagnostics"]["trajectory"]
    assert trajectory["status"] == "FAIL"
    assert "current observable behavior is UNCONFIRMED" in trajectory["reason"]
    assert "RED before production change is UNCONFIRMED" in trajectory["reason"]
    assert json.loads(source.read_text(encoding="utf-8")) == original
    assert source.read_bytes() == evidence_before
    assert trace.read_bytes() == trace_before


def test_malformed_raw_jsonl_is_rejected_with_line_diagnostic(tmp_path):
    from evals.harness.core import Harness

    trace = tmp_path / "broken.jsonl"
    trace.write_text('{"type":"result"}\\n{"type":', encoding="utf-8")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps({"execution_status": "COMPLETED", "scenario": "feature-shout"}))
    with pytest.raises(ValueError, match="line 1"):
        Harness(consumer()).reevaluate(
            evidence, {"trajectory": {}}, raw_trace_path=trace,
            scenario_cfg={}, fixture_path=tmp_path,
        )


def test_trajectory_does_not_reuse_post_change_check_as_pre_change_red(tmp_path):
    events = tool_events("python3 -m pytest -q", "1 failed\n", 1)
    events += [{"type": "tool_use", "name": "write_file", "input": {"path": str(tmp_path / "app.py"), "content": "changed"}},
               {"type": "tool_result", "name": "write_file", "output": json.dumps({"success": True})}]
    events += tool_events("python3 -m pytest -q", "2 passed\n", 0)
    facts = observed(events, tmp_path)
    evidence = {"execution_status": "COMPLETED", "tool_calls": [], "workflow_events": facts}
    result = consumer().evaluate_dimension_diagnostic(
        "trajectory", evidence,
        {"current_probe_count": 1, "preserved_probe_count": 0, "target_failure_signal": "expected failure"},
    )
    assert result["status"] == "FAIL"
    assert "RED" in result["reason"]


def test_semicolon_does_not_assign_final_status_to_an_earlier_test_command(tmp_path):
    hidden_failure = observed(tool_events("python3 -m pytest -q; true", "1 failed\\n", 0), tmp_path)
    confirmed_final_runner = observed(tool_events("true; python3 -m pytest -q", "2 passed\\n", 0), tmp_path)
    assert not any(item["kind"].startswith("target_check_") for item in hidden_failure)
    # The final pytest command's process status is observable, but without a
    # snapshot mapping collected tests to behavior it is not behavior evidence.
    assert not any(item["kind"] == "target_check_passed" for item in confirmed_final_runner)


def test_post_change_program_run_cannot_establish_pre_change_behavior(tmp_path):
    events = [
        {"type": "tool_use", "name": "write_file", "input": {"path": str(tmp_path / "app.py"), "content": "changed"}},
        {"type": "tool_result", "name": "write_file", "output": json.dumps({"success": True})},
    ] + tool_events("python3 app.py Alice", "Hello, Alice!\\n", 0)
    facts = observed(events, tmp_path)
    assert not any(item["kind"] == "current_behavior_observed" for item in facts)
