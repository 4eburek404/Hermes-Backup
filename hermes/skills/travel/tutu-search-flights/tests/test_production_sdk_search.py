"""S2: production CLI uses the real MCP SDK against a recorded in-memory server."""

import json
from copy import deepcopy

import tutu_search_flights

from tests.mcp_recording_server import install_recorded_mcp, read_recording

REQUEST = {
    "origin": "Москва",
    "destination": "Сочи",
    "departure_date": "2026-10-15",
    "page_size": 3,
}


def test_production_cli_uses_sdk_search_avia_and_returns_product_result(monkeypatch, capsys):
    fixture = read_recording("avia/baseline.json")
    assert fixture["arguments"] == REQUEST
    envelope = fixture["response"]["envelope"]
    result_record = envelope["result"]
    source_text = result_record["content"][0]["text"]
    recording = install_recorded_mcp(monkeypatch, result_record)

    def recorded_tool(name, arguments):
        assert name == "search_avia"
        assert arguments == REQUEST
        return deepcopy(envelope)

    expected = tutu_search_flights.search(deepcopy(REQUEST), call_tool=recorded_tool)

    exit_code = tutu_search_flights.main([json.dumps(REQUEST, ensure_ascii=False)])
    captured = capsys.readouterr()
    actual = json.loads(captured.out)

    assert exit_code == 0
    assert captured.err == ""
    assert recording.client_urls == ["https://mcp.tutu.ru/mcp"]
    assert recording.calls == [("search_avia", REQUEST)]
    assert actual == expected

    # Independent fixture anchors guard the CLI result as well as parser parity.
    source_payload = json.loads(source_text)
    assert len(actual["offers"]) == len(source_payload["offers"]) == 3
    assert actual["offers"][0]["legs"][0]["segments"][0]["flight_number"] == "DP-6949"
    assert actual["offers"][0]["fares"][0]["amount"] == "4446.87"
    assert actual["offers"][0]["fares"][0]["currency"] == "RUB"
