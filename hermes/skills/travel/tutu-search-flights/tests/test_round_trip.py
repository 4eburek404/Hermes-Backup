"""S6: round-trip сохраняет outbound и return как отдельные legs."""

import json
from copy import deepcopy
from pathlib import Path

from tests.product_driver import search

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/avia/round-trip.json"


def test_round_trip_preserves_both_legs_and_outbound_route():
    recording = json.loads(FIXTURE.read_text(encoding="utf-8"))
    envelope = recording["response"]["envelope"]
    source = json.loads(envelope["result"]["content"][0]["text"])

    def recorded_tool(name, arguments):
        assert name == "search_avia"
        assert arguments == recording["arguments"]
        return deepcopy(envelope)

    result = search(deepcopy(recording["arguments"]), call_tool=recorded_tool)

    raw_offer = source["offers"][0]
    offer = result["offers"][0]
    assert offer["is_round_trip"] is raw_offer["is_round_trip"] is True
    assert offer["origin"] == raw_offer["legs"][0]["from"]
    assert offer["destination"] == raw_offer["legs"][0]["to"]
    assert offer["return_departure_at"] == raw_offer["return_departure_at"]
    assert offer["return_arrival_at"] == raw_offer["return_arrival_at"]
    assert [leg["label"] for leg in offer["legs"]] == ["outbound", "return"]

    for actual_leg, raw_leg in zip(offer["legs"], raw_offer["legs"], strict=True):
        assert actual_leg["from"] == raw_leg["from"]
        assert actual_leg["to"] == raw_leg["to"]
        assert actual_leg["departure_at"] == raw_leg["departure_at"]
        assert actual_leg["arrival_at"] == raw_leg["arrival_at"]
        assert len(actual_leg["segments"]) == len(raw_leg["segments"])
