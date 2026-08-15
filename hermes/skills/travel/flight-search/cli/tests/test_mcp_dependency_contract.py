from __future__ import annotations

import tomllib
from pathlib import Path


def test_flight_search_uses_hermes_agent_mcp_version() -> None:
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    dependencies = tomllib.loads(pyproject.read_text())["project"]["dependencies"]

    assert "mcp==1.28.1" in dependencies
    assert "mcp==2.0.0" not in dependencies
