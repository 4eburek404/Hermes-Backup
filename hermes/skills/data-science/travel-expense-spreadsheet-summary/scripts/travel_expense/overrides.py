from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import VALID_CATEGORIES
from .text import norm, text_value


@dataclass(frozen=True)
class PatternOverride:
    category: str
    reason: str
    carrier_contains: tuple[str, ...] = ()
    details_contains: tuple[str, ...] = ()
    carrier_regex: str | None = None
    details_regex: str | None = None
    needs_review: bool = False
    name: str = ""


def _valid_category(category: Any) -> str | None:
    if isinstance(category, str) and category in VALID_CATEGORIES:
        return category
    return None


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        stripped = value.strip()
        return (stripped,) if stripped else ()
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _has_matcher(item: dict[str, Any]) -> bool:
    return any(
        item.get(key)
        for key in ("carrier_contains", "details_contains", "carrier_regex", "details_regex")
    )


def _compile_regex(pattern: Any, *, field_name: str) -> str | None:
    if pattern in (None, ""):
        return None
    pattern_text = str(pattern)
    try:
        re.compile(pattern_text, flags=re.IGNORECASE)
    except re.error as exc:
        raise ValueError(f"Некорректный regex в overrides ({field_name}={pattern_text!r}): {exc}") from exc
    return pattern_text


def _looks_like_old_point_override(data: dict[str, Any]) -> bool:
    allowed_top_level = {"version", "pattern_overrides", "patterns", "notes", "description"}
    return any(key not in allowed_top_level for key in data.keys())


def _parse_pattern_override(item: dict[str, Any], *, index: int) -> PatternOverride:
    category = _valid_category(item.get("category"))
    if category is None:
        raise ValueError(f"Некорректная категория в pattern_overrides[{index}]: {item.get('category')!r}")
    if not _has_matcher(item):
        raise ValueError(
            f"pattern_overrides[{index}] не содержит условий. "
            "Добавьте carrier_contains/details_contains/carrier_regex/details_regex."
        )
    if not any(item.get(key) for key in ("details_contains", "details_regex")):
        raise ValueError(
            f"pattern_overrides[{index}] слишком широкое. "
            "Добавьте условие по details_contains или details_regex."
        )
    return PatternOverride(
        category=category,
        reason=str(item.get("reason") or "ручное правило пользователя"),
        carrier_contains=_as_tuple(item.get("carrier_contains")),
        details_contains=_as_tuple(item.get("details_contains")),
        carrier_regex=_compile_regex(item.get("carrier_regex"), field_name="carrier_regex"),
        details_regex=_compile_regex(item.get("details_regex"), field_name="details_regex"),
        needs_review=bool(item.get("needs_review", False)),
        name=str(item.get("name") or f"pattern_overrides[{index}]"),
    )


def load_overrides(path: Path | None) -> list[PatternOverride]:
    """Load reusable user pattern overrides.

    Overrides are not point corrections for a single spreadsheet row. They are
    narrow reusable rules, for example: carrier contains `ВАЙТ ТРЕВЕЛ` and
    details match `Шэньчжэнь-Сиань` => `Авиа`.
    """
    if not path:
        return []
    if not path.exists():
        raise FileNotFoundError(f"Файл overrides не найден: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("overrides должен быть JSON-объектом")

    if _looks_like_old_point_override(data):
        raise ValueError(
            "Точечные overrides для отдельных строк больше не поддерживаются. "
            "Используйте pattern_overrides с условиями по carrier/details."
        )

    items = data.get("pattern_overrides", data.get("patterns", []))
    if items is None:
        items = []
    if not isinstance(items, list):
        raise ValueError("pattern_overrides должен быть списком")

    return [_parse_pattern_override(item, index=index) for index, item in enumerate(items) if isinstance(item, dict)]


def _contains_all(text: str, needles: tuple[str, ...]) -> bool:
    normalized = norm(text)
    return all(norm(needle) in normalized for needle in needles)


def _regex_matches(text: str, pattern: str | None) -> bool:
    if not pattern:
        return True
    raw = text_value(text)
    normalized = norm(text)
    return bool(re.search(pattern, raw, flags=re.IGNORECASE) or re.search(pattern, normalized, flags=re.IGNORECASE))


def match_override(carrier: str, details: str, overrides: list[PatternOverride]) -> PatternOverride | None:
    for item in overrides:
        if item.carrier_contains and not _contains_all(carrier, item.carrier_contains):
            continue
        if item.details_contains and not _contains_all(details, item.details_contains):
            continue
        if not _regex_matches(carrier, item.carrier_regex):
            continue
        if not _regex_matches(details, item.details_regex):
            continue
        return item
    return None
