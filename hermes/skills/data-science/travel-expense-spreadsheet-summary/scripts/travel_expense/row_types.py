from __future__ import annotations

from .models import NormalizedRow, RowKind
from .money import parse_amount
from .text import TOTAL_LABEL_RE, is_formula_error, norm, row_text, text_value


def classify_row_kind(row: NormalizedRow, *, last_source_row: int) -> RowKind:
    text = row_text(row.raw_values)
    if not text:
        return RowKind("blank", "пустая строка")

    has_formula_error = any(is_formula_error(value) for value in row.raw_values)
    has_total_label = bool(TOTAL_LABEL_RE.search(norm(text)))
    empty_date_carrier = not row.date and not row.carrier
    near_bottom = row.source_row >= max(1, last_source_row - 5)

    if has_total_label:
        if has_formula_error:
            return RowKind("total_formula_error", "итоговая строка найдена, но содержит ошибку формулы")
        return RowKind("total", "явная итоговая строка")

    if has_formula_error:
        return RowKind("formula_error", "строка содержит ошибку формулы")

    if empty_date_carrier and row.amount is not None and near_bottom:
        return RowKind("total", "похоже на нижнюю итоговую строку без явного ярлыка")

    if empty_date_carrier and row.amount is not None:
        details_as_count = parse_amount(row.details)
        if details_as_count is not None and float(details_as_count).is_integer():
            return RowKind("total", "похоже на итоговую строку: пустые дата/перевозчик, число в деталях и сумма")

    if row.amount is None:
        return RowKind("non_numeric_amount", "сумма не распознана как число")

    return RowKind("booking", "строка бронирования")
