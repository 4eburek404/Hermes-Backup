from __future__ import annotations

from typing import Any, Mapping

from .constants import CANON_AMOUNT, CANON_DATE, CANONICAL_COLUMNS, COLUMN_HINTS, REQUIRED_COLUMNS
from .models import TableSchema
from .money import parse_amount
from .text import compact, looks_like_date, norm, text_value


def _header_score(header: str, canonical: str) -> int:
    h = norm(header)
    hc = compact(header)
    score = 0
    for hint in COLUMN_HINTS[canonical]:
        nh = norm(hint)
        if h == nh:
            score = max(score, 100)
        elif h.startswith(nh) or nh in h:
            score = max(score, 85)
        elif compact(hint) in hc:
            score = max(score, 75)
    return score


def _find_header_by_name(header: list[Any], requested: str) -> int | None:
    requested_norm = norm(requested)
    for index, cell in enumerate(header):
        if norm(cell) == requested_norm:
            return index
    return None


def _best_mapping_for_header(rows: list[list[Any]], header_row_index: int) -> tuple[int, dict[str, int]]:
    header = rows[header_row_index]
    mapping: dict[str, int] = {}
    used: set[int] = set()
    total = 0
    for canonical in CANONICAL_COLUMNS:
        candidates = [(_header_score(text_value(cell), canonical), col_idx) for col_idx, cell in enumerate(header)]
        score, col_idx = max(candidates, default=(0, -1))
        if score >= 60 and col_idx not in used:
            mapping[canonical] = col_idx
            used.add(col_idx)
            total += score

    sample = rows[header_row_index + 1: header_row_index + 31]
    if CANON_AMOUNT in mapping:
        amount_col = mapping[CANON_AMOUNT]
        numeric = sum(parse_amount(r[amount_col] if amount_col < len(r) else None) is not None for r in sample)
        total += min(numeric * 4, 70)
    if CANON_DATE in mapping:
        date_col = mapping[CANON_DATE]
        dates = sum(looks_like_date(r[date_col] if date_col < len(r) else None) for r in sample)
        total += min(dates * 3, 50)
    return total, mapping


def detect_schema(rows: list[list[Any]], *, overrides: Mapping[str, str] | None = None) -> TableSchema:
    if not rows:
        raise ValueError("Файл пуст")

    best: tuple[int, int, dict[str, int]] | None = None
    for row_idx in range(min(15, len(rows))):
        score, mapping = _best_mapping_for_header(rows, row_idx)
        if best is None or score > best[0]:
            best = (score, row_idx, mapping)

    if not best or best[0] < 250:
        raise ValueError("Не удалось надежно определить строку заголовков и ключевые колонки")

    _, header_row_index, mapping = best
    header = rows[header_row_index]

    if overrides:
        for canonical, column_name in overrides.items():
            if not column_name:
                continue
            column_index = _find_header_by_name(header, column_name)
            if column_index is None:
                raise ValueError(f"Колонка {column_name!r} не найдена в строке заголовков")
            mapping[canonical] = column_index

    missing = [column for column in REQUIRED_COLUMNS if column not in mapping]
    if missing:
        raise ValueError(f"Не найдены обязательные колонки: {', '.join(missing)}")

    column_names = {canonical: text_value(header[index]) for canonical, index in mapping.items() if index < len(header)}
    return TableSchema(header_row_index=header_row_index, column_indexes=mapping, column_names=column_names)


def get_cell(row: list[Any], schema: TableSchema, canonical: str) -> Any:
    index = schema.column_indexes.get(canonical)
    if index is None or index >= len(row):
        return None
    return row[index]
