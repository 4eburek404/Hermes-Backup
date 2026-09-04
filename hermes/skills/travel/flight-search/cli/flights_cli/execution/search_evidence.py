"""Свидетельство одного прогона: только то, что произвели провайдеры.

Здесь лежал ещё и сериализованный план — весь `plan.to_dict()`, замороженный
целиком ради одного ключа `route`. План типизирован и неизменяем сам по себе,
и до решения он доезжает объектом; второй, словарный, экземпляр того же
маршрута был копией, способной разойтись с оригиналом.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..domain.immutable import freeze


@dataclass(frozen=True, slots=True)
class SearchEvidence:
    """Frozen snapshot of all provider execution used by one decision pass."""

    primary_offer_results: tuple[dict[str, Any], ...]
    probe_ledger: dict[str, Any]
    direct_inventory_searches: tuple[dict[str, Any], ...]
    direct_inventory_results: tuple[dict[str, Any], ...]

    @classmethod
    def freeze(
        cls,
        *,
        primary_offer_results: list[dict[str, Any]],
        probe_ledger: dict[str, Any],
        direct_inventory_searches: list[dict[str, Any]],
        direct_inventory_results: list[dict[str, Any]],
    ) -> SearchEvidence:
        return cls(
            primary_offer_results=tuple(freeze(primary_offer_results)),
            probe_ledger=freeze(probe_ledger),
            direct_inventory_searches=tuple(freeze(direct_inventory_searches)),
            direct_inventory_results=tuple(freeze(direct_inventory_results)),
        )
