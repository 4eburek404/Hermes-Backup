from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "evals" / "flight-calendar-ics"
sys.path.insert(0, str(ROOT))


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_existing_ural_scenario_uses_supported_mail_wrapper_source():
    prompt = (EVAL / "prompt" / "ural-url-success.txt").read_text(encoding="utf-8")
    assert "https://tn-hgl.mckx.ru/?u=" in prompt
    assert "service.uralairlines.ru" in prompt


def test_aeroflot_replay_rejects_wrong_request_instead_of_returning_success_fixture():
    replay = load_module(EVAL / "replay" / "carrier_http.py", "mutation_audit_aeroflot_replay")
    fixture = EVAL / "fixtures" / "aeroflot-pnr-view-v3.json"
    with patch.dict(os.environ, {
        "FLIGHT_CALENDAR_EVAL_SCENARIO": "url-success",
        "FLIGHT_CALENDAR_EVAL_HTTP_FIXTURE": str(fixture),
    }):
        with pytest.raises(replay.TransportError):
            replay.request_raw("https://wrong.example/not-the-carrier-api", method="GET")


def test_ural_replay_rejects_wrong_query_or_missing_required_header():
    replay = load_module(EVAL / "replay" / "carrier_http.py", "mutation_audit_ural_replay")
    fixture = EVAL / "fixtures" / "ural" / "reservation.json"
    with patch.dict(os.environ, {
        "FLIGHT_CALENDAR_EVAL_SCENARIO": "ural-url-success",
        "FLIGHT_CALENDAR_EVAL_HTTP_FIXTURE": str(fixture),
    }):
        with pytest.raises(replay.TransportError):
            replay.request_raw(
                "https://ural-api.test/api/Reservation?wrong=value",
                method="GET",
                headers={"Accept": "application/json"},
            )


def test_outcome_fails_when_summary_is_semantically_wrong(tmp_path):
    manifest = json.loads((EVAL / "manifest.json").read_text(encoding="utf-8"))
    consumer_module = load_module(EVAL / "consumer.py", "mutation_audit_consumer")
    consumer = consumer_module.FlightCalendarIcsConsumer(EVAL, ROOT, manifest)
    evidence = consumer._run_reference_cli("ural-url-success")
    artifact = Path(evidence["artifact_evidence_path"])
    text = artifact.read_text(encoding="utf-8")
    text, count = re.subn(r"^SUMMARY:.*$", "SUMMARY:WRONG FLIGHT", text, flags=re.M)
    assert count == 2
    artifact.write_text(text, encoding="utf-8")
    evidence["artifact_observation"] = consumer._observe_ics(artifact)
    result = consumer.evaluate_dimension_diagnostic("outcome", evidence, {})
    assert result["status"] == "FAIL"
    assert "SUMMARY" in str(result["reason"])


def test_reevaluation_preserves_unversioned_historical_result_separately(tmp_path):
    manifest = json.loads((EVAL / "manifest.json").read_text(encoding="utf-8"))
    consumer_module = load_module(EVAL / "consumer.py", "mutation_audit_reevaluation_consumer")
    consumer = consumer_module.FlightCalendarIcsConsumer(EVAL, ROOT, manifest)
    batch_dir = tmp_path / "source-batch"
    run_dir = batch_dir / "runs" / "old-run"
    run_dir.mkdir(parents=True)
    evidence_path = run_dir / "evidence.json"
    score_path = run_dir / "score.json"
    evidence_path.write_text(json.dumps({"scenario": "ural-url-success", "run_id": "old-run"}))
    original_score = '{"score":{"outcome":"FAIL","trajectory":"PASS","privacy":"PASS"}}\n'
    score_path.write_text(original_score, encoding="utf-8")
    (batch_dir / "batch_manifest.json").write_text(json.dumps({
        "consumer": consumer.name,
        "runs": [{
            "run_id": "old-run",
            "scenario": "ural-url-success",
            "model": "historic-model",
            "provider": "historic-provider",
            "skill_version": "candidate",
            "evidence_path": str(evidence_path),
            "score_path": str(score_path),
            "score": {"outcome": "FAIL", "trajectory": "PASS", "privacy": "PASS"},
        }],
    }), encoding="utf-8")
    case = {
        "scenarios": ["ural-url-success"],
        "rules": {"ural-url-success": {}},
        "report": {},
    }
    output_dir = tmp_path / "reevaluation"
    batch = consumer.reevaluate_batch(batch_dir, case, output_dir)
    result = json.loads((output_dir / "runs" / "old-run" / "evaluation.json").read_text())
    assert result["historical_result"]["score"]["outcome"] == "FAIL"
    assert result["historical_result"]["reproducible"] is False
    assert "cannot be independently reproduced" in result["historical_result"]["notice"]
    assert "reevaluated_result" in result
    assert score_path.read_text(encoding="utf-8") == original_score
    report = Path(batch["report_path"]).read_text(encoding="utf-8")
    assert "REEVALUATION" in report


def test_outcome_rejects_media_that_does_not_bind_to_observed_artifact(tmp_path):
    manifest = json.loads((EVAL / "manifest.json").read_text(encoding="utf-8"))
    consumer_module = load_module(EVAL / "consumer.py", "mutation_audit_media_consumer")
    consumer = consumer_module.FlightCalendarIcsConsumer(EVAL, ROOT, manifest)
    evidence = consumer._run_reference_cli("ural-url-success")
    artifact = Path(evidence["artifact_evidence_path"])
    decoy = tmp_path / "decoy.ics"
    decoy.write_text(artifact.read_text(encoding="utf-8"), encoding="utf-8")
    evidence["final_answer"] = f"MEDIA:{decoy}"
    result = consumer.evaluate_dimension_diagnostic("outcome", evidence, {})
    assert result["status"] == "FAIL"
    assert "MEDIA" in str(result["reason"])
