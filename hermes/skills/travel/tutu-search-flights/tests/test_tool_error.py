"""S3: tool-level error Tutu не превращается в успешную выдачу."""

import asyncio
import sys
import types
from copy import deepcopy

import pytest
import tutu_search_flights

REQUEST = {
    "origin": "Москва",
    "destination": "Сочи",
    "departure_date": "2026-10-15",
}


class _TextBlock:
    def __init__(self, text):
        self.text = text


class _ToolResult:
    def __init__(self, text):
        self.content = [_TextBlock(text)]
        self.is_error = True


class _FakeClient:
    instances = []

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
        return _ToolResult("Tutu search failed")


def test_tool_error_is_reported_as_error_not_empty_search(monkeypatch):
    _FakeClient.instances = []
    module = types.ModuleType("mcp")
    module.Client = _FakeClient
    monkeypatch.setitem(sys.modules, "mcp", module)

    with pytest.raises(RuntimeError, match="Tutu search failed"):
        asyncio.run(tutu_search_flights.search_live(deepcopy(REQUEST)))

    assert len(_FakeClient.instances) == 1
    client = _FakeClient.instances[0]
    assert client.url == "https://mcp.tutu.ru/mcp"
    assert client.calls == [("search_avia", REQUEST)]
