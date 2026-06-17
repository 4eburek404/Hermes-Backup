from __future__ import annotations

from typing import Any

from ..reporting.agent_report_builder import build_agent_report
from .agent_report_contract import validate_agent_report


def attach_agent_report(data: dict[str, Any], args: Any, store: Any | None = None) -> dict[str, Any]:
    if bool(getattr(args, "agent_report", False)):
        report = build_agent_report(data, store)
        validate_agent_report(report)
        data["agent_report"] = report

    return data