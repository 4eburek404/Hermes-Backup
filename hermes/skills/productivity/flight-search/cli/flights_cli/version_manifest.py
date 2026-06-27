from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import __skill_name__, __skill_version__, __version__
from .command_surface import (
    COMMAND_SURFACE_VERSION,
    DIAGNOSTIC_COMMANDS,
    PRIMARY_ROUTE_COMMAND,
)
from .contracts.registry import current_contract

MANIFEST_FILENAME = "version_manifest.json"


def source_skill_path() -> Path:
    return Path(__file__).resolve().parents[2]


def manifest_path(skill_path: Path | None = None) -> Path:
    return (skill_path or source_skill_path()) / MANIFEST_FILENAME


def load_version_manifest(skill_path: Path | None = None) -> dict[str, Any]:
    path = manifest_path(skill_path)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def expected_command_surface() -> dict[str, Any]:
    return {
        "version": COMMAND_SURFACE_VERSION,
        "canonical_path": f"{PRIMARY_ROUTE_COMMAND} --request",
        "diagnostic_commands": list(DIAGNOSTIC_COMMANDS),
    }


def manifest_mismatches(manifest: dict[str, Any]) -> list[str]:
    mismatches: list[str] = []
    if not manifest:
        return ["missing version_manifest.json"]

    skill = manifest.get("skill") if isinstance(manifest.get("skill"), dict) else {}
    cli = manifest.get("cli") if isinstance(manifest.get("cli"), dict) else {}
    contracts = (
        manifest.get("contracts") if isinstance(manifest.get("contracts"), dict) else {}
    )
    command_surface = (
        manifest.get("command_surface")
        if isinstance(manifest.get("command_surface"), dict)
        else {}
    )

    if skill.get("name") != __skill_name__:
        mismatches.append("skill.name")
    if skill.get("version") != __skill_version__:
        mismatches.append("skill.version")
    if cli.get("package") != "flights-cli":
        mismatches.append("cli.package")
    if cli.get("version") != __version__:
        mismatches.append("cli.version")

    expected_contracts = {
        "agent_report": current_contract("agent_report")["schema_version"],
        "user_answer": current_contract("user_answer")["schema_version"],
        "flight_search_request": current_contract("search_request")["schema_version"],
        "flight_search_result": current_contract("search_result")["schema_version"],
    }
    for name, version in expected_contracts.items():
        if contracts.get(name) != version:
            mismatches.append(f"contracts.{name}")

    expected_surface = expected_command_surface()
    if command_surface.get("version") != expected_surface["version"]:
        mismatches.append("command_surface.version")
    if command_surface.get("canonical_path") != expected_surface["canonical_path"]:
        mismatches.append("command_surface.canonical_path")
    if sorted(command_surface.get("diagnostic_commands") or []) != sorted(
        expected_surface["diagnostic_commands"]
    ):
        mismatches.append("command_surface.diagnostic_commands")
    return mismatches
