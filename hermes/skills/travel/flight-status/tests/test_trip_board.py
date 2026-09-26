from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "trip_board.py"
LOCAL_TIMEZONE = timezone(timedelta(hours=2))
LOCAL_NOW = datetime(2026, 7, 14, 20, 0, tzinfo=LOCAL_TIMEZONE)


def load_module():
    spec = importlib.util.spec_from_file_location("trip_board", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def status_payload() -> dict:
    cutoff_minus_adjustment = datetime(2026, 7, 14, 13, 0, tzinfo=timezone.utc)

    def timestamp_ms(value: datetime) -> int:
        return int(value.timestamp() * 1000)

    payload = {
        "moduleName": "statusList",
        "currentDate": "2026-07-15",
        "currentTimestamp": timestamp_ms(LOCAL_NOW),
        "data": {
            "airportCode": "SVO",
            "airportName": "Sheremetyevo",
            "dateOptions": [
                "Yesterday (Jul 14)",
                "Today (Jul 15)",
                "Tomorrow (Jul 16)",
            ],
            "i18n": {
                "Scheduled": "Scheduled",
                "Delayed": "Delayed",
                "Possible_Delay": "May be delayed",
                "Take_Off": "En route",
                "Cancelled": "Cancelled",
                "Arrived": "Arrived",
                "delaytime": "Delayed until ${{time}}",
                "arrivetime": "Landed at ${{time}}",
            },
            "originData": {
                "flightStatusByAirport": [
                    {
                        "flightNo": "OLD100",
                        "airlineName": "Old Air",
                        "departTerminal": "B",
                        "flightState": 1,
                        "arrivalCityName": "Old City",
                        "plannedDepartTime": "17:55",
                        "plannedDepartTimeStamp": timestamp_ms(
                            cutoff_minus_adjustment - timedelta(minutes=1)
                        ),
                    },
                    {
                        "flightNo": "SU6311",
                        "airlineName": "Aeroflot",
                        "departTerminal": "B",
                        "flightState": 2,
                        "arrivalCityName": "Kaliningrad",
                        "plannedDepartTime": "00:05",
                        "plannedDepartTimeStamp": timestamp_ms(
                            cutoff_minus_adjustment + timedelta(hours=3, minutes=5)
                        ),
                        "finalDepartTime": "18:27",
                    },
                    {
                        "flightNo": "SU1606",
                        "airlineName": "Aeroflot",
                        "departTerminal": "B",
                        "flightState": 4,
                        "arrivalCityName": "Samara",
                        "plannedDepartTime": "00:10",
                        "plannedDepartTimeStamp": timestamp_ms(
                            cutoff_minus_adjustment + timedelta(hours=3, minutes=10)
                        ),
                    },
                ]
            },
            "arrivalsData": {
                "flightStatusByAirport": [
                    {
                        "flightNo": "SU1867",
                        "airlineName": "Aeroflot",
                        "arrivalTerminal": "C",
                        "flightState": 6,
                        "departCityName": "Yerevan",
                        "plannedArrivalTime": "01:10",
                        "plannedArrivalTimeStamp": timestamp_ms(
                            cutoff_minus_adjustment + timedelta(hours=4, minutes=10)
                        ),
                        "finalArrivalTime": "18:09",
                    },
                    {
                        "flightNo": "DP6874",
                        "airlineName": "Pobeda",
                        "arrivalTerminal": "D",
                        "flightState": 2,
                        "departCityName": "Kaliningrad",
                        "plannedArrivalTime": "01:45",
                        "plannedArrivalTimeStamp": timestamp_ms(
                            cutoff_minus_adjustment + timedelta(hours=4, minutes=45)
                        ),
                        "finalArrivalTime": "21:14",
                    },
                ]
            },
        },
    }
    return payload


def encode_status_payload(payload: dict) -> str:
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    return f"<html><script>var tplB64='eA==';var pr='{encoded}';var w=window;</script></html>"


def status_html() -> str:
    return encode_status_payload(status_payload())


@pytest.mark.parametrize(
    ("direction", "expected"),
    [
        (
            "arrivals",
            [
                {
                    "time": "01:10",
                    "flight_number": "SU1867",
                    "route_point": "Yerevan",
                    "airline": "Aeroflot",
                    "terminal": "C",
                    "status": "Landed at 18:09",
                },
                {
                    "time": "01:45",
                    "flight_number": "DP6874",
                    "route_point": "Kaliningrad",
                    "airline": "Pobeda",
                    "terminal": "D",
                    "status": "Delayed until 21:14",
                },
            ],
        ),
        (
            "departures",
            [
                {
                    "time": "17:55",
                    "flight_number": "OLD100",
                    "route_point": "Old City",
                    "airline": "Old Air",
                    "terminal": "B",
                    "status": "Scheduled",
                },
                {
                    "time": "00:05",
                    "flight_number": "SU6311",
                    "route_point": "Kaliningrad",
                    "airline": "Aeroflot",
                    "terminal": "B",
                    "status": "Delayed until 18:27",
                },
                {
                    "time": "00:10",
                    "flight_number": "SU1606",
                    "route_point": "Samara",
                    "airline": "Aeroflot",
                    "terminal": "B",
                    "status": "En route",
                },
            ],
        ),
    ],
)
def test_parse_current_trip_board(
    direction: str, expected: list[dict[str, str]]
) -> None:
    trip_board = load_module()

    result = trip_board.parse_trip_board(
        status_html(),
        airport="SVO",
        direction=direction,
        observed_at="2026-07-14T18:15:00+00:00",
    )

    assert result["ok"] is True
    assert set(result) == {
        "ok",
        "airport",
        "airport_name",
        "direction",
        "date",
        "date_label",
        "source",
        "observed_at",
        "rows",
    }
    assert result["airport"] == "SVO"
    assert result["direction"] == direction
    assert result["date"] == "2026-07-15"
    assert result["source"] == {
        "name": "Trip.com",
        "data_provider": "VariFlight",
        "kind": "airport_board_aggregator",
        "url": "https://www.trip.com/flights/status/svo/",
    }
    assert result["observed_at"] == "2026-07-14T18:15:00+00:00"
    assert result["rows"] == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("svo", "SVO"), (" KUL ", "KUL")],
)
def test_normalize_iata(value: str, expected: str) -> None:
    trip_board = load_module()
    assert trip_board.normalize_iata(value) == expected


def test_rejects_invalid_iata_and_non_board_pages() -> None:
    trip_board = load_module()

    with pytest.raises(trip_board.TripBoardError, match="invalid_airport_iata"):
        trip_board.normalize_iata("SVO1")
    with pytest.raises(trip_board.TripBoardError, match="trip_antibot_challenge"):
        trip_board.parse_trip_board(
            "<title>Challenge Validation</title>",
            airport="SVO",
            direction="arrivals",
        )
    with pytest.raises(trip_board.TripBoardError, match="trip_parser_changed"):
        trip_board.parse_trip_board(
            "<html><body>No board here</body></html>",
            airport="SVO",
            direction="arrivals",
        )


@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        ("missing_airport", "trip_parser_changed"),
        ("invalid_airport", "trip_parser_changed"),
        ("mismatched_airport", "trip_airport_mismatch"),
    ],
)
def test_required_board_identity_is_fail_closed(case: str, expected_code: str) -> None:
    trip_board = load_module()
    payload = status_payload()
    data = payload["data"]

    if case == "missing_airport":
        data.pop("airportCode")
    elif case == "invalid_airport":
        data["airportCode"] = "not-iata"
    elif case == "mismatched_airport":
        data["airportCode"] = "KUL"

    with pytest.raises(trip_board.TripBoardError) as exc_info:
        trip_board.parse_trip_board(
            encode_status_payload(payload),
            airport="SVO",
            direction="departures",
        )

    assert exc_info.value.code == expected_code


def test_board_returns_every_source_row_without_ui_truncation() -> None:
    trip_board = load_module()
    payload = status_payload()
    source_rows = payload["data"]["originData"]["flightStatusByAirport"]

    result = trip_board.parse_trip_board(
        encode_status_payload(payload),
        airport="SVO",
        direction="departures",
    )

    assert len(result["rows"]) == len(source_rows)
    assert [row["flight_number"] for row in result["rows"]] == [
        row["flightNo"] for row in source_rows
    ]


@pytest.mark.parametrize(
    "invalid_timestamp",
    [
        True,
        "123",
        "NaN",
        "Infinity",
        float("nan"),
        float("inf"),
        None,
        0,
        "",
        10**1000,
        -(10**1000),
    ],
)
def test_timestamp_requires_a_positive_finite_number(invalid_timestamp: object) -> None:
    trip_board = load_module()
    payload = status_payload()
    payload["data"]["originData"]["flightStatusByAirport"][0][
        "plannedDepartTimeStamp"
    ] = invalid_timestamp

    with pytest.raises(trip_board.TripBoardError) as exc_info:
        trip_board.parse_trip_board(
            encode_status_payload(payload),
            airport="SVO",
            direction="departures",
        )

    assert exc_info.value.code == "trip_parser_changed"


@pytest.mark.parametrize(
    "case",
    ["missing_current_date", "invalid_current_date", "non_object_row", "bad_state"],
)
def test_date_and_row_schema_are_fail_closed(case: str) -> None:
    trip_board = load_module()
    payload = status_payload()

    if case == "missing_current_date":
        payload.pop("currentDate")
    elif case == "invalid_current_date":
        payload["currentDate"] = "not-a-date"
    elif case == "non_object_row":
        payload["data"]["originData"]["flightStatusByAirport"] = ["bad-row"]
    elif case == "bad_state":
        payload["data"]["originData"]["flightStatusByAirport"][0]["flightState"] = "1"

    with pytest.raises(trip_board.TripBoardError) as exc_info:
        trip_board.parse_trip_board(
            encode_status_payload(payload),
            airport="SVO",
            direction="departures",
        )

    assert exc_info.value.code == "trip_parser_changed"


def test_invalid_timestamp_fails_closed() -> None:
    trip_board = load_module()
    payload = status_payload()
    payload["data"]["originData"]["flightStatusByAirport"][0][
        "plannedDepartTimeStamp"
    ] = "bad"

    with pytest.raises(trip_board.TripBoardError) as exc_info:
        trip_board.parse_trip_board(
            encode_status_payload(payload),
            airport="SVO",
            direction="departures",
        )

    assert exc_info.value.code == "trip_parser_changed"


@pytest.mark.parametrize(
    ("exact_flight", "operating_date", "expected_code"),
    [
        ("MISSING100", "2026-07-15", "flight_not_found"),
        ("SU6311", "2026-07-14", "trip_operating_date_mismatch"),
    ],
)
def test_exact_flight_lookup_does_not_substitute_or_ignore_date(
    exact_flight: str, operating_date: str, expected_code: str
) -> None:
    trip_board = load_module()

    with pytest.raises(trip_board.TripBoardError) as exc_info:
        trip_board.parse_trip_board(
            status_html(),
            airport="SVO",
            direction="departures",
            exact_flight=exact_flight,
            operating_date=operating_date,
        )

    assert exc_info.value.code == expected_code


def test_json_cli_error_envelope(capsys: pytest.CaptureFixture[str]) -> None:
    trip_board = load_module()

    return_code = trip_board.main(["SVO1", "--direction", "arrivals", "--json"])
    captured = capsys.readouterr()

    assert return_code == 2
    assert json.loads(captured.out) == {
        "ok": False,
        "error": {"code": "invalid_airport_iata", "detail": None},
    }
    assert captured.err == ""


def test_text_render_is_compact_and_source_labelled() -> None:
    trip_board = load_module()
    result = trip_board.parse_trip_board(
        status_html(),
        airport="SVO",
        direction="departures",
    )

    text = trip_board.render_text(result)

    assert "SVO — DEPARTURES" in text
    assert "Airline" in text
    assert "00:05  SU6311  Kaliningrad  Aeroflot  B  Delayed until 18:27" in text
    assert "Trip.com; data: VariFlight" in text
