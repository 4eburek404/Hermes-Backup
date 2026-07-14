from __future__ import annotations

from typing import Any

from ..domain.vocabulary import RequiredControl
from ..execution.probe_ledger import ProbeExecutionLedger, control_identity


CONTROL_BUCKETS = [
    "planned_controls",
    "searched_controls",
    "skipped_controls",
    "failed_controls",
    "not_supported_controls",
    "not_executed_controls",
    "deduped_controls",
]


def _coverage_warnings() -> list[str]:
    return [
        "segment_absence_is_not_route_absence",
        "provider_empty_is_not_carrier_absence",
        "cache_absence_is_not_negative_evidence",
    ]


def _runtime_ledger_diagnostics(
    plan: dict[str, Any], ledger: dict[str, Any]
) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {
        "coverage_mode": ledger.get("coverage_mode")
        or plan.get("coverage_mode")
        or "standard",
        "negative_evidence_type": ledger.get("negative_evidence_type")
        or "bounded_live_controls_only",
        "coverage_warnings": ledger.get("coverage_warnings") or _coverage_warnings(),
        "limits": ledger.get("limits") or plan.get("coverage_limits") or {},
    }
    for bucket in CONTROL_BUCKETS:
        values = ledger.get(bucket)
        diagnostics[bucket] = values if isinstance(values, list) else []
    completeness = (
        ledger.get("completeness")
        if isinstance(ledger.get("completeness"), dict)
        else None
    )
    if completeness is None:
        planned_count = len(diagnostics["planned_controls"])
        terminal_count = sum(
            len(diagnostics[bucket])
            for bucket in (
                "searched_controls",
                "skipped_controls",
                "failed_controls",
                "not_supported_controls",
                "not_executed_controls",
            )
        )
        completeness = {
            "planned_count": planned_count,
            "terminal_count": terminal_count,
            "all_planned_controls_have_terminal_state": planned_count == terminal_count,
        }
    diagnostics["completeness"] = completeness
    return diagnostics


def build_coverage_diagnostics(
    plan: dict[str, Any], live: dict[str, Any]
) -> dict[str, Any]:
    runtime_ledger = (
        live.get("probe_ledger") if isinstance(live.get("probe_ledger"), dict) else None
    )
    if runtime_ledger is not None:
        return _runtime_ledger_diagnostics(plan, runtime_ledger)

    controls = [
        item for item in plan.get("coverage_controls") or [] if isinstance(item, dict)
    ]
    ledger = ProbeExecutionLedger()
    ledger.plan_controls(controls)
    by_key = {control_identity(control): control for control in controls}

    for item in live.get("segment_searches") or []:
        if not isinstance(item, dict):
            continue
        if item.get("status") == "deduped":
            ledger.record_deduped(
                {
                    "type": "route_segment",
                    "direction": item.get("direction"),
                    "leg": item.get("leg"),
                    "origin": item.get("origin"),
                    "destination": item.get("destination"),
                    "date": item.get("date"),
                    "probe_id": item.get("probe_id"),
                },
                original_probe_id=item.get("original_probe_id"),
            )
            continue
        if item.get("status") == "skipped":
            ledger.record_skipped(
                {
                    "type": "route_segment",
                    "direction": item.get("direction"),
                    "leg": item.get("leg"),
                    "origin": item.get("origin"),
                    "destination": item.get("destination"),
                    "date": item.get("date"),
                },
                reason=item.get("reason"),
            )
            continue
        key = control_identity(
            {
                "type": RequiredControl.EXACT_AIRPORT_DIRECT,
                "direction": item.get("direction"),
                "origin": item.get("origin"),
                "destination": item.get("destination"),
                "date": item.get("date"),
            }
        )
        control = by_key.get(key)
        if control:
            ledger.record_searched(
                control,
                status=item.get("status"),
                provider=item.get("provider"),
                offer_count=item.get("offer_count"),
                cache_status=item.get("cache_status"),
            )

    for item in live.get("aggregate_controls") or []:
        if not isinstance(item, dict):
            continue
        filters = item.get("filters") if isinstance(item.get("filters"), dict) else {}
        carriers = [
            str(code).upper() for code in filters.get("only_carriers") or [] if code
        ]
        if carriers:
            for carrier in carriers:
                key = control_identity(
                    {
                        "type": RequiredControl.CARRIER_AGGREGATE,
                        "direction": item.get("direction"),
                        "origin": item.get("origin"),
                        "destination": item.get("destination"),
                        "date": item.get("date"),
                        "carrier": carrier,
                    }
                )
                control = by_key.get(key)
                if control:
                    if item.get("status") == "error":
                        ledger.record_failed(
                            control,
                            provider=item.get("provider"),
                            error=item.get("error"),
                        )
                    else:
                        ledger.record_searched(
                            control,
                            status=item.get("status"),
                            provider=item.get("provider"),
                            offer_count=item.get("offer_count"),
                            cache_status=item.get("cache_status"),
                        )
        else:
            key = control_identity(
                {
                    "type": RequiredControl.FULL_ROUTE_AGGREGATE,
                    "direction": item.get("direction"),
                    "origin": item.get("origin"),
                    "destination": item.get("destination"),
                    "date": item.get("date"),
                }
            )
            control = by_key.get(key)
            if control:
                if item.get("status") == "error":
                    ledger.record_failed(
                        control, provider=item.get("provider"), error=item.get("error")
                    )
                else:
                    ledger.record_searched(
                        control,
                        status=item.get("status"),
                        provider=item.get("provider"),
                        offer_count=item.get("offer_count"),
                        cache_status=item.get("cache_status"),
                    )

    ledger.finalize_unexecuted()
    return ledger.to_coverage_diagnostics(plan)


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
        for bucket in CONTROL_BUCKETS
        if isinstance(diagnostics.get(bucket), list)
    }
    not_executed = diagnostics.get("not_executed_controls")
    failed = diagnostics.get("failed_controls")
    not_supported = diagnostics.get("not_supported_controls")
    blocking_evidence: list[str] = []
    if isinstance(not_executed, list) and not_executed:
        blocking_evidence.append("not_executed_controls")
    if isinstance(failed, list) and failed:
        blocking_evidence.append("failed_controls")
    if provider_failures:
        blocking_evidence.append("provider_failures")
    non_blocking_boundaries = (
        ["not_supported_controls"]
        if isinstance(not_supported, list) and not_supported
        else []
    )
    return {
        "coverage_mode": diagnostics.get("coverage_mode"),
        "negative_evidence_type": diagnostics.get("negative_evidence_type"),
        "coverage_warnings": diagnostics.get("coverage_warnings") or [],
        "counts": counts,
        "completeness": {
            "planned_count": int(completeness.get("planned_count") or 0),
            "terminal_count": int(completeness.get("terminal_count") or 0),
            "all_planned_controls_have_terminal_state": bool(
                completeness.get("all_planned_controls_have_terminal_state")
            ),
        },
        "blocking_evidence": blocking_evidence,
        "non_blocking_boundaries": non_blocking_boundaries,
    }
