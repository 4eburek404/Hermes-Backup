"""S7: пустая выдача не теряет объяснение источника или фильтра."""

import json
from copy import deepcopy
from pathlib import Path

from tests.product_driver import search

ROOT = Path(__file__).resolve().parents[1] / "fixtures/avia"


def _run_recording(name):
    recording = json.loads((ROOT / name).read_text(encoding="utf-8"))
    envelope = recording["response"]["envelope"]

    def recorded_tool(tool_name, arguments):
        assert tool_name == "search_avia"
        assert arguments == recording["arguments"]
        return deepcopy(envelope)

    return recording, search(deepcopy(recording["arguments"]), call_tool=recorded_tool)


def test_upstream_note_survives_empty_result():
    recording, result = _run_recording("past-date.json")
    source = recording["response"]["payload"]

    assert result["offers"] == []
    assert result["total_matched_exact"] is source["meta"]["total_matched_exact"] is True
    assert result["upstream_note"] == source["meta"]["upstream_note"]
    assert result["post_filter_dropped"] == {}


def test_filter_drops_survive_empty_result():
    recording, result = _run_recording("unknown-carrier.json")
    source = recording["response"]["payload"]

    assert result["offers"] == []
    assert result["total_matched_exact"] is source["meta"]["total_matched_exact"] is True
    assert result["upstream_note"] is None
    assert result["post_filter_dropped"] == {
        "wrong_carrier": source["meta"]["post_filter_dropped_wrong_carrier"]
    }
