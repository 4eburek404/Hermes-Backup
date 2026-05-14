from __future__ import annotations

from typing import Any


ControlKey = tuple[Any, Any, Any, Any, Any, Any]


def control_identity(control: dict[str, Any]) -> ControlKey:
    return (
        control.get("type"),
        control.get("direction"),
        control.get("origin"),
        control.get("destination"),
        control.get("date"),
        control.get("carrier"),
    )


class ProbeExecutionLedger:
    def __init__(self) -> None:
        self._planned: dict[ControlKey, dict[str, Any]] = {}
        self._planned_order: list[ControlKey] = []
        self._probe_ids: dict[ControlKey, str] = {}
        self._terminal_keys: set[ControlKey] = set()
        self._searched: list[dict[str, Any]] = []
        self._skipped: list[dict[str, Any]] = []
        self._failed: list[dict[str, Any]] = []
        self._not_executed: list[dict[str, Any]] = []
        self._deduped: list[dict[str, Any]] = []

    def plan_controls(self, controls: list[dict[str, Any]]) -> None:
        for control in controls:
            if not isinstance(control, dict):
                continue
            key = control_identity(control)
            if key in self._planned:
                self.record_deduped(control, original_probe_id=self._probe_ids.get(key))
                continue
            self._planned[key] = control
            self._planned_order.append(key)
            self._probe_ids[key] = str(control.get("probe_id") or f"probe-{len(self._planned_order):03d}")

    def record_searched(
        self,
        control: dict[str, Any],
        status: Any,
        provider: Any,
        offer_count: Any,
        cache_status: Any = None,
    ) -> None:
        key = control_identity(control)
        if key in self._terminal_keys:
            self.record_deduped(control, original_probe_id=self._probe_ids.get(key))
            return
        self._terminal_keys.add(key)
        self._searched.append(
            self._diagnostic(
                control,
                execution_state="searched",
                status=status,
                provider=provider,
                offer_count=offer_count,
                cache_status=cache_status,
            )
        )

    def record_skipped(self, control: dict[str, Any], reason: Any) -> None:
        key = control_identity(control)
        if key in self._terminal_keys:
            self.record_deduped(control, original_probe_id=self._probe_ids.get(key))
            return
        if key in self._planned:
            self._terminal_keys.add(key)
        self._skipped.append(self._diagnostic(control, execution_state="skipped", status="skipped", reason=reason))

    def record_failed(self, control: dict[str, Any], provider: Any, error: Any) -> None:
        key = control_identity(control)
        if key in self._terminal_keys:
            self.record_deduped(control, original_probe_id=self._probe_ids.get(key))
            return
        self._terminal_keys.add(key)
        self._failed.append(
            self._diagnostic(
                control,
                execution_state="failed",
                status="error",
                provider=provider,
                offer_count=0,
                error=error,
            )
        )

    def record_deduped(self, control: dict[str, Any], original_probe_id: Any = None) -> None:
        self._deduped.append(
            self._diagnostic(
                control,
                execution_state="deduped",
                status="deduped",
                original_probe_id=original_probe_id,
            )
        )

    def finalize_unexecuted(self, reason: str = "not_reached_by_current_live_execution") -> None:
        for key in self._planned_order:
            if key in self._terminal_keys:
                continue
            control = self._planned[key]
            self._terminal_keys.add(key)
            self._not_executed.append(
                self._diagnostic(control, execution_state="not_executed", status="not_executed", reason=reason)
            )

    def to_coverage_diagnostics(self, plan: dict[str, Any]) -> dict[str, Any]:
        terminal_count = len(self._terminal_keys)
        planned_count = len(self._planned_order)
        return {
            "coverage_mode": plan.get("coverage_mode") or "standard",
            "negative_evidence_type": "bounded_live_controls_only",
            "planned_controls": [self._diagnostic(self._planned[key], execution_state="planned") for key in self._planned_order],
            "searched_controls": self._searched,
            "skipped_controls": self._skipped,
            "failed_controls": self._failed,
            "not_executed_controls": self._not_executed,
            "deduped_controls": self._deduped,
            "coverage_warnings": [
                "segment_absence_is_not_route_absence",
                "provider_empty_is_not_carrier_absence",
                "cache_absence_is_not_negative_evidence",
            ],
            "limits": plan.get("coverage_limits") or {},
            "completeness": {
                "planned_count": planned_count,
                "terminal_count": terminal_count,
                "all_planned_controls_have_terminal_state": planned_count == terminal_count,
            },
        }

    def _diagnostic(self, control: dict[str, Any], **extra: Any) -> dict[str, Any]:
        key = control_identity(control)
        item = {
            "type": control.get("type"),
            "direction": control.get("direction"),
            "origin": control.get("origin"),
            "destination": control.get("destination"),
            "date": control.get("date"),
            "carrier": control.get("carrier"),
            "leg": control.get("leg"),
            "negative_evidence": control.get("negative_evidence"),
            "probe_id": self._probe_ids.get(key) or control.get("probe_id"),
        }
        for name, value in extra.items():
            if value is not None:
                item[name] = value
        return {name: value for name, value in item.items() if value is not None}

