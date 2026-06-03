from __future__ import annotations

from typing import Any

AGENT_REPORT_V2_SCHEMA_VERSION = "agent_report.v2"

EVIDENCE_ALIASES = {
    "source_boundaries",
    "hub_viability",
    "segment_searches",
    "provider_failures",
    "aggregate_controls",
    "coverage_diagnostics",
    "through_fare_checks",
    "rejected_pair_warnings",
    "stop_policy",
    "stop_policy_diagnostics",
    "ru_priority_controls",
}
FRONTIER_ALIASES = {"status", "offer_graph", "recommended_options", "priority_options"}
DIAGNOSTIC_ALIASES = {"display", "answer_lines", "human_answer", "omitted_counts"}
LEGACY_ALIAS_TARGETS = {
    **{key: ("evidence", key) for key in EVIDENCE_ALIASES},
    **{key: ("frontier", key) for key in FRONTIER_ALIASES},
    **{key: ("diagnostics", key) for key in DIAGNOSTIC_ALIASES},
}


class AgentReportV2(dict):
    """Runtime v2 report with Python-only legacy aliases.

    The serialized report stays a thin v2 wrapper. Existing in-process callers can
    still read or mutate legacy keys during the migration window; aliases resolve
    into evidence/frontier/diagnostics instead of being emitted as top-level JSON.
    """

    def _alias_target(self, key: object) -> tuple[str, str] | None:
        if not isinstance(key, str):
            return None
        return LEGACY_ALIAS_TARGETS.get(key)

    def _alias_container(self, key: str, *, create: bool = False) -> dict[str, Any] | None:
        target = self._alias_target(key)
        if target is None:
            return None
        section, _ = target
        container = dict.get(self, section)
        if isinstance(container, dict):
            return container
        if create:
            container = {}
            dict.__setitem__(self, section, container)
            return container
        return None

    def __getitem__(self, key: str) -> Any:
        try:
            return dict.__getitem__(self, key)
        except KeyError:
            container = self._alias_container(key)
            if container is not None:
                _, field = LEGACY_ALIAS_TARGETS[key]
                if field in container:
                    return container[field]
            raise

    def get(self, key: str, default: Any = None) -> Any:  # type: ignore[override]
        if dict.__contains__(self, key):
            return dict.get(self, key, default)
        target = self._alias_target(key)
        if target is None:
            return default
        container = self._alias_container(key)
        if container is None:
            return default
        _, field = target
        return container.get(field, default)

    def __setitem__(self, key: str, value: Any) -> None:
        target = self._alias_target(key)
        if target is None or dict.__contains__(self, key):
            dict.__setitem__(self, key, value)
            return
        container = self._alias_container(key, create=True)
        assert container is not None
        _, field = target
        container[field] = value

    def __delitem__(self, key: str) -> None:
        if dict.__contains__(self, key):
            dict.__delitem__(self, key)
            return
        target = self._alias_target(key)
        if target is None:
            raise KeyError(key)
        container = self._alias_container(key)
        _, field = target
        if container is None or field not in container:
            raise KeyError(key)
        del container[field]

    def __contains__(self, key: object) -> bool:
        if dict.__contains__(self, key):
            return True
        target = self._alias_target(key)
        if target is None:
            return False
        container = self._alias_container(key)  # type: ignore[arg-type]
        return container is not None and target[1] in container



def build_agent_report_v2(flat_report: dict[str, Any]) -> AgentReportV2:
    evidence: dict[str, Any] = {
        "source_boundaries": flat_report.get("source_boundaries") or [],
        "hub_viability": flat_report.get("hub_viability") or [],
        "segment_searches": flat_report.get("segment_searches") or [],
        "provider_failures": flat_report.get("provider_failures") or [],
        "aggregate_controls": flat_report.get("aggregate_controls") or [],
        "coverage_diagnostics": flat_report.get("coverage_diagnostics") or {},
        "through_fare_checks": flat_report.get("through_fare_checks") or [],
        "rejected_pair_warnings": flat_report.get("rejected_pair_warnings") or [],
        "stop_policy": flat_report.get("stop_policy") or {},
        "stop_policy_diagnostics": flat_report.get("stop_policy_diagnostics") or {},
    }
    if "ru_priority_controls" in flat_report:
        evidence["ru_priority_controls"] = flat_report["ru_priority_controls"]

    frontier = {
        "status": flat_report.get("status") or {},
        "offer_graph": flat_report.get("offer_graph") or {},
        "recommended_options": flat_report.get("recommended_options") or [],
        "priority_options": flat_report.get("priority_options") or [],
    }
    diagnostics = {
        "display": flat_report.get("display") or {},
        "answer_lines": flat_report.get("answer_lines") or [],
        "human_answer": flat_report.get("human_answer") or {},
    }
    if "omitted_counts" in flat_report:
        diagnostics["omitted_counts"] = flat_report["omitted_counts"]

    return AgentReportV2(
        {
            "schema_version": AGENT_REPORT_V2_SCHEMA_VERSION,
            "route": flat_report.get("route") or {},
            "evidence": evidence,
            "frontier": frontier,
            "user_answer": flat_report.get("user_answer") or {},
            "diagnostics": diagnostics,
        }
    )



def legacy_agent_report_view(report: dict[str, Any]) -> AgentReportV2:
    if isinstance(report, AgentReportV2):
        return report
    if report.get("schema_version") != AGENT_REPORT_V2_SCHEMA_VERSION:
        return AgentReportV2(report)
    flat = AgentReportV2(dict(report))
    return flat
