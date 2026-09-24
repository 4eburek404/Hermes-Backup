"""S1: сохранение фактов успешного поиска, specs/02-successful-search.md.

Ожидания прочитаны из raw baseline от 24.09.2026 и заданы независимо от
результата продукта. Словари ниже — язык наблюдений теста, не схема CLI.
"""

import json
from copy import deepcopy
from pathlib import Path

from tests.product_driver import search

BASELINE = Path(__file__).resolve().parents[1] / "fixtures/avia/baseline.json"
REQUEST = {
    "origin": "Москва",
    "destination": "Сочи",
    "departure_date": "2026-10-15",
    "page_size": 3,
}


def fare(name, amount, baggage, cabin, refundable, changeable, exchange=None):
    """Краткая запись ожидаемых фактов; не разбирает данные источника."""
    return {
        "name": name,
        "amount": amount,
        "currency": "RUB",
        "baggage": baggage,
        "cabin_baggage": cabin,
        "refundable": refundable,
        "changeable": changeable,
        "exchange": exchange,
    }


def test_successful_search_preserves_schedule_prices_and_fares():
    # Дано: сырой JSON-RPC ответ, а не готовый response.payload или itinerary.
    recording = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert recording["arguments"] == REQUEST
    envelope = recording["response"]["envelope"]
    calls = []

    def recorded_tool(name, arguments):
        # Любой незаписанный вызов — ошибка, живой сети здесь нет.
        assert name == "search_avia"
        assert arguments == REQUEST
        calls.append((name, deepcopy(arguments)))
        return deepcopy(envelope)

    # Когда: продукт выполняет обычный поиск с подменённой внешней зависимостью.
    result = search(deepcopy(REQUEST), call_tool=recorded_tool)

    # Тогда: он действительно запросил источник и вернул факты этой страницы.
    assert calls, "Результат должен быть получен через источник поиска"
    assert result["pricing_basis"] == "party_total"
    assert result["passengers"] == {"full": 1}
    assert result["has_more"] is True
    offers = result["offers"]
    assert len(offers) == 3
    by_flight = {offer["flight_number"]: offer for offer in offers}
    assert set(by_flight) == {"DP-6949", "S7-2055", "S7-2049"}

    schedules = {
        "DP-6949": ("Победа", "Москва — Шереметьево (SVO), терм. D", "19:25", "23:05", 220),
        "S7-2055": ("S7 Airlines", "Москва — Домодедово (DME)", "11:05", "14:50", 225),
        "S7-2049": ("S7 Airlines", "Москва — Домодедово (DME)", "08:55", "12:40", 225),
    }
    for flight, (carrier, origin, departure, arrival, duration) in schedules.items():
        offer = by_flight[flight]
        assert offer["carrier"] == carrier
        assert offer["origin"] == origin
        assert offer["destination"] == "Сочи, AER"
        assert offer["departure_at"] == f"2026-10-15T{departure}:00+03:00"
        assert offer["arrival_at"] == f"2026-10-15T{arrival}:00+03:00"
        assert offer["duration_min"] == duration
        assert offer["segments_count"] == 1

    # None — источник не сообщил вес; это не ноль и не догадка о норме.
    pobeda_cabin = {"kg": None, "pieces": 1, "dimensions": "36 × 30 × 27"}
    s7_cabin = {"kg": 10, "pieces": 1, "dimensions": "55 × 40 × 23"}
    s7_business_cabin = {"kg": 15, "pieces": 1, "dimensions": "55 × 40 × 23"}
    exchange = {"available": True, "deadline_hours": 48}
    expected_fares = {
        "DP-6949": [
            fare("Базовый", "4446.87", {"kg": 0, "pieces": 0}, pobeda_cabin, False, False),
            fare(
                "Выгодный", "7253.91", {"kg": 10, "pieces": 1}, pobeda_cabin, False, True, exchange
            ),
            fare(
                "Максимум", "10590.19", {"kg": 20, "pieces": 1}, pobeda_cabin, True, True, exchange
            ),
        ],
        "S7-2055": [
            fare("Эконом Базовый", "5365.96", {"kg": 0, "pieces": 0}, s7_cabin, False, True),
            fare("Эконом Стандарт", "8107.60", {"kg": 23, "pieces": 1}, s7_cabin, True, True),
            fare("Эконом Плюс", "16331.92", {"kg": 32, "pieces": 1}, s7_cabin, True, True),
            fare(
                "Бизнес Базовый",
                "45604.97",
                {"kg": 32, "pieces": 1},
                s7_business_cabin,
                False,
                True,
            ),
            fare("Бизнес Плюс", "79288.91", {"kg": 32, "pieces": 2}, s7_business_cabin, True, True),
        ],
    }
    expected_fares["S7-2049"] = deepcopy(expected_fares["S7-2055"])
    for flight, expected in expected_fares.items():
        actual = by_flight[flight]["fares"]
        assert len(actual) == len(expected), f"Потеряны или добавлены тарифы {flight}"
        # Порядок показа не задаётся; связка цена/тариф/условия обязательна.
        assert sorted(actual, key=lambda f: f["name"]) == sorted(expected, key=lambda f: f["name"])
