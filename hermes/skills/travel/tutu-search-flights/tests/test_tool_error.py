"""S3: записанная tool-level error Tutu не превращается в успешную выдачу."""

import asyncio
import json
import sys
import types
from copy import deepcopy
from pathlib import Path

import pytest
import tutu_search_flights

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/avia/empty-route.json"


class _TextBlock:
    def __init__(self, text):
        self.text = text


class _ToolResult:
    def __init__(self, text):
        self.content = [_TextBlock(text)]
        self.is_error = True


class _FakeClient:
    instances = []
    result = None

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


def test_tool_error_is_reported_as_error_not_empty_search(monkeypatch):
    recording = json.loads(FIXTURE.read_text(encoding="utf-8"))
    envelope = recording["response"]["envelope"]
    source_text = envelope["result"]["content"][0]["text"]

    _FakeClient.instances = []
    _FakeClient.result = _ToolResult(source_text)
    module = types.ModuleType("mcp")
    module.Client = _FakeClient
    monkeypatch.setitem(sys.modules, "mcp", module)

    with pytest.raises(RuntimeError, match="avia cannot search origin"):
        asyncio.run(tutu_search_flights.search_live(deepcopy(recording["arguments"])))

    assert len(_FakeClient.instances) == 1
    client = _FakeClient.instances[0]
    assert client.url == "https://mcp.tutu.ru/mcp"
    assert client.calls == [("search_avia", recording["arguments"])]
