from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from .classifier import classify_category
from .constants import (
    CANON_AMOUNT,
    CANON_CARRIER,
    CANON_DATE,
    CANON_DETAILS,
    CATEGORY_ORDER,
    CATEGORY_TOTAL,
    CATEGORY_UNKNOWN,
)
from .io import read_rows
from .models import ClassifiedRow
from .money import format_money, parse_amount
from .normalizer import normalize_row
from .overrides import load_overrides
from .row_types import classify_row_kind
from .schema import detect_schema
from .text import text_value


def _summary_row(category: str, bookings: int, amount: float) -> dict[str, Any]:
    amount = round(float(amount), 2)
    return {
        "category": category,
        "bookings": int(bookings),
        "amount": amount,
        "amount_display": format_money(amount),
    }


def _extract_total_count(total_rows: list[dict[str, Any]]) -> int | None:
    for row in total_rows:
        for value in row.get("raw_values", []):
            parsed = parse_amount(value)
            if parsed is not None and float(parsed).is_integer():
                amount = row.get("amount")
                if amount is None or abs(float(parsed) - float(amount)) > 0.01:
                    return int(parsed)
    return None


def analyze_file(
    path: Path,
    *,
    sheet: str | int | None = None,
    overrides_path: Path | None = None,
    column_overrides: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    rows = read_rows(path, sheet=sheet)
    schema = detect_schema(rows, overrides=column_overrides)
    override_map = load_overrides(overrides_path)
    data_rows = rows[schema.header_row_index + 1:]
    last_source_row = schema.header_row_index + 1 + len(data_rows)

    classified: list[ClassifiedRow] = []
    total_rows: list[dict[str, Any]] = []
    service_rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for source_row, raw_row in enumerate(data_rows, start=schema.header_row_index + 2):
        row = normalize_row(raw_row, source_row=source_row, schema=schema)
        row_kind = classify_row_kind(row, last_source_row=last_source_row)

        if row_kind.kind == "total":
            total_rows.append({
                "row_number": source_row,
                "amount": row.amount,
                "preview": text_value(" ".join(text_value(v) for v in raw_row))[:180],
                "raw_values": raw_row,
                "reason": row_kind.reason,
            })
            continue

        if row_kind.kind == "total_formula_error":
            total_rows.append({
                "row_number": source_row,
                "amount": None,
                "preview": text_value(" ".join(text_value(v) for v in raw_row))[:180],
                "raw_values": raw_row,
                "reason": row_kind.reason,
            })
            warnings.append({"type": "total_formula_error", "row_number": source_row, "message": row_kind.reason})
            continue

        if row_kind.kind != "booking":
            service_rows.append({
                "row_number": source_row,
                "row_kind": row_kind.kind,
                "reason": row_kind.reason,
                "preview": text_value(" ".join(text_value(v) for v in raw_row))[:180],
            })
            continue

        if row.amount is None:
            service_rows.append({"row_number": source_row, "row_kind": "non_numeric_amount", "reason": "сумма не распознана"})
            continue

        category, reason, needs_review = classify_category(row.carrier, row.details)
        override_applied = False
        decision = override_map.get(row.fingerprint) or override_map.get(str(source_row))
        if decision:
            category = decision.category
            reason = decision.reason
            needs_review = False
            override_applied = True

        classified.append(ClassifiedRow(
            row_number=source_row,
            fingerprint=row.fingerprint,
            category=category,
            amount=row.amount,
            amount_display=format_money(row.amount),
            carrier=row.carrier,
            details=row.details,
            reason=reason,
            needs_review=needs_review,
            override_applied=override_applied,
        ))

    counts: dict[str, int] = {category: 0 for category in CATEGORY_ORDER}
    sums: dict[str, float] = {category: 0.0 for category in CATEGORY_ORDER}
    for row in classified:
        counts.setdefault(row.category, 0)
        sums.setdefault(row.category, 0.0)
        counts[row.category] += 1
        sums[row.category] = round(sums[row.category] + row.amount, 2)

    total_count = len(classified)
    total_sum = round(sum(row.amount for row in classified), 2)
    summary = [_summary_row(category, counts.get(category, 0), sums.get(category, 0.0)) for category in CATEGORY_ORDER]
    summary.append(_summary_row(CATEGORY_TOTAL, total_count, total_sum))

    first_numeric_total = next((row for row in total_rows if row.get("amount") is not None), None)
    source_total_sum = first_numeric_total.get("amount") if first_numeric_total else None
    source_total_count = _extract_total_count(total_rows)
    sum_matches = None if source_total_sum is None else abs(float(source_total_sum) - total_sum) < 0.01
    count_matches = None if source_total_count is None else source_total_count == total_count

    if sum_matches is False:
        warnings.append({
            "type": "source_total_sum_mismatch",
            "message": "сумма по категориям не совпадает с исходной итоговой строкой",
            "calculated": total_sum,
            "source_total_sum": source_total_sum,
        })
    if count_matches is False:
        warnings.append({
            "type": "source_total_count_mismatch",
            "message": "количество строк по категориям не совпадает с исходным счетчиком",
            "calculated": total_count,
            "source_total_count": source_total_count,
        })

    classified_dicts = [asdict(row) for row in classified]
    review_rows = [row for row in classified_dicts if row["needs_review"] or row["category"] == CATEGORY_UNKNOWN]
    unknown_rows = [row for row in classified_dicts if row["category"] == CATEGORY_UNKNOWN]

    return {
        "source_file": path.name,
        "schema": {
            "header_row": schema.header_row_index + 1,
            "columns": {canonical: index + 1 for canonical, index in schema.column_indexes.items()},
            "column_names": schema.column_names,
        },
        "summary": summary,
        "verification": {
            "booking_rows": total_count,
            "category_rows": sum(counts.values()),
            "category_sum": total_sum,
            "source_total_present": bool(total_rows),
            "source_total_count": source_total_count,
            "source_total_sum": source_total_sum,
            "source_total_count_matches": count_matches,
            "source_total_sum_matches": sum_matches,
            "total_rows": [{k: v for k, v in row.items() if k != "raw_values"} for row in total_rows],
            "service_rows": service_rows,
        },
        "unknown_rows": unknown_rows,
        "review_rows": review_rows,
        "warnings": warnings,
    }
