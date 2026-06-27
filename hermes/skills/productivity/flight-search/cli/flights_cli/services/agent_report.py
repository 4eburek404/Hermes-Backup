from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..reporting.agent_report_builder import build_agent_report
from .agent_report_contract import validate_agent_report


@dataclass(frozen=True, slots=True)
class AgentReportOptions:
    agent_report: bool = False


def agent_report_options_from_args(args: Any) -> AgentReportOptions:
    return AgentReportOptions(agent_report=bool(getattr(args, "agent_report", False)))


def attach_agent_report(
    data: dict[str, Any], options: AgentReportOptions, store: Any | None = None
) -> dict[str, Any]:
    if options.agent_report:
        report = build_agent_report(data, store)
        validate_agent_report(report)
        data["agent_report"] = report

    return data
