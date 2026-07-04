from __future__ import annotations

from typing import Any

from ..reporting.agent_report_builder import build_agent_report
from .agent_report_contract import validate_agent_report


def build_validated_agent_report(
    route_result: dict[str, Any], store: Any | None = None
) -> dict[str, Any]:
    report = build_agent_report(route_result, store)
    validate_agent_report(report)
    return report
