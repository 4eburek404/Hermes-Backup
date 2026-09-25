"""S4: party_total остаётся ценой всей запрошенной группы."""

import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

from tests.product_driver import search

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/avia/party-2a-1c.json"


def test_party_total_price_is_not_multiplied_again():
    recording = json.loads(FIXTURE.read_text(encoding="utf-8"))
    envelope = recording["response"]["envelope"]
    source = json.loads(envelope["result"]["content"][0]["text"])

    def recorded_tool(name, arguments):
        assert name == "search_avia"
        assert arguments == recording["arguments"]
        return deepcopy(envelope)

    result = search(deepcopy(recording["arguments"]), call_tool=recorded_tool)

    assert result["pricing_basis"] == "party_total"
    assert result["passengers"] == {"full": 2, "child": 1}
    assert len(result["offers"]) == len(source["offers"])

    for offer, raw_offer in zip(result["offers"], source["offers"], strict=True):
        raw_fares = {
            variant["conditions"]["fare_family"]: variant for variant in raw_offer["variants"]
        }
        fares = {fare["name"]: fare for fare in offer["fares"]}
        assert len(fares) == len(offer["fares"]) == len(raw_fares)
        assert set(fares) == set(raw_fares)

        for name, raw_variant in raw_fares.items():
            fare = fares[name]
            actual = Decimal(fare["amount"])
            source_amount = Decimal(str(raw_variant["price"]["amount"]))
            assert actual == source_amount
            assert actual != source_amount * 3
            assert fare["currency"] == raw_variant["price"].get("currency")
            for condition in ("baggage", "cabin_baggage", "refundable", "changeable", "exchange"):
                assert fare[condition] == raw_variant["conditions"].get(condition)
