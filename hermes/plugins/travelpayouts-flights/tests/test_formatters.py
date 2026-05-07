"""Tests for formatters and enrichment formatted fields."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

import importlib.util

spec = importlib.util.spec_from_file_location(
    "travelpayouts_flights_testpkg",
    PLUGIN_ROOT / "__init__.py",
    submodule_search_locations=[str(PLUGIN_ROOT)],
)
pkg = importlib.util.module_from_spec(spec)
sys.modules["travelpayouts_flights_testpkg"] = pkg
assert spec.loader is not None
spec.loader.exec_module(pkg)

formatters = importlib.import_module("travelpayouts_flights_testpkg.formatters")


def test_format_time():
    assert formatters.format_time("2026-05-01T06:30:00+05:00") == "06:30"
    assert formatters.format_time("2026-05-01T23:05:00+03:00") == "23:05"
    assert formatters.format_time("") == "—"
    assert formatters.format_time("garbage") == "—"


def test_format_date():
    assert formatters.format_date("2026-05-01T10:00:00+05:00") == "1 май"
    assert formatters.format_date("2026-01-15T00:00:00Z") == "15 янв"
    assert formatters.format_date("") == "—"


def test_format_duration():
    assert formatters.format_duration(155) == "2ч 35м"
    assert formatters.format_duration(60) == "1ч"
    assert formatters.format_duration(45) == "45м"
    assert formatters.format_duration(0) == "—"
    assert formatters.format_duration(120) == "2ч"


def test_format_transfer():
    result = formatters.format_transfer("Москва (SVO)", 120)
    assert "Москва (SVO)" in result
    assert "2ч" in result
    assert "🔄" in result


def test_format_transfer_night_visa():
    result = formatters.format_transfer("Дубай (DXB)", 180, night_transfer=True, visa_required=True)
    assert "🌙" in result
    assert "⚠️" in result
    assert "3ч" in result


def test_format_price():
    assert formatters.format_price(12500, "RUB") == "12\u00A0500 ₽"
    assert formatters.format_price(500, "USD") == "500 $"
    assert formatters.format_price(1000, "EUR") == "1\u00A0000 €"


def test_format_transfers_count():
    assert formatters.format_transfers_count(0) == "Прямой"
    assert formatters.format_transfers_count(1) == "1 пересадка"
    assert formatters.format_transfers_count(2) == "2 пересадки"
    assert formatters.format_transfers_count(5) == "5 пересадок"


def test_format_flight_results_basic():
    flights = [{
        "price": 12500,
        "currency": "RUB",
        "airline": "U6",
        "airline_name": "Уральские авиалинии",
        "transfers": 0,
        "departure_at": "2026-05-01T06:30:00+05:00",
        "arrival_at": "2026-05-01T08:05:00+03:00",
        "duration_min": 155,
        "outbound": {
            "departure_at": "2026-05-01T06:30:00+05:00",
            "arrival_at": "2026-05-01T08:05:00+03:00",
            "duration_min": 155,
            "duration_formatted": "2ч 35м",
            "transfers_count": 0,
            "legs": [{
                "origin": "SVX",
                "destination": "DME",
                "origin_name": "Екатеринбург (SVX)",
                "destination_name": "Москва (DME)",
                "flight_number": "U6261",
                "carrier": "U6",
                "carrier_name": "Уральские авиалинии",
                "departure_at": "2026-05-01T06:30:00+05:00",
                "arrival_at": "2026-05-01T08:05:00+03:00",
                "departure_formatted": "06:30",
                "arrival_formatted": "08:05",
                "aircraft_code": "738",
                "aircraft_name": "Boeing 737-800",
                "duration_min": 155,
            }],
            "transfers": [],
            "departure_formatted": "06:30, 1 май",
            "arrival_formatted": "08:05, 1 май",
        },
        "booking_url": "https://www.aviasales.ru/search/SVX0105DME1?marker=test",
        "transfers_formatted": "Прямой",
        "duration_formatted": "2ч 35м",
        "price_formatted": "12\u00A0500 ₽",
    }]
    
    html = formatters.format_flight_results(
        flights,
        origin="SVX",
        origin_name="Екатеринбург (SVX)",
        destination="DME",
        destination_name="Москва (DME)",
        departure_date="2026-05-01",
        currency="RUB",
    )
    
    assert "Екатеринбург" in html
    assert "Москва" in html
    assert "12\u00A0500" in html or "12500" in html
    assert "Прямой" in html
    assert "Уральские" in html
    assert "2ч 35м" in html
    assert "<b>" in html


def test_format_flight_results_empty():
    html = formatters.format_flight_results(
        [],
        origin="SVX",
        origin_name="Екатеринбург (SVX)",
        destination="LED",
        destination_name="Санкт-Петербург (LED)",
        departure_date="2026-05-01",
    )
    assert "не найдены" in html


def test_format_flight_results_direct_not_available():
    flights = [{
        "price": 8000,
        "currency": "RUB",
        "airline": None,
        "airline_name": None,
        "transfers": 1,
        "departure_at": "2026-05-01T10:00:00+05:00",
        "duration_min": 240,
        "outbound": None,
        "booking_url": None,
        "transfers_formatted": "1 пересадка",
        "duration_formatted": "4ч",
        "price_formatted": "8\u00A0000 ₽",
    }]
    html = formatters.format_flight_results(
        flights,
        origin="SVX",
        origin_name="Екатеринбург (SVX)",
        destination="AER",
        destination_name="Сочи (AER)",
        departure_date="2026-06-15",
        direct_not_available=True,
    )
    assert "Прямых рейсов нет" in html


def main():
    tests = [
        test_format_time,
        test_format_date,
        test_format_duration,
        test_format_transfer,
        test_format_transfer_night_visa,
        test_format_price,
        test_format_transfers_count,
        test_format_flight_results_basic,
        test_format_flight_results_empty,
        test_format_flight_results_direct_not_available,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"\nPASS {len(tests)} formatter tests")


if __name__ == "__main__":
    main()