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

    raw_offer = source["offers"][0]
    raw_fares = {variant["conditions"]["fare_family"]: variant for variant in raw_offer["variants"]}
    offer = result["offers"][0]
    fares = {fare["name"]: fare for fare in offer["fares"]}
    assert set(fares) == set(raw_fares)

    for name, raw_variant in raw_fares.items():
        actual = Decimal(fares[name]["amount"])
        source_amount = Decimal(str(raw_variant["price"]["amount"]))
        assert actual == source_amount
        assert actual != source_amount * 3
