from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TableSchema:
    header_row_index: int
    column_indexes: dict[str, int]
    column_names: dict[str, str]


@dataclass(frozen=True)
class NormalizedRow:
    source_row: int
    date: str
    carrier: str
    details: str
    amount_cell: Any
    amount: float | None
    raw_values: list[Any]


@dataclass(frozen=True)
class RowKind:
    kind: str
    reason: str


@dataclass
class ClassifiedRow:
    row_number: int
    category: str
    amount: float
    amount_display: str
    carrier: str
    details: str
    reason: str
    needs_review: bool
    override_applied: bool = False
    override_name: str = ""
    row_kind: str = "booking"
