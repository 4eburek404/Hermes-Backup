from __future__ import annotations

import importlib.util
import json
from pathlib import Path

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


def observed(events, tmp_path):
    (tmp_path / "app.py").write_text("print('fixture')\n", encoding="utf-8")
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "tests/test_app.py").write_text("assert True\n", encoding="utf-8")
    cfg = {
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


def test_separate_and_unambiguous_and_chains_prove_same_invocations(tmp_path):
    separate = tool_events("python3 app.py Alice --shout", "HELLO, ALICE!\n")
    separate += tool_events("python3 app.py Alice", "Hello, Alice!\n")
    separate += tool_events("python3 app.py", "Hello, World!\n")
    combined = tool_events(
        "python3 app.py Alice --shout && python3 app.py Alice && python3 app.py",
        "HELLO, ALICE!\nHello, Alice!\nHello, World!\n",
    )
    assert ids(observed(separate, tmp_path)) == {0, 1, 2}
    assert ids(observed(combined, tmp_path)) == {0, 1, 2}


def test_default_invocation_is_distinct_from_explicit_world(tmp_path):
    default = observed(tool_events("python3 app.py", "Hello, World!\n"), tmp_path)
    explicit = observed(tool_events("python3 app.py World", "Hello, World!\n"), tmp_path)
    assert 2 in ids(default) and 3 not in ids(default)
    assert 3 in ids(explicit) and 2 not in ids(explicit)


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
        {"type": "tool_use", "name": "write_file", "input": {"path": str(tmp_path / "app.py"), "content": "changed"}},
        {"type": "tool_result", "name": "write_file", "output": json.dumps({"success": True})},
    ] + tool_events("python3 -m pytest -q", "2 passed\\n", 0)
    trace = tmp_path / "raw.jsonl"
    trace.write_text("\\n".join(json.dumps(event) for event in events) + "\\n", encoding="utf-8")
    cfg = {
        "current_behavior_probes": [probes()[1]],
        "preserved_behavior_probes": [probes()[1]],
        "behavior_probes": [{"command": ["python3", "app.py", "Alice"],
                             "exit_code": 0, "stdout": "Hello, Alice!\\n"}],
    }
    trajectory_rules = {"requires_red": True, "current_probe_count": 1,
                        "preserved_probe_count": 1, "target_failure_signal": "expected failure"}
    reevaluated = Harness(consumer()).reevaluate(
        source, {"trajectory": trajectory_rules}, raw_trace_path=trace,
        scenario_cfg=cfg, fixture_path=tmp_path
    )
    assert reevaluated["reevaluated_from_raw_trace"] is True
    assert not any(item["kind"] == "preserved_behavior_observed"
                   for item in reevaluated["workflow_events"])
    trajectory = reevaluated["diagnostics"]["trajectory"]
    assert trajectory["status"] == "FAIL"
    assert "RED before production change is UNCONFIRMED" in trajectory["reason"]
    assert json.loads(source.read_text(encoding="utf-8")) == original


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
    assert any(item["kind"] == "target_check_passed" for item in confirmed_final_runner)


def test_post_change_program_run_cannot_establish_pre_change_behavior(tmp_path):
    events = [
        {"type": "tool_use", "name": "write_file", "input": {"path": str(tmp_path / "app.py"), "content": "changed"}},
        {"type": "tool_result", "name": "write_file", "output": json.dumps({"success": True})},
    ] + tool_events("python3 app.py Alice", "Hello, Alice!\\n", 0)
    facts = observed(events, tmp_path)
    assert not any(item["kind"] == "current_behavior_observed" for item in facts)
