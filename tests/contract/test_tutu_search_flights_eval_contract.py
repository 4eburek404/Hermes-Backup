"""Recorded Tutu agent-eval outcome contract and mutation proof."""
from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

from evals.harness.core import evaluate_dimension_details, evaluate_dimensions
from evals.harness.skill_source import materialize_skill_source


ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "evals" / "tutu-search-flights"
FIXTURE = EVAL / "fixtures" / "baseline.json"
CONSUMER_PATH = EVAL / "consumer.py"


def load_consumer():
    spec = importlib.util.spec_from_file_location("tutu_search_flights_consumer", CONSUMER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = json.loads((EVAL / "manifest.json").read_text(encoding="utf-8"))
    return module.TutuSearchFlightsConsumer(EVAL, ROOT, manifest, hermes_command=["hermes"])


def evidence_for(answer: str) -> dict:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return {
        "scenario": "search-results-reflect-tutu",
        "final_answer": answer,
        "recorded_tutu_result": fixture,
        "semantic_judge": {
            "status": "PASS",
            "verdict": "PASS",
            "claims": [{"claim": "recorded answer", "supported": True}],
            "model": "contract-test-double",
        },
    }


def test_outcome_accepts_grounded_answer_and_rejects_unsupported_claim_mutations():
    consumer = load_consumer()
    grounded = (
        "В выдаче есть рейс DP-6949 авиакомпании Победа: вылет в 19:25, "
        "тариф «Базовый» стоит 4 446,87 ₽."
    )
    mutations = {
        "flight": " Также доступен рейс SU-9999 авиакомпании Аэрофлот.",
        "flight_association": " Рейс DP-6949 — это S7-2055.",
        "carrier": " Рейс DP-6949 выполняет авиакомпания S7 Airlines.",
        "price": " Для рейса DP-6949 цена составляет 1 ₽.",
        "variant_price": " Для рейса DP-6949 по тарифу «Максимум» цена составляет 4 446,87 ₽.",
        "fare": " Для рейса DP-6949 доступен тариф «Бизнес Плюс».",
        "fare_unquoted": " Для рейса DP-6949 доступен тариф Бизнес Плюс.",
        "baggage": " Для рейса DP-6949 по тарифу «Базовый» включён багаж 20 кг.",
        "time": " Рейс DP-6949 вылетает в 11:05.",
        "date": " Для рейса DP-6949 дата вылета 2026-10-16.",
        "duration": " Рейс DP-6949 длится 48 часов.",
    }

    grounded_score = evaluate_dimensions(consumer, evidence_for(grounded), {})
    assert grounded_score["outcome"] == "PASS"
    for field, mutation in mutations.items():
        details = evaluate_dimension_details(consumer, evidence_for(grounded + mutation), {})
        assert details["outcome"]["status"] == "FAIL", field
        reason = details["outcome"]["reason"] or ""
        assert {
            "flight": "unsupported flight identifier",
            "flight_association": "unsupported flight association",
            "carrier": "unsupported carrier claim",
            "price": "price not present",
            "variant_price": "price not present",
            "fare": "fare name not present",
            "fare_unquoted": "fare name not present",
            "baggage": "baggage quantity is not confirmed",
            "time": "time not present in Tutu result",
            "date": "date not present in Tutu result",
            "duration": "duration not present in Tutu result",
        }[field] in reason, (field, reason)


def test_semantic_judge_cannot_return_fail_without_a_claim_level_failure():
    consumer = load_consumer()
    assert consumer._semantic_judge_status({"verdict": "PASS", "claims": [{"supported": True}]}) == "PASS"
    assert consumer._semantic_judge_status({"verdict": "FAIL", "claims": [{"supported": False}]}) == "FAIL"
    assert consumer._semantic_judge_status({"verdict": "FAIL", "claims": [{"supported": True}]}) == "ERROR"


def test_real_fare_class_and_exchange_window_are_not_misread_as_claims():
    consumer = load_consumer()
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    answer = (
        "Рейс DP-6949: тариф «Выгодный», обмен доступен за 48 часов до вылета. "
        "Также показаны тарифы бизнес-класса. Тарифы и условия такие же, как у S7-2055."
    )
    assert consumer._outcome_issues(answer, fixture) == []


def test_trajectory_accepts_one_served_call_after_a_recorded_request_mismatch():
    consumer = load_consumer()
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    expected = fixture["arguments"]
    served = {
        "host": "mcp.tutu.ru",
        "path": "/mcp",
        "http_method": "POST",
        "jsonrpc_method": "tools/call",
        "tool_name": "search_avia",
        "arguments": expected,
        "replay_status": "fixture-served",
    }
    rejected_attempt = {
        **served,
        "arguments": {**expected, "passengers": {"adults": 1}},
        "replay_status": "request-mismatch",
    }
    command = '"$PYTHON" tutu_search_flights.py \'{"origin":"Москва"}\''
    evidence = {
        "tool_names": ["terminal"],
        "terminal_commands": [command],
        "terminal_invocations": [{"command": command, "success": True, "result_index": 3}],
        "final_event_index": 4,
        "mcp_boundary_requests": [rejected_attempt, served],
        "requested_search_arguments": expected,
        "actual_search_arguments": expected,
        "blocked_tutu_egress_attempts": [],
    }
    rules = consumer.manifest["scenarios"]["search-results-reflect-tutu"]["evaluation"]["trajectory"]
    assert consumer.evaluate_dimension_diagnostic("trajectory", evidence, rules)["status"] == "PASS"


def test_terminal_trace_recognizes_successful_structured_skill_cli_result():
    consumer = load_consumer()
    events = [
        {"type": "tool_use", "name": "terminal", "input": {"command": '"$PYTHON" tutu_search_flights.py ...'}},
        {
            "type": "tool_result",
            "name": "terminal",
            "is_error": False,
            "output": json.dumps({"output": json.dumps({"offers": [{"flight_number": "DP-6949"}]}), "exit_code": 0, "error": None}),
        },
        {"type": "result", "text": "done"},
    ]
    summary = consumer._event_summary("\n".join(json.dumps(event) for event in events))
    assert summary["terminal_invocations"][0]["success"] is True


def test_recorded_boundary_keeps_candidate_cli_parser_and_mcp_sdk_live(tmp_path):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    skill_path = Path("hermes/skills/travel/tutu-search-flights")
    materialized = tmp_path / "skills" / "travel" / "tutu-search-flights"
    identity = materialize_skill_source(
        ROOT,
        skill_path,
        {"source": "git", "ref": "origin/new-tutu"},
        materialized,
    )
    log_path = tmp_path / "mcp-boundary.jsonl"
    env = os.environ.copy()
    replay_path = str(EVAL / "replay")
    env.update(
        {
            "PYTHONPATH": os.pathsep.join(
                value for value in (replay_path, env.get("PYTHONPATH", "")) if value
            ),
            "TUTU_EVAL_FIXTURE": str(FIXTURE),
            "TUTU_EVAL_BOUNDARY_LOG": str(log_path),
        }
    )
    command = [
        sys.executable,
        str(materialized / "tutu_search_flights.py"),
        json.dumps(fixture["arguments"], ensure_ascii=False),
    ]
    proc = subprocess.run(command, env=env, text=True, capture_output=True, check=False)

    assert proc.returncode == 0, proc.stderr
    observed = json.loads(proc.stdout)
    source_text = fixture["response"]["envelope"]["result"]["content"][0]["text"]
    source_result = json.loads(source_text)
    assert len(observed["offers"]) == len(source_result["offers"])
    assert [offer["flight_number"] for offer in observed["offers"]] == [
        offer["legs"][0]["segments"][0]["voyage_no"] for offer in source_result["offers"]
    ]

    records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    calls = [record for record in records if record.get("jsonrpc_method") == "tools/call"]
    assert identity["resolved_commit"] == "ab1ae0ff622be6a78466ccc12f3be71bdb0abceb"
    assert len(calls) == 1
    assert calls[0]["tool_name"] == "search_avia"
    assert calls[0]["arguments"] == fixture["arguments"]


def test_egress_guard_blocks_live_tutu_connect(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "tutu_search_flights_egress_contract", EVAL / "replay" / "egress_proxy.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    blocker = module.TutuEgressGuard(tmp_path / "blocked.jsonl")
    blocker.start()
    try:
        with socket.create_connection(("127.0.0.1", int(blocker.url.rsplit(":", 1)[1]))) as connection:
            connection.sendall(b"CONNECT mcp.tutu.ru:443 HTTP/1.1\r\nHost: mcp.tutu.ru:443\r\n\r\n")
            response = connection.recv(4096).decode("latin-1")
        assert response.startswith("HTTP/1.1 403 Forbidden")
        assert blocker.records() == [{"host": "mcp.tutu.ru", "method": "CONNECT", "blocked": True}]
    finally:
        blocker.close()
