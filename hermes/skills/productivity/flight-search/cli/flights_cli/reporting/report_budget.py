from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any

from .flight_display import sanitize_summary_only_display


@dataclass(frozen=True)
class AgentReportBudget:
    max_bytes: int = 65536
    max_recommended_options: int = 5
    max_priority_options: int = 8
    max_segment_searches: int = 20
    max_coverage_controls: int = 20
    max_provider_failures: int = 10
    max_answer_lines: int = 12


def serialized_report_size(report: dict[str, Any]) -> int:
    return len(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))


def apply_agent_report_budget(report: dict[str, Any], budget: AgentReportBudget | None = None) -> dict[str, Any]:
    budget = budget or AgentReportBudget()
    trimmed = copy.deepcopy(report)
    omitted: dict[str, int] = {}

    _trim_top_level_list(trimmed, "recommended_options", budget.max_recommended_options, omitted)
    _trim_top_level_list(trimmed, "priority_options", budget.max_priority_options, omitted)
    _trim_top_level_list(trimmed, "segment_searches", budget.max_segment_searches, omitted)
    _trim_top_level_list(trimmed, "provider_failures", budget.max_provider_failures, omitted)
    _trim_answer_lines(trimmed, budget.max_answer_lines, omitted)
    _trim_coverage_controls(trimmed, budget.max_coverage_controls, omitted)
    sanitize_summary_only_display(trimmed)

    if omitted:
        trimmed["omitted_counts"] = omitted

    if serialized_report_size(trimmed) > budget.max_bytes:
        removed_segments = _compact_non_primary_option_segments(trimmed)
        if removed_segments:
            omitted = dict(trimmed.get("omitted_counts") or {})
            omitted["option_segments"] = omitted.get("option_segments", 0) + removed_segments
            trimmed["omitted_counts"] = omitted
            sanitize_summary_only_display(trimmed)

    return trimmed


def _trim_top_level_list(report: dict[str, Any], key: str, limit: int, omitted: dict[str, int]) -> None:
    values = report.get(key)
    if not isinstance(values, list):
        return
    allowed = max(0, limit)
    if len(values) <= allowed:
        return
    omitted[key] = len(values) - allowed
    report[key] = values[:allowed]


def _trim_answer_lines(report: dict[str, Any], limit: int, omitted: dict[str, int]) -> None:
    lines = report.get("answer_lines")
    if not isinstance(lines, list):
        return
    allowed = max(1, limit)
    if len(lines) <= allowed:
        return
    report["answer_lines"] = _select_answer_lines(lines, allowed)
    omitted["answer_lines"] = len(lines) - len(report["answer_lines"])


def _select_answer_lines(lines: list[Any], limit: int) -> list[Any]:
    selected: list[Any] = []

    def add(line: Any) -> None:
        if len(selected) < limit and line not in selected:
            selected.append(line)

    if lines:
        add(lines[0])
    for marker in (
        "provider failure",
        "through-fare",
        "through fare",
        "priority control",
        "moscow gateway control",
        "provider aggregate candidate",
        "coverage diagnostics",
        "coverage is incomplete",
        "do not treat",
    ):
        for line in lines:
            if marker in str(line).lower():
                add(line)
    for line in lines:
        add(line)
    return selected


def _trim_coverage_controls(report: dict[str, Any], limit: int, omitted: dict[str, int]) -> None:
    diagnostics = report.get("coverage_diagnostics")
    if not isinstance(diagnostics, dict):
        return
    buckets = [
        "failed_controls",
        "not_executed_controls",
        "searched_controls",
        "skipped_controls",
        "deduped_controls",
        "planned_controls",
    ]
    remaining = max(0, limit)
    omitted_total = 0
    for bucket in buckets:
        values = diagnostics.get(bucket)
        if not isinstance(values, list):
            continue
        if len(values) <= remaining:
            remaining -= len(values)
            continue
        omitted_total += len(values) - remaining
        diagnostics[bucket] = values[:remaining]
        remaining = 0
    if omitted_total:
        omitted["coverage_controls"] = omitted_total


def _compact_non_primary_option_segments(report: dict[str, Any]) -> int:
    removed = 0
    primary_seen = False
    for bucket in ("recommended_options", "priority_options"):
        options = report.get(bucket)
        if not isinstance(options, list):
            continue
        for option in options:
            if not isinstance(option, dict):
                continue
            if bucket == "recommended_options" and not primary_seen:
                primary_seen = True
                continue
            segments = option.get("segments")
            if isinstance(segments, list) and segments:
                removed += len(segments)
                option["segments"] = []
                option["detail_status"] = "summary_only"
    return removed

