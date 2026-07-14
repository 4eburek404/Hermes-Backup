from __future__ import annotations

from typing import Any


PROBE_BUCKETS = (
    "planned_probes",
    "searched_probes",
    "skipped_probes",
    "failed_probes",
    "unsupported_probes",
    "not_executed_probes",
    "deduped_probes",
)


def _coverage_warnings() -> list[str]:
    return [
        "segment_absence_is_not_route_absence",
        "provider_empty_is_not_carrier_absence",
        "cache_absence_is_not_negative_evidence",
    ]


def _runtime_ledger_diagnostics(ledger: dict[str, Any]) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {
        "negative_evidence_type": ledger.get("negative_evidence_type")
        or "bounded_live_probes_only",
        "coverage_warnings": ledger.get("coverage_warnings") or _coverage_warnings(),
    }
    for bucket in PROBE_BUCKETS:
        values = ledger.get(bucket)
        diagnostics[bucket] = values if isinstance(values, list) else []
    completeness = (
        ledger.get("completeness")
        if isinstance(ledger.get("completeness"), dict)
        else None
    )
    if completeness is None:
        planned_count = len(diagnostics["planned_probes"])
        terminal_count = sum(
            len(diagnostics[bucket])
            for bucket in (
                "searched_probes",
                "skipped_probes",
                "failed_probes",
                "unsupported_probes",
                "not_executed_probes",
            )
        )
        completeness = {
            "planned_count": planned_count,
            "terminal_count": terminal_count,
            "all_planned_probes_have_terminal_state": planned_count == terminal_count,
        }
    diagnostics["completeness"] = completeness
    return diagnostics


def build_coverage_diagnostics(
    plan: dict[str, Any], live: dict[str, Any]
) -> dict[str, Any]:
    del plan
    runtime_ledger = (
        live.get("probe_ledger") if isinstance(live.get("probe_ledger"), dict) else {}
    )
    return _runtime_ledger_diagnostics(runtime_ledger)


def compact_coverage_summary(
    diagnostics: dict[str, Any], provider_failures: list[dict[str, Any]]
) -> dict[str, Any]:
    completeness = (
        diagnostics.get("completeness")
        if isinstance(diagnostics.get("completeness"), dict)
        else {}
    )
    counts = {
        bucket: len(diagnostics.get(bucket) or [])
        for bucket in PROBE_BUCKETS
        if isinstance(diagnostics.get(bucket), list)
    }
    blocking_evidence: list[str] = []
    if diagnostics.get("not_executed_probes"):
        blocking_evidence.append("not_executed_probes")
    if diagnostics.get("failed_probes"):
        blocking_evidence.append("failed_probes")
    if provider_failures:
        blocking_evidence.append("provider_failures")
    non_blocking_boundaries = (
        ["unsupported_probes"] if diagnostics.get("unsupported_probes") else []
    )
    return {
        "negative_evidence_type": diagnostics.get("negative_evidence_type"),
        "coverage_warnings": diagnostics.get("coverage_warnings") or [],
        "counts": counts,
        "completeness": {
            "planned_count": int(completeness.get("planned_count") or 0),
            "terminal_count": int(completeness.get("terminal_count") or 0),
            "all_planned_probes_have_terminal_state": bool(
                completeness.get("all_planned_probes_have_terminal_state")
            ),
        },
        "blocking_evidence": blocking_evidence,
        "non_blocking_boundaries": non_blocking_boundaries,
    }
