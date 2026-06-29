import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import travel_expense_summary as tes


def test_classify_record_handles_travel_edge_cases():
    cases = [
        (
            {"Перевозчик": "TRIP.COM TRAVEL SINGAPORE PTE.LTD.", "Детали": "ЖД, приказ 246а/к, 26.05.2026 Шанхай-Чжанцзяган"},
            "ЖД",
        ),
        (
            {"Перевозчик": "TRIP.COM TRAVEL SINGAPORE PTE.LTD.", "Детали": "Проживание с 26.05-28.05.2026, Atour Hotel"},
            "Проживание в отелях",
        ),
        (
            {"Перевозчик": "ООО Аэроэкспресс Москва", "Детали": "аэроэскпресс туда-обратно"},
            "ЖД",
        ),
        (
            {"Перевозчик": "ПАО Аэрофлот", "Детали": "05.06.2026 ЕКБ-Москва/21.06.2026 Москва-ЕКБ, Физтех отель, МФТИ"},
            "Авиа",
        ),
        (
            {"Перевозчик": "ООО \"ЯНДЕКС ВЕРТИКАЛИ\" Москва", "Детали": "Приказ, 16.03-17.03.2026, Екатеринбург, апартаменты"},
            "Проживание в отелях",
        ),
        # Unknown: no airline/rail/hotel marker → not auto-classified as Авиа
        (
            {"Перевозчик": "", "Детали": "13.06.2026 ЕКБ-Ереван/ 14.06.2026 Ереван-Рим/27.06.2026 Рим-Ереван-ЕКБ"},
            "Unknown",
        ),
        # ВАЙТ ТРЕВЕЛ — mixed-service vendor, classified per row details
        (
            {"Перевозчик": "ООО \"ВАЙТ ТРЕВЕЛ\" МОСКВА", "Детали": "Приказ 5434, 04.05.2026 Санкт-Петербург- Великие Луки"},
            "Unknown",
        ),
        # Поздний выезд → Проживание в отелях
        (
            {"Перевозчик": "ООО \"Центр бронирования ЮСТА\" Екатеринбург", "Детали": "Поздний выезд 26.04.2026, Екатеринбург, Московская горка"},
            "Проживание в отелях",
        ),
        # Аэрофлот + "РЖД" в деталях как название организации → Авиа, не ЖД
        (
            {"Перевозчик": "ПАО \"Аэрофлот- Российские авиалинии\" Москва", "Детали": "12.01.2025 ЕКБ-Москва/13.01.2025 Москва-ЕКБ (Конструкторское бюро РЖД)"},
            "Авиа",
        ),
    ]

    for record, expected in cases:
        assert tes.classify_record(record) == expected


def test_summarize_records_excludes_total_and_verifies_source_total():
    records = [
        {"Дата": "01.05.2026", "Сотрудник": "A", "Перевозчик": "Аэрофлот", "Детали": "ЕКБ-Москва", "Сумма": "10000"},
        {"Дата": "02.05.2026", "Сотрудник": "B", "Перевозчик": "TRIP.COM", "Детали": "ЖД Москва-Пермь", "Сумма": "1500,50"},
        {"Дата": "03.05.2026", "Сотрудник": "C", "Перевозчик": "TRIP.COM", "Детали": "проживание с 03.05-04.05, Hotel", "Сумма": "3000"},
        {"Дата": "04.05.2026", "Сотрудник": "D", "Перевозчик": "ООО Аэроэкспресс", "Детали": "аэроэкспресс", "Сумма": "650"},
        {"Дата": "05.05.2026", "Сотрудник": "E", "Перевозчик": "", "Детали": "ЕКБ-Ереван/Ереван-Рим", "Сумма": "20000"},
        {"Дата": "06.05.2026", "Сотрудник": "F", "Перевозчик": "Яндекс", "Детали": "Проживание с 06.05-07.05, Москва", "Сумма": "4000"},
        {"Дата": "Итог", "Сотрудник": "6", "Перевозчик": "", "Детали": "", "Сумма": "39150,50"},
    ]

    result = tes.summarize_records(records)

    by_category = {row["category"]: row for row in result["summary"]}
    assert by_category["Авиа"] == {"category": "Авиа", "bookings": 1, "amount": 10000.0, "amount_display": "10 000,00 ₽"}
    assert by_category["ЖД"] == {"category": "ЖД", "bookings": 2, "amount": 2150.5, "amount_display": "2 150,50 ₽"}
    assert by_category["Проживание в отелях"] == {
        "category": "Проживание в отелях",
        "bookings": 2,
        "amount": 7000.0,
        "amount_display": "7 000,00 ₽",
    }
    assert by_category["Unknown"] == {"category": "Unknown", "bookings": 1, "amount": 20000.0, "amount_display": "20 000,00 ₽"}
    assert by_category["ИТОГО"] == {"category": "ИТОГО", "bookings": 6, "amount": 39150.5, "amount_display": "39 150,50 ₽"}

    assert result["verification"] == {
        "clean_rows": 6,
        "category_rows": 6,
        "category_sum": 39150.5,
        "source_total_present": True,
        "source_total_count": 6,
        "source_total_sum": 39150.5,
        "matches_source_total": True,
    }
    warning_types = {warning["type"] for warning in result["warnings"]}
    assert {"mixed_service_vendor", "unknown_category"} <= warning_types


def test_csv_cli_outputs_json_and_markdown(tmp_path):
    path = tmp_path / "travel.csv"
    rows = [
        {"Дата": "01.05.2026", "Сотрудник": "A", "Перевозчик": "Аэрофлот", "Детали": "ЕКБ-Москва", "Сумма": "10000"},
        {"Дата": "02.05.2026", "Сотрудник": "B", "Перевозчик": "РЖД", "Детали": "Пермь-Москва", "Сумма": "2000"},
        {"Дата": "03.05.2026", "Сотрудник": "C", "Перевозчик": "Яндекс", "Детали": "Проживание с 03.05-04.05", "Сумма": "3000"},
        {"Дата": "Итог", "Сотрудник": "3", "Перевозчик": "", "Детали": "", "Сумма": "15000"},
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["Дата", "Сотрудник", "Перевозчик", "Детали", "Сумма"])
        writer.writeheader()
        writer.writerows(rows)

    json_run = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "travel_expense_summary.py"), str(path), "--format", "json"],
        check=True,
        text=True,
        capture_output=True,
    )
    data = json.loads(json_run.stdout)
    assert data["verification"]["matches_source_total"] is True
    assert data["summary"][-1] == {"category": "ИТОГО", "bookings": 3, "amount": 15000.0, "amount_display": "15 000,00 ₽"}

    markdown_run = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "travel_expense_summary.py"), str(path), "--format", "markdown"],
        check=True,
        text=True,
        capture_output=True,
    )
    assert "| **Авиа** | 1 | 10 000,00 ₽ |" in markdown_run.stdout
    assert "Сверка: сумма по категориям совпадает с итоговой строкой файла — 15 000,00 ₽." in markdown_run.stdout


def test_non_numeric_amount_raises_clear_error():
    records = [{"Дата": "01.05.2026", "Перевозчик": "Аэрофлот", "Детали": "ЕКБ-Москва", "Сумма": "не число"}]

    with pytest.raises(ValueError, match="Нечисловая сумма"):
        tes.summarize_records(records)
