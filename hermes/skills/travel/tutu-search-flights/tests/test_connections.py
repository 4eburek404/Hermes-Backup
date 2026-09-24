"""S5: пересадочный маршрут сохраняет legs и все сегменты."""

import json
from copy import deepcopy
from pathlib import Path

from tests.product_driver import search

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/avia/connections.json"


def test_connection_offer_preserves_segments_and_transfer_evidence():
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
    assert offer["origin"] == raw_offer["legs"][0]["from"]
    assert offer["destination"] == raw_offer["legs"][0]["to"]
    assert offer["has_self_transfer"] is raw_offer["has_self_transfer"] is True
    assert offer["is_multi_pnr"] is raw_offer["is_multi_pnr"] is True
    assert offer["multi_pnr_note"] == raw_offer["multi_pnr_note"]
    assert len(offer["legs"]) == len(raw_offer["legs"])

    for actual_leg, raw_leg in zip(offer["legs"], raw_offer["legs"], strict=True):
        assert actual_leg["label"] == raw_leg["label"]
        assert actual_leg["from"] == raw_leg["from"]
        assert actual_leg["to"] == raw_leg["to"]
        assert actual_leg["departure_at"] == raw_leg["departure_at"]
        assert actual_leg["arrival_at"] == raw_leg["arrival_at"]
        assert actual_leg["duration_min"] == raw_leg["duration_min"]
        assert len(actual_leg["segments"]) == len(raw_leg["segments"])

        for actual, raw in zip(actual_leg["segments"], raw_leg["segments"], strict=True):
            assert actual == {
                "flight_number": raw["voyage_no"],
                "carrier": raw["carrier"],
                "origin": raw["from"],
                "destination": raw["to"],
                "departure_at": raw["departure_at"],
                "arrival_at": raw["arrival_at"],
                "duration_min": raw["duration_min"],
            }
