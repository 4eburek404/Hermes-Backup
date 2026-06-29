#!/usr/bin/env python3
"""Summarize travel-expense spreadsheets by air, rail, and hotel spend.

The script is intentionally colocated with the Hermes skill so the agent can run a
stable implementation instead of rebuilding pandas snippets from SKILL.md.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

CATEGORY_AIR = "Авиа"
CATEGORY_RAIL = "ЖД"
CATEGORY_HOTEL = "Проживание в отелях"
CATEGORY_UNKNOWN = "Unknown"
CATEGORY_TOTAL = "ИТОГО"
CATEGORY_ORDER = [CATEGORY_AIR, CATEGORY_RAIL, CATEGORY_HOTEL, CATEGORY_UNKNOWN]

RAIL_MARKERS = ["ржд", "жд", "ж/д", "гранд сервис", "аэроэкспресс", "аэроэскпресс"]
AIRLINE_MARKERS = [
    "авиа", "аэрофлот", "победа", "air ", "airlines", "airways", "turkish",
    "ютэйр", "red wings", "ред вингс", "нордстар", "nordstar", "ювт аэро", "ювтаэро",
    "уральские", "северсталь", "belavia", "indigo", "hainan",
    "tianjin", "china eastern", "china southern", "china united",
    "spring", "s7", "с7", "emirates", "etihad", "fly dubai", "flydubai", "nordwind", "нордвинд",
]
MIXED_SERVICE_MARKERS = ["trip.com", "trip com", "trip", "вайт тревел"]
HOTEL_VENDOR_MARKERS = ["яндекс", "дубльгис", "комфорт букинг", "гостиниц"]
TOTAL_LABELS = {"итог", "total", "grand total"}


def _is_nan(value: Any) -> bool:
    try:
        return bool(value != value)  # NaN is not equal to itself.
    except Exception:
        return False


def text_value(value: Any) -> str:
    if value is None or _is_nan(value):
        return ""
    return str(value).strip()


def lower_value(value: Any) -> str:
    return text_value(value).lower()


def parse_amount(value: Any) -> float:
    """Parse Russian/Excel-style amount values into float."""
    if value is None or _is_nan(value):
        raise ValueError("Нечисловая сумма: пустое значение")

    if isinstance(value, (int, float)):
        return round(float(value), 2)

    original = str(value)
    s = original.strip().replace("\u00a0", " ").replace("₽", "")
    s = re.sub(r"(?i)руб\.?", "", s)
    s = re.sub(r"[^0-9,\.\- ]", "", s).strip()
    if not s:
        raise ValueError(f"Нечисловая сумма: {original!r}")

    # Russian format is normally `1 234,56`. Support `1,234.56` too.
    s = s.replace(" ", "")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")

    try:
        return round(float(s), 2)
    except ValueError as exc:
        raise ValueError(f"Нечисловая сумма: {original!r}") from exc


def format_money(amount: float) -> str:
    formatted = f"{amount:,.2f}".replace(",", " ").replace(".", ",")
    return f"{formatted} ₽"


def classify_record(
    record: Mapping[str, Any],
    *,
    carrier_col: str = "Перевозчик",
    details_col: str = "Детали",
) -> str:
    carrier = lower_value(record.get(carrier_col))
    details = lower_value(record.get(details_col))
    text = f"{carrier} {details}"

    if any(marker in details for marker in ("прожив", "апартамент", "поздний выезд")):
        return CATEGORY_HOTEL

    # If the carrier itself is an airline, it's aviation — regardless of
    # what organisation name appears in the trip details (e.g. "РЖД" as
    # a destination company in "Конструкторское бюро РЖД").
    if any(marker in carrier for marker in AIRLINE_MARKERS):
        return CATEGORY_AIR

    if any(marker in text for marker in RAIL_MARKERS):
        return CATEGORY_RAIL

    # Airline marker only in details (e.g. empty carrier, route description).
    if any(marker in text for marker in AIRLINE_MARKERS):
        return CATEGORY_AIR

    return CATEGORY_UNKNOWN


def _first_column_name(record: Mapping[str, Any]) -> str | None:
    return next(iter(record.keys()), None)


def is_total_row(
    record: Mapping[str, Any],
    *,
    date_col: str = "Дата",
    carrier_col: str = "Перевозчик",
) -> bool:
    first_col = _first_column_name(record)
    candidates = [record.get(date_col)]
    if first_col and first_col != date_col:
        candidates.append(record.get(first_col))
    # Also check all column values — some files put "ИТОГО:" in Детали
    # with an empty date column.
    candidates.extend(record.values())
    if any(lower_value(value) in TOTAL_LABELS or lower_value(value).startswith("итого") for value in candidates):
        return True
    # Fallback: empty date + empty carrier → total row (some files have
    # only a count in Детали and the total sum in Сумма, with no "ИТОГО" label).
    date_val = lower_value(record.get(date_col))
    carrier_val = lower_value(record.get(carrier_col))
    if not date_val and not carrier_val:
        return True
    return False


def _source_total_count(total_row: Mapping[str, Any], amount_col: str) -> int | None:
    for key, value in total_row.items():
        if key == amount_col:
            continue
        try:
            parsed = parse_amount(value)
        except ValueError:
            continue
        if parsed.is_integer():
            return int(parsed)
    return None


def _make_summary_row(category: str, bookings: int, amount: float) -> dict[str, Any]:
    rounded = round(float(amount), 2)
    return {
        "category": category,
        "bookings": int(bookings),
        "amount": rounded,
        "amount_display": format_money(rounded),
    }


def _warning_row(
    warning_type: str,
    row_number: int,
    category: str,
    record: Mapping[str, Any],
    *,
    carrier_col: str,
    details_col: str,
) -> dict[str, Any]:
    return {
        "type": warning_type,
        "row_number": row_number,
        "category": category,
        "carrier": text_value(record.get(carrier_col)),
        "details_preview": text_value(record.get(details_col))[:160],
    }


def summarize_records(
    records: Iterable[Mapping[str, Any]],
    *,
    amount_col: str = "Сумма",
    carrier_col: str = "Перевозчик",
    details_col: str = "Детали",
    date_col: str = "Дата",
) -> dict[str, Any]:
    records_list = list(records)
    clean_rows: list[dict[str, Any]] = []
    total_rows: list[Mapping[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for index, raw_record in enumerate(records_list, start=2):
        record = dict(raw_record)
        if is_total_row(record, date_col=date_col, carrier_col=carrier_col):
            total_rows.append(record)
            continue

        amount_text = text_value(record.get(amount_col))
        if not amount_text:
            continue

        try:
            amount = parse_amount(record.get(amount_col))
        except ValueError as exc:
            raise ValueError(f"Нечисловая сумма в строке {index}: {record.get(amount_col)!r}") from exc

        category = classify_record(record, carrier_col=carrier_col, details_col=details_col)
        record["_row_number"] = index
        record["_amount"] = amount
        record["_category"] = category
        clean_rows.append(record)

        carrier = lower_value(record.get(carrier_col))
        details = lower_value(record.get(details_col))
        if category == CATEGORY_UNKNOWN:
            warnings.append(
                _warning_row(
                    "unknown_category",
                    index,
                    category,
                    record,
                    carrier_col=carrier_col,
                    details_col=details_col,
                )
            )
        if not carrier and category == CATEGORY_AIR:
            warnings.append(
                _warning_row(
                    "missing_carrier_air_route",
                    index,
                    category,
                    record,
                    carrier_col=carrier_col,
                    details_col=details_col,
                )
            )
        if any(marker in carrier for marker in MIXED_SERVICE_MARKERS):
            warnings.append(
                _warning_row(
                    "mixed_service_vendor",
                    index,
                    category,
                    record,
                    carrier_col=carrier_col,
                    details_col=details_col,
                )
            )
        if (
            any(marker in carrier for marker in HOTEL_VENDOR_MARKERS)
            and category != CATEGORY_HOTEL
            and not any(marker in details for marker in ("прожив", "апартамент", "поздний выезд"))
        ):
            warnings.append(
                _warning_row(
                    "hotel_vendor_without_lodging_marker",
                    index,
                    category,
                    record,
                    carrier_col=carrier_col,
                    details_col=details_col,
                )
            )

    category_rows = {category: 0 for category in CATEGORY_ORDER}
    category_sums = {category: 0.0 for category in CATEGORY_ORDER}
    for row in clean_rows:
        category = row["_category"]
        category_rows[category] += 1
        category_sums[category] = round(category_sums[category] + row["_amount"], 2)

    summary = [
        _make_summary_row(category, category_rows[category], category_sums[category])
        for category in CATEGORY_ORDER
    ]
    total_count = len(clean_rows)
    total_sum = round(sum(row["_amount"] for row in clean_rows), 2)
    summary.append(_make_summary_row(CATEGORY_TOTAL, total_count, total_sum))

    source_total_present = bool(total_rows)
    source_total_count = None
    source_total_sum = None
    matches_source_total = None
    if total_rows:
        total_row = total_rows[0]
        source_total_count = _source_total_count(total_row, amount_col)
        source_total_sum = parse_amount(total_row.get(amount_col))
        count_matches = source_total_count is None or source_total_count == total_count
        sum_matches = abs(source_total_sum - total_sum) < 0.01
        matches_source_total = bool(count_matches and sum_matches)

    verification = {
        "clean_rows": total_count,
        "category_rows": sum(category_rows.values()),
        "category_sum": total_sum,
        "source_total_present": source_total_present,
        "source_total_count": source_total_count,
        "source_total_sum": source_total_sum,
        "matches_source_total": matches_source_total,
    }

    return {
        "summary": summary,
        "verification": verification,
        "warnings": warnings,
    }


def read_table(path: Path, *, sheet: str | int | None = None) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return read_csv(path)
    if suffix in {".xls", ".xlsx", ".xlsm"}:
        return read_excel(path, sheet=sheet)
    raise ValueError(f"Неподдерживаемый формат файла: {path.suffix}")


def read_csv(path: Path) -> list[dict[str, Any]]:
    sample = path.read_text(encoding="utf-8-sig", errors="replace")[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh, dialect=dialect)
        return [dict(row) for row in reader]


def read_excel(path: Path, *, sheet: str | int | None = None) -> list[dict[str, Any]]:
    try:
        import pandas as pd  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Для чтения Excel нужен pandas + xlrd/openpyxl. "
            "Создайте venv и установите: python3 -m pip install pandas xlrd openpyxl"
        ) from exc

    suffix = path.suffix.lower()
    engine = "xlrd" if suffix == ".xls" else "openpyxl"
    sheet_name: str | int = 0 if sheet is None else sheet
    dataframe = pd.read_excel(path, sheet_name=sheet_name, engine=engine)
    dataframe.columns = [str(column).strip() for column in dataframe.columns]
    return dataframe.to_dict("records")


def render_markdown(result: Mapping[str, Any]) -> str:
    lines = [
        "| Категория | Бронирований | Сумма |",
        "|---|---:|---:|",
    ]
    for row in result["summary"]:
        lines.append(f"| **{row['category']}** | {row['bookings']} | {row['amount_display']} |")

    verification = result["verification"]
    total_display = result["summary"][-1]["amount_display"]
    lines.append("")
    if verification["source_total_present"]:
        if verification["matches_source_total"]:
            lines.append(f"Сверка: сумма по категориям совпадает с итоговой строкой файла — {total_display}.")
        else:
            source_sum = verification.get("source_total_sum")
            source_display = format_money(float(source_sum)) if source_sum is not None else "не найдена"
            lines.append(
                "Сверка: есть расхождение с итоговой строкой файла — "
                f"расчёт {total_display}, исходный итог {source_display}."
            )
    else:
        lines.append(f"Сверка: итоговая строка в файле не найдена; сумма категорий — {total_display}.")
    return "\n".join(lines)


def render_warnings(warnings: Iterable[Mapping[str, Any]]) -> str:
    warnings = list(warnings)
    if not warnings:
        return ""
    lines = ["", "Предупреждения для проверки:"]
    for warning in warnings:
        lines.append(
            f"- строка {warning['row_number']}: {warning['type']} → "
            f"{warning['category']} ({warning.get('details_preview', '')})"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize travel expense spreadsheet categories.")
    parser.add_argument("path", type=Path, help="Path to .xls/.xlsx/.xlsm/.csv file")
    parser.add_argument("--sheet", help="Excel sheet name/index; default: first sheet")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--amount-col", default="Сумма")
    parser.add_argument("--carrier-col", default="Перевозчик")
    parser.add_argument("--details-col", default="Детали")
    parser.add_argument("--date-col", default="Дата")
    parser.add_argument("--show-warnings", action="store_true", help="Append ambiguous-row warnings to markdown output")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        sheet: str | int | None = args.sheet
        if isinstance(sheet, str) and sheet.isdigit():
            sheet = int(sheet)
        records = read_table(args.path, sheet=sheet)
        result = summarize_records(
            records,
            amount_col=args.amount_col,
            carrier_col=args.carrier_col,
            details_col=args.details_col,
            date_col=args.date_col,
        )
    except Exception as exc:  # noqa: BLE001 - CLI should present concise user-facing errors.
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        output = render_markdown(result)
        if args.show_warnings:
            output += render_warnings(result["warnings"])
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
