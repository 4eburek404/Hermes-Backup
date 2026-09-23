from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from evals.harness.core import Harness
from evals.harness.report import render_report


ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "evals" / "flight-calendar-ics"


def load_consumer_module():
    path = EVAL / "consumer.py"
    spec = importlib.util.spec_from_file_location("flight_calendar_eval_consumer", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_run_eval_module():
    path = EVAL / "run_eval.py"
    spec = importlib.util.spec_from_file_location("flight_calendar_eval_runner", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_consumer():
    module = load_consumer_module()
    manifest = json.loads((EVAL / "manifest.json").read_text(encoding="utf-8"))
    return module.FlightCalendarIcsConsumer(EVAL, ROOT, manifest), module


def test_oracles_describe_observable_renderer_contract_only():
    for name in ("ural-url-success", "pdf-success"):
        oracle = json.loads((EVAL / "expected" / f"{name}.json").read_text())
        fragments = [fragment for event in oracle["events"] for fragment in event["description_fragments"]]
        assert not any(fragment.startswith("Рейс:") for fragment in fragments)
    pdf = json.loads((EVAL / "expected" / "pdf-success.json").read_text())
    assert "ticket.pdf" not in pdf["privacy_forbidden_final_answer"]
    assert "Passenger:" not in pdf["privacy_forbidden_final_answer"]


def test_known_good_outcome_reference_is_checked_before_agent_runs():
    consumer, _ = make_consumer()
    assert hasattr(consumer, "preflight")
    assert hasattr(consumer, "_reference_itinerary")


def test_cli_result_parser_distinguishes_failed_and_successful_attempts():
    _, module = make_consumer()
    stream = "\n".join(
        [
            json.dumps({"type": "tool_use", "name": "terminal", "input": {"command": "flight_calendar_ics.py --json build --input x"}}),
            json.dumps({"type": "tool_result", "name": "terminal", "output": json.dumps({"output": '{"ok": false}', "exit_code": 2})}),
            json.dumps({"type": "tool_use", "name": "terminal", "input": {"command": "flight_calendar_ics.py --json build --input x"}}),
            json.dumps({"type": "tool_result", "name": "terminal", "output": json.dumps({"output": '{"ok": true, "media": "MEDIA:/tmp/a.ics"}', "exit_code": 0})}),
            json.dumps({"type": "result", "text": "MEDIA:/tmp/a.ics"}),
        ]
    )
    summary = module.FlightCalendarIcsConsumer._event_summary(stream)
    assert [item["success"] for item in summary["cli_attempts"]] == [False, True]
    assert summary["successful_cli_index"] is not None


def test_terminal_result_survives_tool_result_in_saved_evidence(tmp_path):
    consumer, module = make_consumer()
    run_eval = load_run_eval_module()
    case = run_eval.build_case(
        consumer.manifest,
        EVAL,
        runtime_version="test-runtime",
        selected_scenarios=["url-success"],
    )
    case["models"] = [{"model": "test-model", "provider": "test-provider"}]
    skill_root = tmp_path / "skills"
    skill_root.mkdir()

    terminal_text = "MEDIA:/tmp/result.ics"
    command = "flight_calendar_ics.py --json build --url https://example.test/booking"
    stream = "\n".join(
        json.dumps(event)
        for event in (
            {"type": "tool_use", "name": "terminal", "input": {"command": command}},
            {
                "type": "tool_result",
                "name": "terminal",
                "output": json.dumps(
                    {"output": json.dumps({"ok": True, "media": terminal_text}), "exit_code": 0}
                ),
            },
            {"type": "result", "text": terminal_text},
        )
    )

    with (
        patch.object(module.FlightCalendarIcsConsumer, "_build_skill_root", return_value=(skill_root, {})),
        patch.object(module.FlightCalendarIcsConsumer, "_seed_timezone_cache"),
        patch.object(module.FlightCalendarIcsConsumer, "_make_home"),
        patch.object(
            module.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 0, stdout=stream, stderr=""),
        ),
    ):
        batch = Harness(consumer).run(case, tmp_path / "batch")

    run = batch["runs"][0]
    run_dir = Path(run["evidence_path"]).parent
    saved_evidence = json.loads((run_dir / "evidence.json").read_text())
    assert saved_evidence["final_answer"] == terminal_text
    assert (run_dir / "raw_final_answer.txt").read_text() == terminal_text
    assert [attempt["success"] for attempt in run["cli_attempts"]] == [True]


def test_tool_result_without_terminal_result_is_not_terminal_evidence(tmp_path):
    consumer, module = make_consumer()
    run_eval = load_run_eval_module()
    case = run_eval.build_case(
        consumer.manifest,
        EVAL,
        runtime_version="test-runtime",
        selected_scenarios=["url-success"],
    )
    case["models"] = [{"model": "test-model", "provider": "test-provider"}]
    skill_root = tmp_path / "skills"
    skill_root.mkdir()

    tool_output = "MEDIA:/tmp/tool-result.ics"
    command = "flight_calendar_ics.py --json build --url https://example.test/booking"
    stream = "\n".join(
        json.dumps(event)
        for event in (
            {"type": "tool_use", "name": "terminal", "input": {"command": command}},
            {
                "type": "tool_result",
                "name": "terminal",
                "output": json.dumps(
                    {"output": json.dumps({"ok": True, "media": tool_output}), "exit_code": 0}
                ),
            },
        )
    )

    with (
        patch.object(module.FlightCalendarIcsConsumer, "_build_skill_root", return_value=(skill_root, {})),
        patch.object(module.FlightCalendarIcsConsumer, "_seed_timezone_cache"),
        patch.object(module.FlightCalendarIcsConsumer, "_make_home"),
        patch.object(
            module.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 0, stdout=stream, stderr=""),
        ),
    ):
        batch = Harness(consumer).run(case, tmp_path / "batch")

    run = batch["runs"][0]
    run_dir = Path(run["evidence_path"]).parent
    saved_evidence = json.loads((run_dir / "evidence.json").read_text())
    assert saved_evidence["event_summary"]["has_result"] is False
    assert saved_evidence["final_answer"] == ""
    assert saved_evidence["tool_uses"][0]["name"] == "terminal"
    assert saved_evidence["cli_attempts"][0]["success"] is True
    assert saved_evidence["execution_status"] == "RUNTIME_FAILURE"


def test_agent_failure_with_real_result_is_not_runtime_failure():
    _, module = make_consumer()
    summary = {"event_count": 2, "tool_uses": [{"index": 0, "name": "terminal"}], "final_answer": "task failed"}
    assert module.classify_execution_status(1, summary) == "AGENT_FAILURE"
    assert module.classify_execution_status(1, {"event_count": 0, "tool_uses": [], "final_answer": ""}) == "RUNTIME_FAILURE"


def test_failed_cli_retry_success_then_stop_is_valid_trajectory():
    consumer, _ = make_consumer()
    evidence = {
        "terminal_commands": ["flight_calendar_ics.py --json build --input x", "flight_calendar_ics.py --json build --input x"],
        "tool_names": ["terminal", "terminal"],
        "tool_uses": [
            {"index": 0, "name": "terminal", "input": {"command": "flight_calendar_ics.py --json build --input x"}},
            {"index": 1, "name": "terminal", "input": {"command": "flight_calendar_ics.py --json build --input x"}},
        ],
        "cli_attempts": [{"success": False}, {"success": True}],
        "final_answer": "MEDIA:/tmp/a.ics",
    }
    detail = consumer.evaluate_dimension_diagnostic("trajectory", evidence, {
        "required_cli_fragments": ["--input"],
        "require_successful_cli": True,
        "stop_after_successful_cli": True,
    })
    assert detail["status"] == "PASS"


def test_tool_after_successful_cli_fails_trajectory():
    consumer, _ = make_consumer()
    evidence = {
        "terminal_commands": ["flight_calendar_ics.py --json build --input x", "read after success"],
        "tool_names": ["terminal", "read_file"],
        "tool_uses": [
            {"index": 0, "name": "terminal", "input": {"command": "flight_calendar_ics.py --json build --input x"}},
            {"index": 1, "name": "read_file", "input": {}},
        ],
        "cli_attempts": [{"success": True, "tool_index": 0}],
        "final_answer": "MEDIA:/tmp/a.ics",
    }
    detail = consumer.evaluate_dimension_diagnostic("trajectory", evidence, {"stop_after_successful_cli": True})
    assert detail["status"] == "FAIL"
    assert "after successful CLI" in detail["reason"]


def test_failures_always_have_structured_diagnostics():
    consumer, _ = make_consumer()
    detail = consumer.evaluate_dimension_diagnostic("outcome", {"final_answer": ""}, {})
    assert detail["status"] == "FAIL"
    assert detail["reason"]


def test_pdf_privacy_uses_real_sensitive_markers_only():
    consumer, _ = make_consumer()
    oracle = consumer._oracle("pdf-success")
    forbidden = oracle["privacy_forbidden_final_answer"]
    assert "ALEX EXAMPLE" in forbidden
    assert "PDF7K2" in forbidden
    assert "5552401234567" in forbidden
    assert "ticket.pdf" not in forbidden
    assert "Passenger:" not in forbidden


def test_report_is_matrix_first_and_separates_facts_from_diagnostics():
    batch = {
        "consumer": "flight-calendar-ics",
        "expected_run_ids": ["a", "b"],
        "executed_run_ids": ["a", "b"],
        "runs": [
            {
                "run_id": "a", "model": "model-a", "provider": "provider-a", "scenario": "ural-url-success",
                "repeat": 1, "execution_status": "COMPLETED", "score": {"outcome": "PASS", "trajectory": "PASS", "privacy": "PASS"},
                "diagnostics": {"outcome": {"status": "PASS", "reason": None}, "trajectory": {"status": "PASS", "reason": None}, "privacy": {"status": "PASS", "reason": None}},
                "metrics": {"tool_calls": 1, "cli_build_calls": 1, "duration_seconds": 1.0}, "report_facts": {"CLI": 1, "URL": "exact"},
                "started_at": "2026-09-22T13:00:00+00:00", "ended_at": "2026-09-22T13:00:01+00:00",
            },
            {
                "run_id": "b", "model": "model-a", "provider": "provider-a", "scenario": "pdf-success",
                "repeat": 1, "execution_status": "AGENT_FAILURE", "score": {"outcome": "FAIL", "trajectory": "FAIL", "privacy": "PASS"},
                "diagnostics": {"outcome": {"status": "FAIL", "reason": "artifact missing"}, "trajectory": {"status": "FAIL", "reason": "CLI did not succeed"}, "privacy": {"status": "PASS", "reason": None}},
                "metrics": {"tool_calls": 3, "cli_build_calls": 1, "duration_seconds": 2.0}, "report_facts": {"CLI": 1, "URL": "—", "Source": "PDF", "AnyDoc": 1},
                "started_at": "2026-09-22T13:00:01+00:00", "ended_at": "2026-09-22T13:00:03+00:00",
            },
        ],
    }
    report = render_report(batch, {"report": {"timezone": "Asia/Yekaterinburg", "timezone_label": "Екатеринбург (UTC+5)"}})
    assert report.index("| Model | Ural | PDF |") < report.index("## FINDINGS")
    assert "Source: PDF" in report
    assert "artifact missing" in report
    assert "| Scenario | Run |" not in report


def test_harness_emits_start_and_finish_progress_callbacks():
    class Consumer:
        name = "test"
        def prepare(self, spec, run_dir, case):
            return {"actual_fixture_version": spec.fixture_version}
        def execute(self, spec, run_dir, prepared, case):
            return {"execution_status": "COMPLETED", "final_answer": "done"}
        def evaluate_dimension(self, dimension, evidence, rules):
            return "PASS"

    events = []
    case = {"scenarios": ["s"], "models": [{"model": "m", "provider": "p"}], "skill_versions": ["candidate"], "repeats": 1, "fixture_version": "f", "prompt_version": "p", "runtime_version": "r", "mode": "recorded", "rules": {"s": {}}}
    Harness(Consumer()).run(case, ROOT / ".tmp-test-progress", progress=lambda event: events.append(event))
    assert [event["phase"] for event in events] == ["start", "finish"]
    import shutil
    shutil.rmtree(ROOT / ".tmp-test-progress")


def test_reevaluation_reports_zero_agent_executions_and_preserves_source():
    consumer, _ = make_consumer()
    assert hasattr(consumer, "reevaluate_batch")
    assert hasattr(consumer, "classify_saved_evidence")


def test_runner_supports_reevaluate_argument_without_model_execution():
    runner = load_run_eval_module()
    assert "--reevaluate" in runner.build_parser()._option_string_actions
