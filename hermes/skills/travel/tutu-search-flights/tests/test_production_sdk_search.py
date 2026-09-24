"""S2: production CLI использует MCP SDK и search_avia."""

import json
import sys
import types
from copy import deepcopy
from pathlib import Path
from typing import ClassVar

import tutu_search_flights

BASELINE = Path(__file__).resolve().parents[1] / "fixtures/avia/baseline.json"
REQUEST = {
    "origin": "Москва",
    "destination": "Сочи",
    "departure_date": "2026-10-15",
    "page_size": 3,
}


class _TextBlock:
    def __init__(self, text):
        self.text = text


class _ToolResult:
    def __init__(self, text, *, is_error=False):
        self.content = [_TextBlock(text)]
        self.is_error = is_error


class _FakeClient:
    instances: ClassVar[list] = []
    result: ClassVar = None

    def __init__(self, url):
        self.url = url
        self.calls = []
        self.__class__.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def call_tool(self, name, arguments):
        self.calls.append((name, deepcopy(arguments)))
        return self.__class__.result


def _install_fake_mcp(monkeypatch, result):
    _FakeClient.instances = []
    _FakeClient.result = result
    module = types.ModuleType("mcp")
    module.Client = _FakeClient
    monkeypatch.setitem(sys.modules, "mcp", module)


def test_production_cli_uses_sdk_search_avia_and_returns_product_result(monkeypatch, capsys):
    recording = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert recording["arguments"] == REQUEST
    envelope = recording["response"]["envelope"]
    raw_text = envelope["result"]["content"][0]["text"]
    _install_fake_mcp(monkeypatch, _ToolResult(raw_text))

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
    assert len(_FakeClient.instances) == 1
    client = _FakeClient.instances[0]
    assert client.url == "https://mcp.tutu.ru/mcp"
    assert client.calls == [("search_avia", REQUEST)]
    assert actual == expected
