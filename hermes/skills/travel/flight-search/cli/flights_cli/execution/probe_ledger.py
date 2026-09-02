from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..domain.normalize import normalize_airport_scope, normalize_carrier_code
from ..domain.vocabulary import ProbeStatus
from ..ports.providers import ProviderProbeResult
from .failure_classifier import error_payload_from_provider_result
from .probe_intent import ProbeIntent


ProbeInput = dict[str, Any] | Mapping[str, Any] | ProbeIntent
ProbeKey = tuple[Any, ...]


def _probe_dict(probe: ProbeInput) -> dict[str, Any]:
    if isinstance(probe, ProbeIntent):
        return probe.to_probe()
    return dict(probe)


def _values(item: Mapping[str, Any], name: str) -> tuple[str, ...]:
    filters = item.get("filters") if isinstance(item.get("filters"), Mapping) else {}
    values = item.get(name) or filters.get(name) or []
    return tuple(sorted(str(value).strip().upper() for value in values if value))


def logical_query_key(probe: ProbeInput) -> ProbeKey:
    """Physical provider request identity; diagnostics metadata is excluded."""

    item = _probe_dict(probe)
    filters = item.get("filters") if isinstance(item.get("filters"), Mapping) else {}
    return (
        "provider-query",
        str(item.get("provider") or "").strip().lower(),
        str(item.get("probe_type") or item.get("type") or ""),
        str(item.get("origin") or "").strip().upper(),
        str(item.get("destination") or "").strip().upper(),
        str(item.get("date") or ""),
        str(item.get("return_date") or ""),
        str(item.get("currency") or "").strip().upper(),
        bool(item.get("direct_only", filters.get("direct_only", False))),
        _values(item, "only_carriers"),
        _values(item, "origin_airports"),
        _values(item, "destination_airports"),
        int(item.get("limit") or 0),
    )


@dataclass(frozen=True, slots=True)
class LedgerClaim:
    key: ProbeKey
    probe_id: str
    original_probe_id: str | None = None
    original: Any = None
    execution_allowed: bool = True
    blocked_reason: str | None = None

    @property
    def is_duplicate(self) -> bool:
        return self.original_probe_id is not None


class ProbeRunLedger:
    """The sole owner of planned probes, dedupe, terminal state and failures."""

    def __init__(self, max_physical_attempts: int | None = None) -> None:
        self._planned: dict[str, dict[str, Any]] = {}
        self._planned_order: list[str] = []
        self._logical_originals: dict[ProbeKey, str] = {}
        self._duplicate_of: dict[str, str] = {}
        self._outcomes: dict[str, Any] = {}
        self._terminal_ids: set[str] = set()
        self._searched: list[dict[str, Any]] = []
        self._skipped: list[dict[str, Any]] = []
        self._failed: list[dict[str, Any]] = []
        self._not_supported: list[dict[str, Any]] = []
        self._not_executed: list[dict[str, Any]] = []
        self._deduped: list[dict[str, Any]] = []
        self._counter = 0
        self._max_physical_attempts = (
            max(0, int(max_physical_attempts))
            if max_physical_attempts is not None
            else None
        )
        self._claimed_originals: set[str] = set()

    def _next_probe_id(self) -> str:
        self._counter += 1
        return f"probe-{self._counter:03d}"

    def _new_probe_id(self, item: Mapping[str, Any]) -> str:
        requested = str(item.get("probe_id") or "")
        if requested and requested not in self._planned:
            return requested
        candidate = self._next_probe_id()
        while candidate in self._planned:
            candidate = self._next_probe_id()
        return candidate

    def plan_probes(self, probes: list[ProbeInput]) -> None:
        for probe in probes:
            item = _probe_dict(probe)
            explicit_id = str(item.get("probe_id") or "")
            if explicit_id and explicit_id in self._planned:
                continue
            probe_id = self._new_probe_id(item)
            planned = {**item, "probe_id": probe_id}
            key = logical_query_key(planned)
            original_probe_id = self._logical_originals.get(key)
            self._planned[probe_id] = planned
            self._planned_order.append(probe_id)
            if original_probe_id is None:
                self._logical_originals[key] = probe_id
                continue
            self._duplicate_of[probe_id] = original_probe_id
            self._append_terminal(
                probe_id,
                self._deduped,
                self._diagnostic(
                    planned,
                    execution_state=ProbeStatus.DEDUPED,
                    status=ProbeStatus.DEDUPED,
                    original_probe_id=original_probe_id,
                ),
            )

    def plan_intents(self, intents: list[ProbeIntent]) -> None:
        self.plan_probes(list(intents))

    def claim_probe(self, probe: ProbeInput) -> LedgerClaim:
        item = _probe_dict(probe)
        key = logical_query_key(item)
        existing_original = self._logical_originals.get(key)
        self.plan_probes([item])
        explicit_id = str(item.get("probe_id") or "")
        probe_id = explicit_id if explicit_id in self._planned else ""
        if not probe_id:
            if existing_original is None:
                probe_id = self._logical_originals[key]
            else:
                probe_id = next(
                    reversed(
                        [
                            candidate
                            for candidate in self._planned_order
                            if self._duplicate_of.get(candidate) == existing_original
                        ]
                    ),
                    existing_original,
                )
        key = logical_query_key(self._planned[probe_id])
        original_probe_id = self._duplicate_of.get(probe_id)
        claim = LedgerClaim(
            key=key,
            probe_id=probe_id,
            original_probe_id=original_probe_id,
            original=(
                self._outcomes.get(original_probe_id)
                if original_probe_id is not None
                else None
            ),
        )
        if claim.is_duplicate:
            return claim
        if probe_id in self._terminal_ids:
            return LedgerClaim(
                key=claim.key,
                probe_id=claim.probe_id,
                execution_allowed=False,
                blocked_reason="probe_already_terminal",
            )
        if probe_id in self._claimed_originals:
            return LedgerClaim(
                key=claim.key,
                probe_id=claim.probe_id,
                execution_allowed=False,
                blocked_reason="probe_already_claimed",
            )
        if (
            self._max_physical_attempts is not None
            and len(self._claimed_originals) >= self._max_physical_attempts
        ):
            self.record_not_executed(
                probe_id, reason="provider_attempt_budget_exhausted"
            )
            return LedgerClaim(
                key=claim.key,
                probe_id=claim.probe_id,
                execution_allowed=False,
                blocked_reason="provider_attempt_budget_exhausted",
            )
        self._claimed_originals.add(probe_id)
        return claim

    def claim_segment_probe(
        self,
        *,
        spec: dict[str, Any],
        provider: str,
        plan: dict[str, Any],
        only_carriers: list[str],
        limit: int,
        direct_only: bool = True,
    ) -> LedgerClaim:
        item = {
            **spec,
            "provider": provider,
            "currency": str(plan.get("currency") or "").upper(),
            "direct_only": direct_only,
            "only_carriers": [
                normalize_carrier_code(code, "only-carrier")
                for code in (spec.get("only_carriers") or only_carriers)
            ],
            "origin_airports": normalize_airport_scope(
                list(spec.get("origin_airports") or []), "origin-airport"
            ),
            "destination_airports": normalize_airport_scope(
                list(spec.get("destination_airports") or []), "destination-airport"
            ),
            "limit": int(limit),
        }
        return self.claim_probe(item)

    def record_claim(self, claim: LedgerClaim, outcome: Any) -> None:
        if not claim.is_duplicate:
            self._outcomes[claim.probe_id] = outcome

    def _resolve_probe_id(self, item: dict[str, Any]) -> str:
        explicit = str(item.get("probe_id") or "")
        if explicit in self._planned:
            return explicit
        if explicit:
            self.plan_probes([item])
            return explicit
        original = self._logical_originals.get(logical_query_key(item))
        if original is not None:
            return original
        self.plan_probes([item])
        explicit = str(item.get("probe_id") or "")
        if explicit in self._planned:
            return explicit
        return self._logical_originals[logical_query_key(item)]

    def _append_terminal(
        self,
        probe_id: str,
        target: list[dict[str, Any]],
        diagnostic: dict[str, Any],
    ) -> bool:
        if probe_id in self._terminal_ids:
            return False
        if probe_id not in self._planned:
            raise RuntimeError(f"terminal probe is not planned: {probe_id}")
        self._terminal_ids.add(probe_id)
        target.append(diagnostic)
        return True

    def _record_terminal(
        self,
        probe: ProbeInput,
        target: list[dict[str, Any]],
        **extra: Any,
    ) -> None:
        item = _probe_dict(probe)
        probe_id = self._resolve_probe_id(item)
        if probe_id in self._duplicate_of:
            return
        if probe_id in self._terminal_ids:
            return
        self._append_terminal(
            probe_id,
            target,
            self._diagnostic(self._planned[probe_id], **extra),
        )

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

    def record_not_executed(self, probe: ProbeInput | str, reason: Any) -> None:
        if isinstance(probe, str) and probe in self._planned:
            item: ProbeInput = self._planned[probe]
        else:
            item = probe
        self._record_terminal(
            item,
            self._not_executed,
            execution_state=ProbeStatus.NOT_EXECUTED,
            status=ProbeStatus.NOT_EXECUTED,
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
                error=error_payload_from_provider_result(result),
            )
            return
        if result.execution_state == ProbeStatus.SKIPPED:
            self.record_skipped(
                probe, reason=result.result_summary.get("reason") or "provider_skipped"
            )
            return
        if result.execution_state == ProbeStatus.NOT_EXECUTED:
            self.record_not_executed(
                probe,
                reason=result.result_summary.get("reason") or "provider_not_executed",
            )
            return
        if result.execution_state == ProbeStatus.DEDUPED:
            self.record_deduped(
                probe,
                original_probe_id=result.result_summary.get("original_probe_id"),
            )
            return
        if result.execution_state == ProbeStatus.SEARCHED:
            self.record_searched(
                probe,
                status=result.result_summary.get("status") or result.execution_state,
                provider=result.provider,
                offer_count=result.result_summary.get(
                    "offer_count", len(result.offers)
                ),
                cache_status=result.cache_status,
            )
            return
        raise ValueError(f"unknown provider execution state: {result.execution_state}")

    def record_deduped(self, probe: ProbeInput, original_probe_id: Any = None) -> None:
        item = _probe_dict(probe)
        key = logical_query_key(item)
        expected_original = self._logical_originals.get(key)
        supplied_original = str(original_probe_id or "")
        if expected_original is None:
            raise ValueError("deduped probe must reference a planned original probe")
        if supplied_original and supplied_original != expected_original:
            raise ValueError(
                "deduped probe original_probe_id does not match its logical query"
            )

        explicit_id = str(item.get("probe_id") or "")
        if explicit_id in self._planned:
            if explicit_id == expected_original:
                if explicit_id in self._terminal_ids:
                    return
                raise ValueError("an original planned probe cannot become deduped")
            actual_original = self._duplicate_of.get(explicit_id)
            if actual_original != expected_original:
                raise ValueError(
                    "deduped probe must be a distinct planned logical duplicate"
                )
            if explicit_id not in self._terminal_ids:
                self._append_terminal(
                    explicit_id,
                    self._deduped,
                    self._diagnostic(
                        self._planned[explicit_id],
                        execution_state=ProbeStatus.DEDUPED,
                        status=ProbeStatus.DEDUPED,
                        original_probe_id=expected_original,
                    ),
                )
            return

        before = set(self._planned)
        self.plan_probes([item])
        new_probe_ids = [
            probe_id for probe_id in self._planned_order if probe_id not in before
        ]
        if len(new_probe_ids) != 1:
            raise RuntimeError("deduped probe planning did not create one probe")
        duplicate_id = new_probe_ids[0]
        if self._duplicate_of.get(duplicate_id) != expected_original:
            raise RuntimeError("deduped probe was not linked to its original probe")

    def finalize_unexecuted(self, reason: str = "not_reached_by_execution") -> None:
        for probe_id in self._planned_order:
            if probe_id in self._terminal_ids:
                continue
            self._append_terminal(
                probe_id,
                self._not_executed,
                self._diagnostic(
                    self._planned[probe_id],
                    execution_state=ProbeStatus.NOT_EXECUTED,
                    status=ProbeStatus.NOT_EXECUTED,
                    reason=reason,
                ),
            )

    def _terminal_diagnostics(self) -> list[dict[str, Any]]:
        terminal = [
            *self._searched,
            *self._skipped,
            *self._failed,
            *self._not_supported,
            *self._not_executed,
            *self._deduped,
        ]
        probe_ids = [str(item.get("probe_id") or "") for item in terminal]
        if any(not probe_id for probe_id in probe_ids):
            raise RuntimeError("terminal probe diagnostic is missing probe_id")
        if len(probe_ids) != len(set(probe_ids)):
            raise RuntimeError("a planned probe has more than one terminal state")
        if set(probe_ids) != self._terminal_ids:
            raise RuntimeError("terminal probe index does not match terminal buckets")
        unplanned = set(probe_ids).difference(self._planned)
        if unplanned:
            raise RuntimeError(
                f"terminal state exists for unplanned probes: {sorted(unplanned)}"
            )
        return terminal

    def to_diagnostics(self) -> dict[str, Any]:
        self._terminal_diagnostics()
        return {
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
        }

    def _diagnostic(self, probe: ProbeInput, **extra: Any) -> dict[str, Any]:
        item_probe = _probe_dict(probe)
        item = {
            "type": item_probe.get("type") or item_probe.get("probe_type"),
            "phase": item_probe.get("phase"),
            "trigger": item_probe.get("trigger"),
            "direction": item_probe.get("direction"),
            "origin": item_probe.get("origin"),
            "destination": item_probe.get("destination"),
            "date": item_probe.get("date"),
            "carrier": item_probe.get("carrier"),
            "leg": item_probe.get("leg"),
            "provider": item_probe.get("provider"),
            "negative_evidence": item_probe.get("negative_evidence"),
            "probe_id": item_probe.get("probe_id"),
        }
        filters = item_probe.get("filters")
        if isinstance(filters, dict) and filters:
            item["filters"] = filters
        for name, value in extra.items():
            if value is not None:
                item[name] = value
        return {name: value for name, value in item.items() if value is not None}


__all__ = [
    "LedgerClaim",
    "ProbeRunLedger",
    "logical_query_key",
]
