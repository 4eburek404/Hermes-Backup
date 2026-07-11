from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..domain.vocabulary import AbsenceReason, ProbeStatus
from ..ports.providers import ProviderProbeResult
from .probe_intent import ProbeIntent
from .request_deduper import logical_query_key


ControlInput = dict[str, Any] | Mapping[str, Any] | ProbeIntent


def _control_dict(control: ControlInput) -> dict[str, Any]:
    if isinstance(control, ProbeIntent):
        return control.to_control()
    return dict(control)


def control_identity(control: ControlInput) -> tuple[Any, ...]:
    return logical_query_key(_control_dict(control))


class ProbeExecutionLedger:
    """Append-only execution ledger indexed by unique probe IDs."""

    def __init__(self) -> None:
        self._planned: dict[str, dict[str, Any]] = {}
        self._planned_order: list[str] = []
        self._logical_originals: dict[tuple[Any, ...], str] = {}
        self._terminal_ids: set[str] = set()
        self._searched: list[dict[str, Any]] = []
        self._skipped: list[dict[str, Any]] = []
        self._failed: list[dict[str, Any]] = []
        self._not_supported: list[dict[str, Any]] = []
        self._not_executed: list[dict[str, Any]] = []
        self._deduped: list[dict[str, Any]] = []
        self._counter = 0

    def _next_probe_id(self) -> str:
        self._counter += 1
        return f"probe-{self._counter:03d}"

    def _new_probe_id(self, item: dict[str, Any]) -> str:
        requested = str(item.get("probe_id") or "")
        if requested and requested not in self._planned:
            return requested
        candidate = self._next_probe_id()
        while candidate in self._planned:
            candidate = self._next_probe_id()
        return candidate

    def _resolve_probe_id(self, item: dict[str, Any]) -> str:
        explicit = str(item.get("probe_id") or "")
        if explicit in self._planned:
            return explicit
        original = self._logical_originals.get(logical_query_key(item))
        if original is not None:
            return original
        probe_id = self._new_probe_id(item)
        planned = {**item, "probe_id": probe_id}
        self._planned[probe_id] = planned
        self._planned_order.append(probe_id)
        self._logical_originals[logical_query_key(item)] = probe_id
        return probe_id

    def plan_controls(self, controls: list[ControlInput]) -> None:
        for control in controls:
            item = _control_dict(control)
            key = logical_query_key(item)
            original_probe_id = self._logical_originals.get(key)
            probe_id = self._new_probe_id(item)
            planned = {**item, "probe_id": probe_id}
            self._planned[probe_id] = planned
            self._planned_order.append(probe_id)
            if original_probe_id is None:
                self._logical_originals[key] = probe_id
                continue
            self._terminal_ids.add(probe_id)
            self._deduped.append(
                self._diagnostic(
                    planned,
                    execution_state=ProbeStatus.DEDUPED,
                    status=ProbeStatus.DEDUPED,
                    original_probe_id=original_probe_id,
                )
            )

    def plan_intents(self, intents: list[ProbeIntent]) -> None:
        self.plan_controls(list(intents))

    def _record_terminal(
        self,
        control: ControlInput,
        target: list[dict[str, Any]],
        **extra: Any,
    ) -> None:
        item = _control_dict(control)
        probe_id = self._resolve_probe_id(item)
        if probe_id in self._terminal_ids:
            self.record_deduped(item, original_probe_id=probe_id)
            return
        self._terminal_ids.add(probe_id)
        target.append(self._diagnostic(self._planned[probe_id], **extra))

    def record_searched(
        self,
        control: ControlInput,
        status: Any,
        provider: Any,
        offer_count: Any,
        cache_status: Any = None,
    ) -> None:
        self._record_terminal(
            control,
            self._searched,
            execution_state=ProbeStatus.SEARCHED,
            status=status,
            provider=provider,
            offer_count=offer_count,
            cache_status=cache_status,
        )

    def record_skipped(self, control: ControlInput, reason: Any) -> None:
        self._record_terminal(
            control,
            self._skipped,
            execution_state=ProbeStatus.SKIPPED,
            status=ProbeStatus.SKIPPED,
            reason=reason,
        )

    def record_failed(self, control: ControlInput, provider: Any, error: Any) -> None:
        self._record_terminal(
            control,
            self._failed,
            execution_state=ProbeStatus.FAILED,
            status=ProbeStatus.FAILED,
            provider=provider,
            offer_count=0,
            error=error,
        )

    def record_not_supported(
        self, control: ControlInput, provider: Any, reason: Any
    ) -> None:
        self._record_terminal(
            control,
            self._not_supported,
            execution_state=ProbeStatus.NOT_SUPPORTED,
            status=ProbeStatus.NOT_SUPPORTED,
            provider=provider,
            offer_count=0,
            reason=reason,
        )

    def record_provider_result(
        self, control: ControlInput, result: ProviderProbeResult
    ) -> None:
        if result.execution_state == ProbeStatus.NOT_SUPPORTED:
            reason = result.result_summary.get("reason")
            if reason is None and result.errors:
                reason = result.errors[0].get("message")
            self.record_not_supported(control, provider=result.provider, reason=reason)
            return
        if result.execution_state == ProbeStatus.FAILED:
            self.record_failed(
                control,
                provider=result.provider,
                error=result.errors[0] if result.errors else None,
            )
            return
        self.record_searched(
            control,
            status=result.result_summary.get("status") or result.execution_state,
            provider=result.provider,
            offer_count=result.result_summary.get("offer_count", len(result.offers)),
            cache_status=result.cache_status,
        )

    def record_deduped(
        self, control: ControlInput, original_probe_id: Any = None
    ) -> None:
        item = _control_dict(control)
        duplicate_id = self._new_probe_id(item)
        original = original_probe_id or self._logical_originals.get(
            logical_query_key(item)
        )
        self._deduped.append(
            self._diagnostic(
                {**item, "probe_id": duplicate_id},
                execution_state=ProbeStatus.DEDUPED,
                status=ProbeStatus.DEDUPED,
                original_probe_id=original,
            )
        )

    def finalize_unexecuted(
        self, reason: str = "not_reached_by_current_live_execution"
    ) -> None:
        for probe_id in self._planned_order:
            if probe_id in self._terminal_ids:
                continue
            self._terminal_ids.add(probe_id)
            self._not_executed.append(
                self._diagnostic(
                    self._planned[probe_id],
                    execution_state=ProbeStatus.NOT_EXECUTED,
                    status=ProbeStatus.NOT_EXECUTED,
                    reason=reason,
                )
            )

    def to_coverage_diagnostics(self, plan: dict[str, Any]) -> dict[str, Any]:
        planned_count = len(self._planned_order)
        terminal_count = len(self._terminal_ids)
        return {
            "coverage_mode": plan.get("coverage_mode") or "standard",
            "negative_evidence_type": "bounded_live_controls_only",
            "planned_controls": [
                self._diagnostic(
                    self._planned[probe_id], execution_state=ProbeStatus.PLANNED
                )
                for probe_id in self._planned_order
            ],
            "searched_controls": self._searched,
            "skipped_controls": self._skipped,
            "failed_controls": self._failed,
            "not_supported_controls": self._not_supported,
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
                "all_planned_controls_have_terminal_state": (
                    planned_count == terminal_count
                ),
            },
        }

    def _diagnostic(self, control: ControlInput, **extra: Any) -> dict[str, Any]:
        item_control = _control_dict(control)
        execution_state = extra.get("execution_state")
        offer_count = extra.get("offer_count")
        evidence_type, absence_class = self._evidence_classification(
            item_control, execution_state, offer_count
        )
        item = {
            "type": item_control.get("type") or item_control.get("probe_type"),
            "direction": item_control.get("direction"),
            "origin": item_control.get("origin"),
            "destination": item_control.get("destination"),
            "date": item_control.get("date"),
            "carrier": item_control.get("carrier"),
            "leg": item_control.get("leg"),
            "provider": item_control.get("provider"),
            "negative_evidence": item_control.get("negative_evidence"),
            "evidence_type": evidence_type,
            "absence_class": absence_class,
            "probe_id": item_control.get("probe_id"),
        }
        if "wave_index" in item_control:
            item["wave_index"] = item_control.get("wave_index")
        filters = item_control.get("filters")
        if isinstance(filters, dict) and filters:
            item["filters"] = filters
        for name, value in extra.items():
            if value is not None:
                item[name] = value
        return {name: value for name, value in item.items() if value is not None}

    @staticmethod
    def _evidence_classification(
        control: dict[str, Any], execution_state: Any, offer_count: Any
    ) -> tuple[str | None, str | None]:
        negative_evidence = str(control.get("negative_evidence") or "")
        try:
            count = int(offer_count) if offer_count is not None else None
        except (TypeError, ValueError):
            count = None
        if execution_state == ProbeStatus.SEARCHED and count == 0:
            if "carrier" in negative_evidence:
                return (
                    AbsenceReason.PROVIDER_EMPTY,
                    "provider_empty_not_carrier_absence",
                )
            if "aggregate" in negative_evidence:
                return AbsenceReason.PROVIDER_EMPTY, "provider_empty_not_route_absence"
            return AbsenceReason.PROVIDER_EMPTY, "provider_empty_not_structural_absence"
        if execution_state == ProbeStatus.SEARCHED and count is not None and count > 0:
            return "provider_positive", None
        if execution_state == ProbeStatus.FAILED:
            return (
                AbsenceReason.RUNTIME_PROVIDER_FAILURE,
                AbsenceReason.RUNTIME_PROVIDER_FAILURE,
            )
        if execution_state == ProbeStatus.NOT_SUPPORTED:
            return (
                AbsenceReason.PROVIDER_COVERAGE_GAP,
                AbsenceReason.PROVIDER_COVERAGE_GAP,
            )
        if execution_state == ProbeStatus.SKIPPED:
            return AbsenceReason.CONSTRAINT_MISMATCH, AbsenceReason.CONSTRAINT_MISMATCH
        if execution_state == ProbeStatus.NOT_EXECUTED:
            return "missing_evidence", "not_executed"
        return None, None
