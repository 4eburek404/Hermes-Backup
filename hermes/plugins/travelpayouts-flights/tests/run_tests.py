from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import os
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
MODULE_NAME = "hermes_plugins.travelpayouts_flights_test"

# Mirror Hermes PluginManager loading: create a namespace package module from
# __init__.py with submodule_search_locations so relative imports work even
# though the filesystem directory contains a hyphen.
spec = importlib.util.spec_from_file_location(
    MODULE_NAME,
    PLUGIN_ROOT / "__init__.py",
    submodule_search_locations=[str(PLUGIN_ROOT)],
)
pkg = importlib.util.module_from_spec(spec)
sys.modules[MODULE_NAME] = pkg
assert spec and spec.loader
spec.loader.exec_module(pkg)

tools = importlib.import_module(f"{MODULE_NAME}.tools")
client = importlib.import_module(f"{MODULE_NAME}.client")
parsers = importlib.import_module(f"{MODULE_NAME}.parsers")


def test_validation_rejects_bad_iata():
    data = json.loads(asyncio.run(tools.travelpayouts_flight_search({"origin": "SVXX", "destination": "MOW", "departure_date": "2026-05-01"})))
    assert data["success"] is False
    assert data["error_type"] == "validation_error"


def test_missing_credentials_returns_json():
    old = os.environ.pop("TRAVELPAYOUTS_TOKEN", None)
    try:
        data = json.loads(asyncio.run(tools.travelpayouts_flight_search({"origin": "SVX", "destination": "MOW", "departure_date": "2026-05-01"})))
        assert data["success"] is False
        assert data["error_type"] == "missing_credentials"
        assert "TOKEN" in data["error"]
    finally:
        if old is not None:
            os.environ["TRAVELPAYOUTS_TOKEN"] = old


def test_build_booking_url_adds_marker_once():
    url = client.build_booking_url("/search/SVX0105MOW1", marker="abc")
    assert url.startswith("https://www.aviasales.ru/search/")
    assert "marker=abc" in url
    url2 = client.build_booking_url(url, marker="abc")
    assert url2.count("marker=abc") == 1


def test_parse_and_dedup_key():
    flight = parsers.parse_graphql_flight({
        "departure_at": "2026-05-01T10:00:00+05:00",
        "value": 12345,
        "number_of_changes": 0,
        "main_airline": "SU",
        "segments": [{
            "departure_at": "2026-05-01T10:00:00+05:00",
            "arrival_at": "2026-05-01T11:00:00+03:00",
            "flight_legs": [{
                "origin": "SVX", "destination": "SVO", "flight_number": "SU1401",
                "operating_carrier": "SU", "aircraft_code": "738",
                "departure_at": "2026-05-01T10:00:00+05:00",
                "arrival_at": "2026-05-01T11:00:00+03:00",
            }],
            "transfers": [],
        }],
    }, "SVX", "MOW")
    assert flight.price == 12345
    assert parsers.flight_dedup_key(flight) == "SU1401_10:00_11:00"


def main():
    tests = [
        test_validation_rejects_bad_iata,
        test_missing_credentials_returns_json,
        test_build_booking_url_adds_marker_once,
        test_parse_and_dedup_key,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"PASS {len(tests)} tests")


if __name__ == "__main__":
    main()
