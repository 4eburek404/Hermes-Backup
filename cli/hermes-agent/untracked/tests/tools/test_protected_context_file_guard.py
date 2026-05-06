"""Regression tests for approval guard on Hermes context files."""

import json
import os
from pathlib import Path

from tools import approval
from tools.file_tools import patch_tool, write_file_tool
from tools.memory_tool import MemoryStore, memory_tool


def _enable_gateway_surface(monkeypatch, session_key="guard-test"):
    monkeypatch.setenv("HERMES_GATEWAY_SESSION", "1")
    monkeypatch.setenv("HERMES_SESSION_KEY", session_key)
    approval.clear_session(session_key)
    return session_key


def test_write_file_blocks_protected_memory_without_approval(monkeypatch):
    session_key = _enable_gateway_surface(monkeypatch)
    target = Path(os.environ["HERMES_HOME"]) / "memories" / "MEMORY.md"

    result = json.loads(write_file_tool(str(target), "new memory", task_id="guard-write"))

    assert result["error"]
    assert "protected Hermes context file" in result["error"]
    assert not target.exists()
    approval.clear_session(session_key)


def test_write_file_allows_protected_memory_after_session_approval(monkeypatch):
    session_key = _enable_gateway_surface(monkeypatch)
    target = Path(os.environ["HERMES_HOME"]) / "memories" / "MEMORY.md"
    approval.approve_session(session_key, "protected-context-file:MEMORY.md")

    result = json.loads(write_file_tool(str(target), "approved memory", task_id="guard-write-approved"))

    assert not result.get("error")
    assert target.read_text(encoding="utf-8") == "approved memory"
    approval.clear_session(session_key)


def test_patch_blocks_protected_soul_without_approval(monkeypatch):
    session_key = _enable_gateway_surface(monkeypatch)
    target = Path(os.environ["HERMES_HOME"]) / "SOUL.md"
    target.write_text("old\n", encoding="utf-8")

    result = json.loads(patch_tool(mode="replace", path=str(target), old_string="old", new_string="new", task_id="guard-patch"))

    assert result["error"]
    assert "protected Hermes context file" in result["error"]
    assert target.read_text(encoding="utf-8") == "old\n"
    approval.clear_session(session_key)


def test_memory_tool_blocks_builtin_memory_without_approval(monkeypatch):
    session_key = _enable_gateway_surface(monkeypatch)
    store = MemoryStore()
    store.load_from_disk()

    result = json.loads(memory_tool(action="add", target="memory", content="durable fact", store=store))

    assert result["success"] is False
    assert "protected Hermes context file" in result["error"]
    target = Path(os.environ["HERMES_HOME"]) / "memories" / "MEMORY.md"
    assert not target.exists() or target.read_text(encoding="utf-8") == ""
    approval.clear_session(session_key)


def test_memory_tool_allows_builtin_memory_after_session_approval(monkeypatch):
    session_key = _enable_gateway_surface(monkeypatch)
    approval.approve_session(session_key, "protected-context-file:MEMORY.md")
    store = MemoryStore()
    store.load_from_disk()

    result = json.loads(memory_tool(action="add", target="memory", content="durable fact", store=store))

    assert result["success"] is True
    target = Path(os.environ["HERMES_HOME"]) / "memories" / "MEMORY.md"
    assert "durable fact" in target.read_text(encoding="utf-8")
    approval.clear_session(session_key)


def test_terminal_detection_flags_protected_context_file_writes():
    examples = [
        "echo x > ~/.hermes/memories/MEMORY.md",
        "echo x > /home/konstantin/.hermes/memories/MEMORY.md",
        "printf y | tee ~/.hermes/memories/USER.md",
        "sed -i s/old/new/ ~/.hermes/SOUL.md",
        "rm ~/.hermes/SOUL.md",
    ]

    for command in examples:
        is_dangerous, _key, description = approval.detect_dangerous_command(command)
        assert is_dangerous, command
        assert "protected Hermes context file" in description
