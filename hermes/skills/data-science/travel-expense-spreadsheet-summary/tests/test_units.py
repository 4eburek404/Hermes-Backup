from __future__ import annotations

import json
from pathlib import Path

import pytest

from travel_expense.classifier import classify_category
from travel_expense.constants import CATEGORY_AIR, CATEGORY_HOTEL, CATEGORY_RAIL, CATEGORY_UNKNOWN
from travel_expense.money import parse_amount
from travel_expense.overrides import load_overrides, match_override
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


def test_ground_transport_legacy_rail_no_review_noise():
    category, reason, review = classify_category("Аэроэкспресс", "Аэропорт-город")
    assert category == CATEGORY_RAIL
    assert not review


def test_transfer_to_hotel_is_not_lodging():
    category, reason, review = classify_category("Трансфер", "Трансфер аэропорт-отель")
    assert category == CATEGORY_RAIL


def test_airline_row_with_hotel_note_stays_air():
    category, reason, review = classify_category("Аэрофлот", "Командировка, размещение: отель Амакс Сафар")
    assert category == CATEGORY_AIR
    assert not review


def test_pattern_override_matches_future_similar_rows(tmp_path: Path):
    overrides_path = tmp_path / "overrides.json"
    overrides_path.write_text(json.dumps({
        "version": 2,
        "pattern_overrides": [
            {
                "name": "white-travel-shenzhen-xian-air",
                "carrier_contains": "ВАЙТ ТРЕВЕЛ",
                "details_regex": "Шэньчжэнь\\s*[-–—]\\s*Сиань",
                "category": "Авиа",
                "reason": "подтвержденный авиамаршрут",
            }
        ],
    }, ensure_ascii=False), encoding="utf-8")
    patterns = load_overrides(overrides_path)
    assert match_override("ООО ВАЙТ ТРЕВЕЛ", "05.04.2025 Шэньчжэнь — Сиань", patterns).category == CATEGORY_AIR


def test_old_point_override_format_is_rejected(tmp_path: Path):
    overrides_path = tmp_path / "overrides.json"
    overrides_path.write_text('{"2df630be4b7f71ff": "Авиа"}', encoding="utf-8")
    with pytest.raises(ValueError, match="Точечные overrides"):
        load_overrides(overrides_path)


def test_too_broad_pattern_override_is_rejected(tmp_path: Path):
    overrides_path = tmp_path / "overrides.json"
    overrides_path.write_text(json.dumps({
        "version": 2,
        "pattern_overrides": [
            {"carrier_contains": "ВАЙТ ТРЕВЕЛ", "category": "Авиа"}
        ],
    }, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="слишком широкое"):
        load_overrides(overrides_path)
