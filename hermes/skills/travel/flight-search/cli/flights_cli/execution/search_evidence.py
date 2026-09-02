from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..domain.immutable import freeze, thaw


_TRACE_PRIVATE_FIELDS = frozenset(
    {
        "endpoint",
        "endpoint_url",
        "mcp_url",
        "provider_payload",
        "raw_payload",
        "raw_provider_payload",
        "raw_response",
        "session_id",
        "url",
    }
)


def _trace_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _trace_safe(item)
            for key, item in value.items()
            if key not in _TRACE_PRIVATE_FIELDS
        }
    if isinstance(value, (list, tuple)):
        return [_trace_safe(item) for item in value]
    return thaw(value)


@dataclass(frozen=True, slots=True)
class SearchEvidence:
    """Frozen snapshot of all provider execution used by one decision pass."""

    search_plan: dict[str, Any]
    provider_policy: str
    primary_offer_results: tuple[dict[str, Any], ...]
    gateway_leg_results: dict[str, Any]
    observed_gateway_diagnostics: dict[str, Any]
    probe_ledger: dict[str, Any]
    direct_presence_gate: dict[str, Any]
    direct_inventory_searches: tuple[dict[str, Any], ...]
    direct_inventory_results: tuple[dict[str, Any], ...]

    @property
    def route_context(self) -> dict[str, Any]:
        context = self.search_plan.get("route")
        return context if isinstance(context, dict) else {}

    @classmethod
    def freeze(
        cls,
        *,
        search_plan: dict[str, Any],
        provider_policy: str,
        primary_offer_results: list[dict[str, Any]],
        gateway_leg_results: dict[str, Any],
        observed_gateway_diagnostics: dict[str, Any],
        probe_ledger: dict[str, Any],
        direct_presence_gate: dict[str, Any],
        direct_inventory_searches: list[dict[str, Any]],
        direct_inventory_results: list[dict[str, Any]],
    ) -> SearchEvidence:
        return cls(
            search_plan=freeze(search_plan),
            provider_policy=str(provider_policy),
            primary_offer_results=tuple(freeze(primary_offer_results)),
            gateway_leg_results=freeze(gateway_leg_results),
            observed_gateway_diagnostics=freeze(observed_gateway_diagnostics),
            probe_ledger=freeze(probe_ledger),
            direct_presence_gate=freeze(direct_presence_gate),
            direct_inventory_searches=tuple(freeze(direct_inventory_searches)),
            direct_inventory_results=tuple(freeze(direct_inventory_results)),
        )

    def to_trace_dict(self) -> dict[str, Any]:
        probe_ledger = thaw(self.probe_ledger)
        failures = [
            dict(item)
            for item in probe_ledger.get("failed_probes") or []
            if isinstance(item, dict)
        ]
        payload = {
            "provider_policy": self.provider_policy,
            "primary_offer_results": thaw(self.primary_offer_results),
            "gateway_leg_results": thaw(self.gateway_leg_results),
            "observed_gateway_diagnostics": thaw(self.observed_gateway_diagnostics),
            "probe_ledger": probe_ledger,
            "failures": failures,
            "direct_presence_gate": thaw(self.direct_presence_gate),
        }
        return _trace_safe(payload)
