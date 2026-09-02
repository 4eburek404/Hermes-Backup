from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..domain.immutable import freeze


@dataclass(frozen=True, slots=True)
class SearchEvidence:
    """Frozen snapshot of all provider execution used by one decision pass."""

    search_plan: dict[str, Any]
    provider_policy: str
    primary_offer_results: tuple[dict[str, Any], ...]
    probe_ledger: dict[str, Any]
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
        probe_ledger: dict[str, Any],
        direct_inventory_searches: list[dict[str, Any]],
        direct_inventory_results: list[dict[str, Any]],
    ) -> SearchEvidence:
        return cls(
            search_plan=freeze(search_plan),
            provider_policy=str(provider_policy),
            primary_offer_results=tuple(freeze(primary_offer_results)),
            probe_ledger=freeze(probe_ledger),
            direct_inventory_searches=tuple(freeze(direct_inventory_searches)),
            direct_inventory_results=tuple(freeze(direct_inventory_results)),
        )
