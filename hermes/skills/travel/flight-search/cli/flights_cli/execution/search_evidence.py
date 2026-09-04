"""Свидетельство одного прогона: только то, что произвели провайдеры.

Здесь лежал ещё и сериализованный план — весь `plan.to_dict()`, замороженный
целиком ради одного ключа `route`. План типизирован и неизменяем сам по себе,
и до решения он доезжает объектом; второй, словарный, экземпляр того же
маршрута был копией, способной разойтись с оригиналом.

Прямой инвентарь тоже был двумя списками словарей вместо одного: исполнитель
дважды проходил один и тот же фильтр и складывал двадцать ключей, из которых
окно дат читало четыре.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..domain.direct_inventory import DirectInventoryProbe
from ..domain.immutable import freeze


@dataclass(frozen=True, slots=True)
class SearchEvidence:
    """Frozen snapshot of all provider execution used by one decision pass."""

    primary_offer_results: tuple[dict[str, Any], ...]
    probe_ledger: dict[str, Any]
    direct_inventory: tuple[DirectInventoryProbe, ...]

    @classmethod
    def freeze(
        cls,
        *,
        primary_offer_results: list[dict[str, Any]],
        probe_ledger: dict[str, Any],
        direct_inventory: list[DirectInventoryProbe],
    ) -> SearchEvidence:
        return cls(
            primary_offer_results=tuple(freeze(primary_offer_results)),
            probe_ledger=freeze(probe_ledger),
            direct_inventory=tuple(direct_inventory),
        )
