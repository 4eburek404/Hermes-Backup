from __future__ import annotations

from typing import Any


def minutes_label(value: Any) -> str | None:
    if value is None:
        return None
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return None
    hours, mins = divmod(max(0, minutes), 60)
    if hours and mins:
        return f"{hours}h{mins:02d}"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


def price_label(amount: Any, currency: Any) -> str:
    if amount is None:
        return "price n/a"
    try:
        number = int(amount)
    except (TypeError, ValueError):
        return f"{amount} {currency or ''}".strip()
    return f"{number:,} {currency or ''}".replace(",", " ").strip()
