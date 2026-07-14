from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..domain.vocabulary import AbsenceReason, ProbeStatus
from ..ports.providers import ProviderProbeResult
from .probe_intent import ProbeIntent
from .request_deduper import logical_query_key


ProbeInput = dict[str, Any] | Mapping[str, Any] | ProbeIntent


def _probe_dict(probe: ProbeInput) -> dict[str, Any]:
    if isinstance(probe, ProbeIntent):
        return probe.to_probe()
    return dict(probe)


def probe_identity(probe: ProbeInput) -> tuple[Any, ...]:
    return logical_query_key(_probe_dict(probe))


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

    def plan_probes(self, probes: list[ProbeInput]) -> None:
        for probe in probes:
            item = _probe_dict(probe)
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
        self.plan_probes(list(intents))

    def _record_terminal(
        self,
        probe: ProbeInput,
        target: list[dict[str, Any]],
        **extra: Any,
    ) -> None:
        item = _probe_dict(probe)
        probe_id = self._resolve_probe_id(item)
        if probe_id in self._terminal_ids:
            self.record_deduped(item, original_probe_id=probe_id)
            return
        self._terminal_ids.add(probe_id)
        target.append(self._diagnostic(self._planned[probe_id], **extra))

    def record_searched(
        self,
        probe: ProbeInput,
        status: Any,
        provider: Any,
        offer_count: Any,
        cache_status: Any = None,
    ) -> None:
        self._record_terminal(
            probe,
            self._searched,
            execution_state=ProbeStatus.SEARCHED,
            status=status,
            provider=provider,
            offer_count=offer_count,
            cache_status=cache_status,
        )

    def record_skipped(self, probe: ProbeInput, reason: Any) -> None:
        self._record_terminal(
            probe,
            self._skipped,
            execution_state=ProbeStatus.SKIPPED,
            status=ProbeStatus.SKIPPED,
            reason=reason,
        )

    def record_failed(self, probe: ProbeInput, provider: Any, error: Any) -> None:
        self._record_terminal(
            probe,
            self._failed,
            execution_state=ProbeStatus.FAILED,
            status=ProbeStatus.FAILED,
            provider=provider,
            offer_count=0,
            error=error,
        )

    def record_not_supported(
        self, probe: ProbeInput, provider: Any, reason: Any
    ) -> None:
        self._record_terminal(
            probe,
            self._not_supported,
            execution_state=ProbeStatus.NOT_SUPPORTED,
            status=ProbeStatus.NOT_SUPPORTED,
            provider=provider,
            offer_count=0,
            reason=reason,
        )

    def record_provider_result(
        self, probe: ProbeInput, result: ProviderProbeResult
    ) -> None:
        if result.execution_state == ProbeStatus.NOT_SUPPORTED:
            reason = result.result_summary.get("reason")
            if reason is None and result.errors:
                reason = result.errors[0].get("message")
            self.record_not_supported(probe, provider=result.provider, reason=reason)
            return
        if result.execution_state == ProbeStatus.FAILED:
            self.record_failed(
                probe,
                provider=result.provider,
                error=result.errors[0] if result.errors else None,
            )
            return
        self.record_searched(
            probe,
            status=result.result_summary.get("status") or result.execution_state,
            provider=result.provider,
            offer_count=result.result_summary.get("offer_count", len(result.offers)),
            cache_status=result.cache_status,
        )

    def record_deduped(self, probe: ProbeInput, original_probe_id: Any = None) -> None:
        item = _probe_dict(probe)
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

    def to_diagnostics(self) -> dict[str, Any]:
        planned_count = len(self._planned_order)
        terminal_count = len(self._terminal_ids)
        return {
            "negative_evidence_type": "bounded_live_probes_only",
            "planned_probes": [
                self._diagnostic(
                    self._planned[probe_id], execution_state=ProbeStatus.PLANNED
                )
                for probe_id in self._planned_order
            ],
            "searched_probes": self._searched,
            "skipped_probes": self._skipped,
            "failed_probes": self._failed,
            "unsupported_probes": self._not_supported,
            "not_executed_probes": self._not_executed,
            "deduped_probes": self._deduped,
            "coverage_warnings": [
                "segment_absence_is_not_route_absence",
                "provider_empty_is_not_carrier_absence",
                "cache_absence_is_not_negative_evidence",
            ],
            "completeness": {
                "planned_count": planned_count,
                "terminal_count": terminal_count,
                "all_planned_probes_have_terminal_state": (
                    planned_count == terminal_count
                ),
            },
        }

    def _diagnostic(self, probe: ProbeInput, **extra: Any) -> dict[str, Any]:
        item_probe = _probe_dict(probe)
        execution_state = extra.get("execution_state")
        offer_count = extra.get("offer_count")
        evidence_type, absence_class = self._evidence_classification(
            item_probe, execution_state, offer_count
        )
        item = {
            "type": item_probe.get("type") or item_probe.get("probe_type"),
            "direction": item_probe.get("direction"),
            "origin": item_probe.get("origin"),
            "destination": item_probe.get("destination"),
            "date": item_probe.get("date"),
            "carrier": item_probe.get("carrier"),
            "leg": item_probe.get("leg"),
            "provider": item_probe.get("provider"),
            "negative_evidence": item_probe.get("negative_evidence"),
            "evidence_type": evidence_type,
            "absence_class": absence_class,
            "probe_id": item_probe.get("probe_id"),
        }
        filters = item_probe.get("filters")
        if isinstance(filters, dict) and filters:
            item["filters"] = filters
        for name, value in extra.items():
            if value is not None:
                item[name] = value
        return {name: value for name, value in item.items() if value is not None}

    @staticmethod
    def _evidence_classification(
        probe: dict[str, Any], execution_state: Any, offer_count: Any
    ) -> tuple[str | None, str | None]:
        negative_evidence = str(probe.get("negative_evidence") or "")
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
