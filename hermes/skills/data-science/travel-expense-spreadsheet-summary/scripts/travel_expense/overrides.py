from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import VALID_CATEGORIES


@dataclass(frozen=True)
class OverrideDecision:
    category: str
    reason: str = "ручное переопределение"


def _valid_category(category: Any) -> str | None:
    if isinstance(category, str) and category in VALID_CATEGORIES:
        return category
    return None


def load_overrides(path: Path | None) -> dict[str, OverrideDecision]:
    if not path:
        return {}
    if not path.exists():
        raise FileNotFoundError(f"Файл overrides не найден: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, OverrideDecision] = {}
    if not isinstance(data, dict):
        raise ValueError("overrides должен быть JSON-объектом")

    # Simple compatible format: {"fingerprint": "Авиа"}
    for key, value in data.items():
        category = _valid_category(value)
        if category:
            result[str(key)] = OverrideDecision(category=category)

    # Preferred format: {"rows": {"fingerprint": {"category": "Авиа", "reason": "..."}}}
    rows = data.get("rows")
    if isinstance(rows, dict):
        for key, value in rows.items():
            if isinstance(value, dict):
                category = _valid_category(value.get("category"))
                reason = str(value.get("reason") or "ручное переопределение по fingerprint")
            else:
                category = _valid_category(value)
                reason = "ручное переопределение по fingerprint"
            if category:
                result[str(key)] = OverrideDecision(category=category, reason=reason)

    # Legacy list format.
    row_overrides = data.get("row_overrides")
    if isinstance(row_overrides, list):
        for item in row_overrides:
            if not isinstance(item, dict):
                continue
            fingerprint = item.get("fingerprint") or item.get("row_number")
            category = _valid_category(item.get("category"))
            if fingerprint and category:
                result[str(fingerprint)] = OverrideDecision(
                    category=category,
                    reason=str(item.get("reason") or "ручное переопределение"),
                )
    return result
