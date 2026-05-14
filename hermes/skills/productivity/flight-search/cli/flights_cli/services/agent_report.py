from __future__ import annotations

from typing import Any

from ..reporting.agent_report_builder import (
    build_agent_report,
    provider_failure_summary,
    provider_failures,
    rejected_pair_warnings,
)
from ..reporting.answer_line_renderer import build_answer_lines
from ..reporting.coverage_projector import build_coverage_diagnostics
from ..reporting.formatting import minutes_label, price_label, segment_line
from ..reporting.option_projector import (
    candidate_options_from_details,
    connection_summary,
    priority_candidate_options,
    ranked_candidate_options,
    segment_summary,
)
from ..reporting.provider_aggregate_projector import aggregate_control_summary, provider_aggregate_candidate_options
from ..reporting.through_fare_analyzer import grouped_option_segments, option_common_carriers, through_fare_checks
from .agent_report_contract import validate_agent_report


def attach_agent_report(data: dict[str, Any], args: Any, store: Any | None = None) -> dict[str, Any]:
    if bool(getattr(args, "agent_report", False)) or bool(getattr(args, "agent_mode", False)):
        report = build_agent_report(data, store)
        validate_agent_report(report)
        data["agent_report"] = report
    return data
