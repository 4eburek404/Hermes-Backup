from __future__ import annotations

from typing import Any

from ..execution.probe_ledger import ProbeExecutionLedger, control_identity


def build_coverage_diagnostics(plan: dict[str, Any], live: dict[str, Any]) -> dict[str, Any]:
    controls = [item for item in plan.get("coverage_controls") or [] if isinstance(item, dict)]
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
        key = ("exact_airport_direct", item.get("direction"), item.get("origin"), item.get("destination"), item.get("date"), None)
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
        carriers = [str(code).upper() for code in filters.get("only_carriers") or [] if code]
        if carriers:
            for carrier in carriers:
                key = ("carrier_aggregate", item.get("direction"), item.get("origin"), item.get("destination"), item.get("date"), carrier)
                control = by_key.get(key)
                if control:
                    if item.get("status") == "error":
                        ledger.record_failed(control, provider=item.get("provider"), error=item.get("error"))
                    else:
                        ledger.record_searched(
                            control,
                            status=item.get("status"),
                            provider=item.get("provider"),
                            offer_count=item.get("offer_count"),
                            cache_status=item.get("cache_status"),
                        )
        else:
            key = ("full_route_aggregate", item.get("direction"), item.get("origin"), item.get("destination"), item.get("date"), None)
            control = by_key.get(key)
            if control:
                if item.get("status") == "error":
                    ledger.record_failed(control, provider=item.get("provider"), error=item.get("error"))
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
