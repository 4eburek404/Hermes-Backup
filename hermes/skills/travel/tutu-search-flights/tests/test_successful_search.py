"""S1: проверки свойств сохранённого ответа, specs/02-successful-search.md."""

import json
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from tests.product_driver import search

BASELINE = Path(__file__).resolve().parents[1] / "fixtures/avia/baseline.json"
REQUEST = {
    "origin": "Москва",
    "destination": "Сочи",
    "departure_date": "2026-10-15",
    "page_size": 3,
}


def test_successful_search_preserves_source_results_prices_and_conditions():
    recording = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert recording["arguments"] == REQUEST
    scenario_at = datetime.fromisoformat(recording["recorded_at"])
    assert scenario_at.utcoffset() is not None
    envelope = recording["response"]["envelope"]
    source = json.loads(envelope["result"]["content"][0]["text"])
    calls = []

    def recorded_tool(name, arguments):
        assert name == "search_avia"
        assert arguments == REQUEST
        calls.append((name, deepcopy(arguments)))
        return deepcopy(envelope)

    # The recorded call is replayed as-is; the machine's current date is irrelevant.
    result = search(deepcopy(REQUEST), call_tool=recorded_tool)

    assert calls == [("search_avia", REQUEST)]
    assert result["pricing_basis"] == source["meta"]["pricing"]["basis"] == "party_total"
    assert result["passengers"] == source["meta"]["pricing"]["passengers"] == {"full": 1}
    assert result["has_more"] is source["meta"]["has_more"] is True

    source_offers = source["offers"]
    offers = result["offers"]
    assert len(offers) == len(source_offers) == 3
    by_flight = {offer["flight_number"]: offer for offer in offers}
    source_flights = {offer["legs"][0]["segments"][0]["voyage_no"] for offer in source_offers}
    assert set(by_flight) == source_flights

    # These are independent control examples from this historical recording, not
    # product requirements to return this flight or carrier in other searches.
    control = by_flight["DP-6949"]
    assert control["carrier"] == "Победа"
    assert control["origin"] == "Москва — Шереметьево (SVO), терм. D"
    assert control["destination"] == "Сочи, AER"
    assert control["departure_at"] == "2026-10-15T19:25:00+03:00"
    assert control["arrival_at"] == "2026-10-15T23:05:00+03:00"
    assert control["duration_min"] == 220
    assert control["segments_count"] == 1

    for raw_offer in source_offers:
        raw_segment = raw_offer["legs"][0]["segments"][0]
        offer = by_flight[raw_segment["voyage_no"]]
        assert offer["carrier"] == raw_segment["carrier"]
        assert offer["origin"] == raw_segment["from"]
        assert offer["destination"] == raw_segment["to"]
        assert offer["departure_at"] == raw_offer["departure_at"]
        assert offer["arrival_at"] == raw_offer["arrival_at"]
        assert datetime.fromisoformat(offer["departure_at"]).utcoffset() is not None
        assert datetime.fromisoformat(offer["arrival_at"]).utcoffset() is not None
        assert offer["duration_min"] == raw_offer["duration_min"]
        assert offer["segments_count"] == raw_offer["segments_count"]

        raw_variants = raw_offer["variants"]
        actual_fares = offer["fares"]
        assert len(actual_fares) == len(raw_variants)
        by_fare = {fare["name"]: fare for fare in actual_fares}
        assert set(by_fare) == {v["conditions"]["fare_family"] for v in raw_variants}
        for raw_variant in raw_variants:
            conditions = raw_variant["conditions"]
            fare = by_fare[conditions["fare_family"]]
            # The source amount stays attached to its source fare; no passenger
            # multiplier is applied to a party_total price.
            assert Decimal(fare["amount"]) == Decimal(str(raw_variant["price"]["amount"]))
            assert fare["currency"] == raw_variant["price"]["currency"]
            assert fare["baggage"] == conditions.get("baggage")
            assert fare["cabin_baggage"] == conditions.get("cabin_baggage")
            assert fare["refundable"] == conditions.get("refundable")
            assert fare["changeable"] == conditions.get("changeable")
            assert fare["exchange"] == conditions.get("exchange")

    # A missing cabin-baggage weight remains explicitly unknown in this example.
    base_fare = next(f for f in control["fares"] if f["name"] == "Базовый")
    assert base_fare["cabin_baggage"] == {
        "kg": None,
        "pieces": 1,
        "dimensions": "36 × 30 × 27",
    }
    changeable_fare = next(f for f in control["fares"] if f["name"] == "Выгодный")
    assert changeable_fare["exchange"] == {"available": True, "deadline_hours": 48}
