from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT.parent))

# Import via package name with underscore fallback is awkward for hyphen dirs, so load
# through importlib package spec in ad-hoc tests would be overkill. Instead, make the
# plugin root importable and use importlib to load files as package is handled by
# Hermes itself. These tests focus pure helper behaviour through direct file import.
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

tools = importlib.import_module("travelpayouts_flights_testpkg.tools")
client = importlib.import_module("travelpayouts_flights_testpkg.client")
parsers = importlib.import_module("travelpayouts_flights_testpkg.parsers")


def test_validation_rejects_bad_iata():
    data = json.loads(asyncio.run(tools.travelpayouts_flight_search({"origin": "SVXX", "destination": "MOW", "departure_date": "2026-05-01"})))
    assert data["success"] is False
    assert data["error_type"] == "validation_error"


def test_missing_credentials_returns_json(monkeypatch=None):
    old = os.environ.pop("TRAVELPAYOUTS_TOKEN", None)
    try:
        data = json.loads(asyncio.run(tools.travelpayouts_flight_search({"origin": "SVX", "destination": "MOW", "departure_date": "2026-05-01"})))
        assert data["success"] is False
        assert data["error_type"] == "missing_credentials"
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
