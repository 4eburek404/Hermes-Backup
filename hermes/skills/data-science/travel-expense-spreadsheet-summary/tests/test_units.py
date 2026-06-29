from __future__ import annotations

from travel_expense.classifier import classify_category
from travel_expense.constants import CATEGORY_AIR, CATEGORY_HOTEL, CATEGORY_RAIL, CATEGORY_UNKNOWN
from travel_expense.money import parse_amount
from travel_expense.schema import detect_schema


def test_parse_russian_money():
    assert parse_amount("1 234,56 ₽") == 1234.56
    assert parse_amount("1,234.56") == 1234.56
    assert parse_amount("#NAME?") is None


def test_detect_schema_date_purchase():
    rows = [
        ["Дата покупки", "Поставщик", "Описание", "Стоимость"],
        ["01.03.2025", "Аэрофлот", "Москва-Сочи", "10 000,00"],
    ]
    schema = detect_schema(rows)
    assert schema.column_names["date"] == "Дата покупки"
    assert schema.column_names["amount"] == "Стоимость"


def test_airline_carrier_beats_rail_in_details():
    category, reason, review = classify_category("Аэрофлот", "Конструкторское бюро РЖД, Москва")
    assert category == CATEGORY_AIR
    assert not review


def test_yuvtaero_compact_airline():
    category, reason, review = classify_category("ЮВТАЭРО", "01.03.2025 Казань-Самара")
    assert category == CATEGORY_AIR


def test_mixed_vendor_without_marker_unknown():
    category, reason, review = classify_category("ВАЙТ ТРЕВЕЛ", "23.03.2025 Шэньчжэнь-Сиань")
    assert category == CATEGORY_UNKNOWN
    assert review


def test_structural_yandex_hotel_review():
    category, reason, review = classify_category("Яндекс", "26.03-27.03.2025 Казань, Амакс Сафар")
    assert category == CATEGORY_HOTEL
    assert review


def test_ground_transport_legacy_rail_review():
    category, reason, review = classify_category("Аэроэкспресс", "Аэропорт-город")
    assert category == CATEGORY_RAIL
    assert review
