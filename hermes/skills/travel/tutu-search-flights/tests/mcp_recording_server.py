"""Small real-SDK MCP in-memory fixture for deterministic production tests."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import mcp
from mcp import Client as real_Client
from mcp import types
from mcp.server import Server

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@dataclass
class Recording:
    client_urls: list[str] = field(default_factory=list)
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)


def read_recording(path: str) -> dict[str, Any]:
    return json.loads((FIXTURES / path).read_text(encoding="utf-8"))


def install_recorded_mcp(monkeypatch, call_result: dict[str, Any]) -> Recording:
    tools_list_record = read_recording("meta/tools-list.json")
    tools_list_result = tools_list_record["response"]["envelope"]["result"]
    recording = Recording()

    async def call_handler(ctx, params):
        recording.calls.append((params.name, deepcopy(params.arguments)))
        return types.CallToolResult.model_validate(deepcopy(call_result))

    async def list_handler(ctx, params):
        return types.ListToolsResult.model_validate(deepcopy(tools_list_result))

    server = Server("recorded", on_call_tool=call_handler, on_list_tools=list_handler)

    def client_factory(url: str):
        recording.client_urls.append(url)
        return real_Client(server)

    monkeypatch.setattr(mcp, "Client", client_factory)
    return recording
