"""Прямая проба одного дня — общий словарь исполнения и отчёта.

Исполнитель складывал прямой инвентарь двумя списками словарей: один нёс
статус пробы, другой — её предложения, оба под одним и тем же фильтром и с
одними и теми же семью первыми ключами. Из двадцати ключей окно дат читало
четыре, и они здесь.

Запись живёт в `domain`, потому что производит её `execution`, а читает
`reporting`, и напрямую эти слои друг друга не видят.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DirectInventoryProbe:
    """Один прямой запрос за один день: столько, сколько читает окно дат."""

    leg: str
    date: str
    status: str
    offer_count: int


__all__ = ["DirectInventoryProbe"]
