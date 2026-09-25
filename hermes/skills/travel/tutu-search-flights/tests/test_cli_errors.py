"""S8: CLI input and search failures have explicit exit and stream contracts."""

import json

import mcp
import pytest
import tutu_search_flights

from tests.mcp_recording_server import install_recorded_mcp, read_recording

REQUEST = {
    "origin": "Москва",
    "destination": "Сочи",
    "departure_date": "2026-10-15",
    "page_size": 3,
}


def _assert_search_failure(capsys, exit_code):
    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip()
    return captured.err


def test_invalid_json_uses_argparse_error_contract(capsys):
    with pytest.raises(SystemExit) as error:
        tutu_search_flights.main(["{"])

    captured = capsys.readouterr()
    assert error.value.code == 2
    assert captured.out == ""
    assert "usage:" in captured.err
    assert "arguments must be valid JSON" in captured.err


def test_non_object_json_uses_argparse_error_contract(capsys):
    with pytest.raises(SystemExit) as error:
        tutu_search_flights.main(["[]"])

    captured = capsys.readouterr()
    assert error.value.code == 2
    assert captured.out == ""
    assert "usage:" in captured.err
    assert "arguments must be a JSON object" in captured.err


def test_tool_error_emits_full_reason_on_stderr(monkeypatch, capsys):
    fixture = read_recording("avia/empty-route.json")
    result_record = fixture["response"]["envelope"]["result"]
    reason = result_record["content"][0]["text"]
    recording = install_recorded_mcp(monkeypatch, result_record)

    exit_code = tutu_search_flights.main([json.dumps(fixture["arguments"], ensure_ascii=False)])

    error_text = _assert_search_failure(capsys, exit_code)
    assert reason in error_text
    assert recording.client_urls == ["https://mcp.tutu.ru/mcp"]
    assert recording.calls == [("search_avia", fixture["arguments"])]


def test_transport_error_emits_reason_on_stderr(monkeypatch, capsys):
    client_urls = []

    def failing_client(url):
        client_urls.append(url)
        raise ExceptionGroup(
            "unhandled errors in a TaskGroup (1 sub-exception)",
            [
                ExceptionGroup(
                    "network transport",
                    [OSError("All connection attempts failed at MCP test boundary")],
                )
            ],
        )

    monkeypatch.setattr(mcp, "Client", failing_client)
    exit_code = tutu_search_flights.main([json.dumps(REQUEST)])

    error_text = _assert_search_failure(capsys, exit_code)
    assert "All connection attempts failed at MCP test boundary" in error_text
    assert client_urls == ["https://mcp.tutu.ru/mcp"]


@pytest.mark.parametrize(
    ("timeout", "expected_reason"),
    [
        pytest.param(
            TimeoutError("MCP test transport timed out"),
            "MCP test transport timed out",
            id="with-message",
        ),
        pytest.param(TimeoutError(), "TimeoutError", id="empty-message"),
    ],
)
def test_timeout_emits_reason_on_stderr(monkeypatch, capsys, timeout, expected_reason):
    client_urls = []

    def failing_client(url):
        client_urls.append(url)
        raise timeout

    monkeypatch.setattr(mcp, "Client", failing_client)
    exit_code = tutu_search_flights.main([json.dumps(REQUEST)])

    error_text = _assert_search_failure(capsys, exit_code)
    assert expected_reason in error_text
    assert client_urls == ["https://mcp.tutu.ru/mcp"]


def test_missing_text_fails_without_success_json(monkeypatch, capsys):
    recording = install_recorded_mcp(monkeypatch, {"content": [], "isError": False})

    exit_code = tutu_search_flights.main([json.dumps(REQUEST)])

    error_text = _assert_search_failure(capsys, exit_code)
    assert "no text result" in error_text
    assert recording.calls == [("search_avia", REQUEST)]


def test_malformed_result_text_fails_without_success_json(monkeypatch, capsys):
    recording = install_recorded_mcp(
        monkeypatch,
        {
            "content": [{"type": "text", "text": "{"}],
            "isError": False,
        },
    )

    exit_code = tutu_search_flights.main([json.dumps(REQUEST)])

    _assert_search_failure(capsys, exit_code)
    assert recording.calls == [("search_avia", REQUEST)]


def test_invalid_search_result_fails_without_success_json(monkeypatch, capsys):
    recording = install_recorded_mcp(
        monkeypatch,
        {
            "content": [{"type": "text", "text": json.dumps({"offers": [], "meta": {}})}],
            "isError": False,
        },
    )

    exit_code = tutu_search_flights.main([json.dumps(REQUEST)])

    _assert_search_failure(capsys, exit_code)
    assert recording.calls == [("search_avia", REQUEST)]
