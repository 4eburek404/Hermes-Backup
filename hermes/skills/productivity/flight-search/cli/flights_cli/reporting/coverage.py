from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
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
TERMINAL_PROBE_BUCKETS = PROBE_BUCKETS[1:]


def coverage_warnings() -> list[str]:
    return [
        "segment_absence_is_not_route_absence",
        "provider_empty_is_not_carrier_absence",
        "cache_absence_is_not_negative_evidence",
    ]


def provider_failure_summary(failure: dict[str, Any]) -> dict[str, Any]:
    error = failure.get("error") if isinstance(failure.get("error"), dict) else {}
    error_summary = {
        key: error.get(key)
        for key in (
            "type",
            "message",
            "classification",
            "retryable",
            "retry_after_seconds",
            "retry_after_parse_error",
            "http_status",
        )
        if key in error or key in {"type", "message"}
    }
    return {
        "direction": failure.get("direction"),
        "leg": failure.get("leg"),
        "origin": failure.get("origin"),
        "destination": failure.get("destination"),
        "date": failure.get("date"),
        "provider": failure.get("provider"),
        "cache_status": failure.get("cache_status"),
        "probe_id": failure.get("probe_id"),
        "error": error_summary,
    }


def compact_provider_failures(
    ledger: dict[str, Any], *, limit: int = 10
) -> list[dict[str, Any]]:
    return [
        provider_failure_summary(item)
        for item in failed_probes_from_ledger(ledger)[: max(0, limit)]
    ]


def failed_probes_from_ledger(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    """Return defensive copies of the ledger-owned provider failures."""

    return [
        deepcopy(item)
        for item in ledger.get("failed_probes") or []
        if isinstance(item, dict)
    ]


def _coverage_diagnostics_from_ledger(ledger: dict[str, Any]) -> dict[str, Any]:
    missing = [bucket for bucket in PROBE_BUCKETS if bucket not in ledger]
    invalid = [
        bucket
        for bucket in PROBE_BUCKETS
        if bucket in ledger and not isinstance(ledger[bucket], list)
    ]
    if missing or invalid:
        details = []
        if missing:
            details.append(f"missing buckets: {', '.join(missing)}")
        if invalid:
            details.append(f"non-list buckets: {', '.join(invalid)}")
        raise ValueError(
            f"invalid production probe ledger shape ({'; '.join(details)})"
        )

    diagnostics = {bucket: deepcopy(ledger[bucket]) for bucket in PROBE_BUCKETS}
    planned_count = len(diagnostics["planned_probes"])
    terminal_count = sum(len(diagnostics[bucket]) for bucket in TERMINAL_PROBE_BUCKETS)
    diagnostics.update(
        {
            "negative_evidence_type": "bounded_live_probes_only",
            "coverage_warnings": coverage_warnings(),
            "completeness": {
                "planned_count": planned_count,
                "terminal_count": terminal_count,
                "all_planned_probes_have_terminal_state": (
                    planned_count == terminal_count
                ),
            },
        }
    )
    return diagnostics


def _compact_summary(diagnostics: dict[str, Any]) -> dict[str, Any]:
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


def _answer_evidence_status(
    diagnostics: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    completeness = summary["completeness"]
    execution_complete = bool(
        completeness.get("all_planned_probes_have_terminal_state")
    )
    blocking_evidence = list(summary.get("blocking_evidence") or [])
    evidence_complete = execution_complete and not blocking_evidence
    return {
        "coverage_complete": evidence_complete,
        "execution_complete": execution_complete,
        "evidence_complete": evidence_complete,
        "answerability": (
            "answerable"
            if evidence_complete
            else "answerable_with_caveats"
            if execution_complete
            else "needs_more_evidence"
        ),
        "planned_probe_count": int(completeness.get("planned_count") or 0),
        "terminal_probe_count": int(completeness.get("terminal_count") or 0),
        "not_executed_probe_count": len(diagnostics.get("not_executed_probes") or []),
        "failed_probe_count": len(diagnostics.get("failed_probes") or []),
        "unsupported_probe_count": len(diagnostics.get("unsupported_probes") or []),
        "provider_failure_count": len(diagnostics.get("failed_probes") or []),
        "blocking_evidence": blocking_evidence,
        "non_blocking_boundaries": list(summary.get("non_blocking_boundaries") or []),
    }


@dataclass(frozen=True, slots=True)
class CoverageSnapshot:
    diagnostics: dict[str, Any]
    summary: dict[str, Any]
    provider_failures: tuple[dict[str, Any], ...]
    answer_evidence_status: dict[str, Any]

    @classmethod
    def from_live(
        cls, live: dict[str, Any], *, failure_limit: int = 10
    ) -> CoverageSnapshot:
        ledger = live.get("probe_ledger")
        if not isinstance(ledger, dict):
            raise ValueError("live search output requires a production probe_ledger")
        return cls.from_diagnostics(ledger, failure_limit=failure_limit)

    @classmethod
    def from_diagnostics(
        cls,
        diagnostics: dict[str, Any],
        *,
        failure_limit: int = 10,
    ) -> CoverageSnapshot:
        normalized = _coverage_diagnostics_from_ledger(diagnostics)
        failures = compact_provider_failures(normalized, limit=failure_limit)
        summary = _compact_summary(normalized)
        return cls(
            diagnostics=normalized,
            summary=summary,
            provider_failures=tuple(failures),
            answer_evidence_status=_answer_evidence_status(normalized, summary),
        )


__all__ = [
    "CoverageSnapshot",
    "PROBE_BUCKETS",
    "TERMINAL_PROBE_BUCKETS",
    "compact_provider_failures",
    "coverage_warnings",
    "failed_probes_from_ledger",
    "provider_failure_summary",
]
