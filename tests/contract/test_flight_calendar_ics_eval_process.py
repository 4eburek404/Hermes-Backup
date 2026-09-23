from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

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


def test_terminal_result_token_fields_are_preserved_in_saved_metrics(tmp_path):
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

    token_usage = {
        "input": 1234,
        "output": 567,
        "total": 2468,
        "cache_read": 89,
        "cache_write": 13,
    }
    stream = json.dumps(
        {"type": "result", "text": "Done.", "tokens": token_usage}
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
    assert saved_evidence["metrics"]["usage"] == token_usage
    raw_stream_path = run_dir / "raw_stream.jsonl"
    raw_stream_before = raw_stream_path.read_bytes()
    assert raw_stream_before == stream.encode()

    reevaluated = consumer.reevaluate_batch(
        tmp_path / "batch", case, tmp_path / "reevaluations"
    )
    assert reevaluated["agent_execution_count"] == 0
    assert reevaluated["runs"][0]["metrics"]["usage"] == token_usage
    assert raw_stream_path.read_bytes() == raw_stream_before


@pytest.mark.parametrize(
    ("tokens", "has_output"),
    [
        pytest.param(
            {"input": 91, "total": 91, "cache_read": 0, "cache_write": 0},
            False,
            id="output-missing",
        ),
        pytest.param(
            {"input": 91, "output": 0, "total": 91, "cache_read": 0, "cache_write": 0},
            True,
            id="output-measured-zero",
        ),
    ],
)
def test_missing_token_metric_remains_distinct_from_measured_zero(
    tmp_path, tokens, has_output
):
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
    stream = json.dumps({"type": "result", "text": "Done.", "tokens": tokens})

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
    usage = saved_evidence["metrics"]["usage"]
    assert saved_evidence["execution_status"] == "COMPLETED"
    assert usage == tokens
    assert ("output" in usage) is has_output
    if has_output:
        assert usage["output"] == 0
    assert (run_dir / "raw_stream.jsonl").read_bytes() == stream.encode()


def test_reevaluation_is_deterministic_and_does_not_launch_runtime(tmp_path):
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
    events = [
        {
            "type": "tool_use",
            "name": "terminal",
            "input": {"command": "flight_calendar_ics.py --json build --url https://example.test/booking"},
        },
        {
            "type": "tool_result",
            "name": "terminal",
            "output": json.dumps({"output": json.dumps({"ok": True}), "exit_code": 0}),
        },
        {"type": "result", "text": "Done."},
    ]
    stream = "\n".join(json.dumps(event) for event in events)

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
        initial_batch = Harness(consumer).run(case, tmp_path / "batch")

    initial = initial_batch["runs"][0]
    reevaluation_results = []
    with (
        patch.object(
            module.subprocess,
            "run",
            side_effect=AssertionError("runtime/provider process launched during re-evaluation"),
        ),
        patch.object(
            module.FlightCalendarIcsConsumer,
            "_build_skill_root",
            side_effect=AssertionError("skill setup invoked during re-evaluation"),
        ),
        patch.object(
            module.FlightCalendarIcsConsumer,
            "_seed_timezone_cache",
            side_effect=AssertionError("fixture setup invoked during re-evaluation"),
        ),
        patch.object(
            module.FlightCalendarIcsConsumer,
            "_make_home",
            side_effect=AssertionError("runtime home created during re-evaluation"),
        ),
    ):
        for index in (1, 2):
            batch = consumer.reevaluate_batch(
                tmp_path / "batch", case, tmp_path / f"reevaluation-{index}"
            )
            reevaluation_results.append(batch["runs"][0])
            assert batch["agent_execution_count"] == 0

    def semantic_result(run):
        return {
            "execution_status": run["execution_status"],
            "score": run["score"],
            "diagnostics": run["diagnostics"],
            "metrics": run["metrics"],
            "final_answer": run["final_answer"],
        }

    first, second = reevaluation_results
    assert semantic_result(first) == semantic_result(second)
    assert first["execution_status"] == initial["execution_status"]
    assert set(first["score"]) == {"outcome", "trajectory", "privacy"}


def test_reevaluation_preserves_source_evidence_and_writes_derived_result_separately(tmp_path):
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
    artifact_source = tmp_path / "runtime-result.ics"
    artifact_source.write_text(
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "BEGIN:VEVENT\r\n"
        "DTSTART:20261110T100000Z\r\n"
        "DTEND:20261110T110000Z\r\n"
        "DESCRIPTION:Saved source artifact\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n",
        encoding="utf-8",
    )
    events = [
        {
            "type": "tool_use",
            "name": "terminal",
            "input": {"command": "flight_calendar_ics.py --json build --url https://example.test/booking"},
        },
        {
            "type": "tool_result",
            "name": "terminal",
            "output": json.dumps({"output": json.dumps({"ok": True}), "exit_code": 0}),
        },
        {"type": "result", "text": "Done."},
    ]
    events[-1]["text"] = f"MEDIA:{artifact_source}"
    stream = "\n".join(json.dumps(event) for event in events)
    source_batch_dir = tmp_path / "source-batch"

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
        initial_batch = Harness(consumer).run(case, source_batch_dir)

    initial = initial_batch["runs"][0]
    run_dir = Path(initial["evidence_path"]).parent
    source_evidence_path = Path(initial["evidence_path"])
    original_score_path = Path(initial["score_path"])
    source_files = {
        "raw runtime stream": run_dir / "raw_stream.jsonl",
        "raw runtime stderr": run_dir / "raw_stderr.txt",
        "captured terminal answer": run_dir / "raw_final_answer.txt",
        "execution-produced artifact": run_dir / "artifact.ics",
        "normalized source evidence": source_evidence_path,
        "execution metadata": run_dir / "metadata.json",
    }
    assert all(path.is_file() for path in source_files.values())
    source_bytes_before = {
        name: path.read_bytes() for name, path in source_files.items()
    }
    original_score_before = original_score_path.read_bytes()
    original_report_path = Path(initial_batch["report_path"])
    original_report_before = original_report_path.read_bytes()

    for index in (1, 2):
        output_dir = tmp_path / f"reevaluation-{index}"
        reevaluated_batch = consumer.reevaluate_batch(
            source_batch_dir, case, output_dir
        )
        reevaluated = reevaluated_batch["runs"][0]
        evaluation_path = (
            output_dir / "runs" / initial["run_id"] / "evaluation.json"
        )

        assert evaluation_path.is_file()
        assert evaluation_path != source_evidence_path
        evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
        assert evaluation["source_evidence"] == str(source_evidence_path)
        assert evaluation["execution_status"] == reevaluated["execution_status"]
        assert evaluation["score"] == reevaluated["score"]
        assert evaluation["diagnostics"] == reevaluated["diagnostics"]
        assert Path(reevaluated["evidence_path"]) == source_evidence_path
        assert Path(reevaluated_batch["report_path"]).parent == output_dir
        assert Path(reevaluated_batch["report_path"]).is_file()
        assert Path(reevaluated_batch["report_path"]) != original_report_path

        for name, path in source_files.items():
            assert path.read_bytes() == source_bytes_before[name], name
        assert original_score_path.read_bytes() == original_score_before
        assert original_report_path.read_bytes() == original_report_before
        assert json.loads(original_score_path.read_text(encoding="utf-8"))["score"] == initial["score"]


def test_persisted_evaluator_provenance_tracks_effective_inputs(tmp_path):
    _, module = make_consumer()
    run_eval = load_run_eval_module()
    manifest = json.loads((EVAL / "manifest.json").read_text(encoding="utf-8"))
    eval_root = tmp_path / "eval-root"
    (eval_root / "expected").mkdir(parents=True)
    for relative in (
        manifest["scenarios"]["url-success"]["prompt"],
        manifest["scenarios"]["url-success"]["fixture"],
    ):
        target = eval_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((EVAL / relative).read_bytes())

    oracle_relative = manifest["scenarios"]["url-success"]["oracle"]
    oracle_path = eval_root / oracle_relative
    oracle_a = {
        "expected_event_count": 1,
        "events": [
            {
                "dtstart": "20261110T100000Z",
                "dtend": "20261110T110000Z",
                "description_fragments": ["Saved source artifact"],
            }
        ],
        "privacy_forbidden_final_answer": [],
    }
    oracle_b = {
        **oracle_a,
        "privacy_forbidden_final_answer": ["Done."],
    }
    oracle_path.write_text(json.dumps(oracle_a, indent=2) + "\n", encoding="utf-8")
    consumer = module.FlightCalendarIcsConsumer(eval_root, ROOT, manifest)
    case = run_eval.build_case(
        manifest,
        EVAL,
        runtime_version="test-runtime",
        selected_scenarios=["url-success"],
    )
    case["models"] = [{"model": "test-model", "provider": "test-provider"}]

    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    artifact_source = tmp_path / "runtime-result.ics"
    artifact_source.write_text(
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "BEGIN:VEVENT\r\n"
        "DTSTART:20261110T100000Z\r\n"
        "DTEND:20261110T110000Z\r\n"
        "DESCRIPTION:Saved source artifact\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n",
        encoding="utf-8",
    )
    command = "flight_calendar_ics.py --json build --url https://example.test/booking"
    events = [
        {"type": "tool_use", "name": "terminal", "input": {"command": command}},
        {
            "type": "tool_result",
            "name": "terminal",
            "output": json.dumps({"output": json.dumps({"ok": True}), "exit_code": 0}),
        },
        {"type": "result", "text": f"MEDIA:{artifact_source} Done."},
    ]
    stream = "\n".join(json.dumps(event) for event in events)
    source_batch_dir = tmp_path / "source-batch"
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
        initial_batch = Harness(consumer).run(case, source_batch_dir)

    initial = initial_batch["runs"][0]
    source_evidence_path = Path(initial["evidence_path"])
    source_bytes = {
        "raw_stream": (source_evidence_path.parent / "raw_stream.jsonl").read_bytes(),
        "evidence": source_evidence_path.read_bytes(),
        "artifact": (source_evidence_path.parent / "artifact.ics").read_bytes(),
    }

    def reevaluate(name):
        output_dir = tmp_path / name
        batch = consumer.reevaluate_batch(source_batch_dir, case, output_dir)
        run = batch["runs"][0]
        evaluation_path = output_dir / "runs" / initial["run_id"] / "evaluation.json"
        assert evaluation_path.is_file()
        evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
        assert evaluation["source_evidence"] == str(source_evidence_path)
        assert Path(run["evidence_path"]) == source_evidence_path
        return run, evaluation

    alternate_relative = "expected/alternate-url-success.json"
    (eval_root / alternate_relative).write_text(
        json.dumps(oracle_a, indent=2) + "\n", encoding="utf-8"
    )
    reevaluated = []
    with patch.object(
        module.subprocess,
        "run",
        side_effect=AssertionError("agent/runtime execution during re-evaluation"),
    ):
        run_a1, evaluation_a1 = reevaluate("reevaluation-a1")
        run_a2, evaluation_a2 = reevaluate("reevaluation-a2")
        consumer.manifest["scenarios"]["url-success"]["oracle"] = alternate_relative
        run_a3, evaluation_a3 = reevaluate("reevaluation-a-alternate-path")
        consumer.manifest["scenarios"]["url-success"]["oracle"] = oracle_relative
        oracle_path.write_text(json.dumps(oracle_b, indent=2) + "\n", encoding="utf-8")
        run_b, evaluation_b = reevaluate("reevaluation-b")
        reevaluated.extend(
            [
                (run_a1, evaluation_a1),
                (run_a2, evaluation_a2),
                (run_a3, evaluation_a3),
                (run_b, evaluation_b),
            ]
        )

    assert run_a1["score"]["privacy"] == "PASS"
    assert run_b["score"]["privacy"] == "FAIL"
    assert source_evidence_path.read_bytes() == source_bytes["evidence"]
    assert (source_evidence_path.parent / "raw_stream.jsonl").read_bytes() == source_bytes["raw_stream"]
    assert (source_evidence_path.parent / "artifact.ics").read_bytes() == source_bytes["artifact"]

    initial_score = json.loads(Path(initial["score_path"]).read_text(encoding="utf-8"))
    provenance_records = [
        initial_score.get("evaluator_provenance"),
        *(evaluation.get("evaluator_provenance") for _, evaluation in reevaluated),
    ]
    assert all(isinstance(item, dict) for item in provenance_records), (
        "persisted score/evaluation is missing effective evaluator provenance",
        provenance_records,
    )
    provenance_a1, provenance_a2, provenance_a3, provenance_b = provenance_records[1:]
    assert provenance_records[0] == provenance_a1 == provenance_a2 == provenance_a3
    assert provenance_a1["effective_rules"] == case["rules"]["url-success"]
    assert provenance_a1["effective_oracle"] == oracle_a
    assert provenance_b["effective_rules"] == case["rules"]["url-success"]
    assert provenance_b["effective_oracle"] == oracle_b
    assert provenance_a1["identity_sha256"] == provenance_a2["identity_sha256"]
    assert provenance_a1["identity_sha256"] == provenance_a3["identity_sha256"]
    assert provenance_a1["implementation_sha256"] == provenance_b["implementation_sha256"]
    assert provenance_a1["rules_sha256"] == provenance_b["rules_sha256"]
    assert provenance_a1["oracle_sha256"] != provenance_b["oracle_sha256"]
    assert provenance_a1["identity_sha256"] != provenance_b["identity_sha256"]


def test_fixture_failure_is_not_reported_as_pass(tmp_path, capsys):
    consumer, _ = make_consumer()
    run_eval = load_run_eval_module()
    case = run_eval.build_case(
        consumer.manifest,
        EVAL,
        runtime_version="test-runtime",
        selected_scenarios=["url-success"],
    )
    case["models"] = [{"model": "test-model", "provider": "test-provider"}]
    case["scenario_metadata"]["url-success"]["fixture_version"] = "stale-fixture-identity"

    batch = Harness(consumer).run(
        case, tmp_path / "batch", progress=run_eval._progress
    )
    run = batch["runs"][0]
    progress = capsys.readouterr().out

    assert run["execution_status"] == "FIXTURE_FAILURE"
    assert run["comparable"] is False
    assert run["agent_started"] is False
    assert batch["agent_execution_count"] == 0
    assert run["score"] == {
        "outcome": "UNDEFINED",
        "trajectory": "UNDEFINED",
        "privacy": "UNDEFINED",
    }
    assert run_eval._result_label(run) == "FIXTURE_FAILURE"
    assert "FIXTURE_FAILURE" in progress
    assert "PASS" not in progress


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


@pytest.mark.parametrize(
    ("has_terminal_result", "expected_status"),
    [(True, "AGENT_FAILURE"), (False, "RUNTIME_FAILURE")],
)
def test_nonzero_exit_status_matches_saved_evidence_reevaluation(
    tmp_path, has_terminal_result, expected_status
):
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

    final_answer = "The agent could not complete this request." if has_terminal_result else ""
    command = "flight_calendar_ics.py --json build --url https://example.test/booking"
    events = [
        {"type": "tool_use", "name": "terminal", "input": {"command": command}},
        {
            "type": "tool_result",
            "name": "terminal",
            "output": json.dumps(
                {"output": json.dumps({"ok": False}), "exit_code": 1}
            ),
        },
    ]
    if has_terminal_result:
        events.append({"type": "result", "text": final_answer})
    stream = "\n".join(json.dumps(event) for event in events)

    with (
        patch.object(module.FlightCalendarIcsConsumer, "_build_skill_root", return_value=(skill_root, {})),
        patch.object(module.FlightCalendarIcsConsumer, "_seed_timezone_cache"),
        patch.object(module.FlightCalendarIcsConsumer, "_make_home"),
        patch.object(
            module.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 1, stdout=stream, stderr=""),
        ),
    ):
        batch = Harness(consumer).run(case, tmp_path / "batch")

    initial = batch["runs"][0]
    run_dir = Path(initial["evidence_path"]).parent
    saved_evidence = json.loads((run_dir / "evidence.json").read_text())
    reevaluated = consumer.reevaluate_batch(
        tmp_path / "batch", case, tmp_path / "reevaluations"
    )["runs"][0]
    assert reevaluated["execution_status"] == initial["execution_status"]
    assert initial["execution_status"] == expected_status
    assert saved_evidence["event_summary"]["has_result"] is has_terminal_result
    assert saved_evidence["final_answer"] == final_answer
    assert len(saved_evidence["cli_attempts"]) == 1
    assert reevaluated["final_answer"] == initial["final_answer"]


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
