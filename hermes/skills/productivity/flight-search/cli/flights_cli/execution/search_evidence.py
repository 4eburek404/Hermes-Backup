from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..domain.immutable import freeze, thaw


_TRACE_PRIVATE_FIELDS = frozenset(
    {
        "endpoint",
        "endpoint_url",
        "fli_mcp_url",
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
    failures: tuple[dict[str, Any], ...]
    direct_mode: dict[str, bool]
    max_connections_by_direction: dict[str, int]
    direct_presence_gate: dict[str, Any]
    direct_inventory_searches: tuple[dict[str, Any], ...]
    direct_inventory_results: tuple[dict[str, Any], ...]
    date_window_inventory: dict[str, Any] | None

    @property
    def route_context(self) -> dict[str, Any]:
        context = self.search_plan.get("route_context")
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
        failures: list[dict[str, Any]],
        direct_mode: dict[str, bool],
        max_connections_by_direction: dict[str, int],
        direct_presence_gate: dict[str, Any],
        direct_inventory_searches: list[dict[str, Any]],
        direct_inventory_results: list[dict[str, Any]],
        date_window_inventory: dict[str, Any] | None,
    ) -> SearchEvidence:
        return cls(
            search_plan=freeze(search_plan),
            provider_policy=str(provider_policy),
            primary_offer_results=tuple(freeze(primary_offer_results)),
            gateway_leg_results=freeze(gateway_leg_results),
            observed_gateway_diagnostics=freeze(observed_gateway_diagnostics),
            probe_ledger=freeze(probe_ledger),
            failures=tuple(freeze(failures)),
            direct_mode=freeze(direct_mode),
            max_connections_by_direction=freeze(max_connections_by_direction),
            direct_presence_gate=freeze(direct_presence_gate),
            direct_inventory_searches=tuple(freeze(direct_inventory_searches)),
            direct_inventory_results=tuple(freeze(direct_inventory_results)),
            date_window_inventory=freeze(date_window_inventory),
        )

    def to_trace_dict(self) -> dict[str, Any]:
        payload = {
            "provider_policy": self.provider_policy,
            "primary_offer_results": thaw(self.primary_offer_results),
            "gateway_leg_results": thaw(self.gateway_leg_results),
            "observed_gateway_diagnostics": thaw(self.observed_gateway_diagnostics),
            "probe_ledger": thaw(self.probe_ledger),
            "failures": thaw(self.failures),
            "direct_mode": thaw(self.direct_mode),
            "max_connections_by_direction": thaw(self.max_connections_by_direction),
            "direct_presence_gate": thaw(self.direct_presence_gate),
        }
        if self.date_window_inventory is not None:
            payload["date_window_inventory"] = thaw(self.date_window_inventory)
        return _trace_safe(payload)
