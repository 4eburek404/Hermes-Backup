from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import time
from zoneinfo import ZoneInfo

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
            "defaultSelectedTime": "21:00",
            "timeOptionsWithMinutes": [{"label": "21:00", "minutes": 1260}],
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
        timezone_offset_minutes=-120,
        now=LOCAL_NOW,
    )

    assert result["ok"] is True
    assert set(result) == {
        "ok",
        "airport",
        "airport_name",
        "direction",
        "date",
        "date_label",
        "time_from",
        "source",
        "observed_at",
        "rows",
    }
    assert result["airport"] == "SVO"
    assert result["direction"] == direction
    assert result["date"] == "2026-07-15"
    assert result["time_from"] == "21:00"
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
        ("missing_cutoff", "trip_parser_changed"),
        ("invalid_cutoff", "trip_parser_changed"),
        ("missing_time_options", "trip_parser_changed"),
        ("missing_selected_option", "trip_parser_changed"),
        ("invalid_selected_minutes", "trip_parser_changed"),
    ],
)
def test_required_board_metadata_is_fail_closed(case: str, expected_code: str) -> None:
    trip_board = load_module()
    payload = status_payload()
    data = payload["data"]

    if case == "missing_airport":
        data.pop("airportCode")
    elif case == "invalid_airport":
        data["airportCode"] = "not-iata"
    elif case == "mismatched_airport":
        data["airportCode"] = "KUL"
    elif case == "missing_cutoff":
        data.pop("defaultSelectedTime")
    elif case == "invalid_cutoff":
        data["defaultSelectedTime"] = "bad"
    elif case == "missing_time_options":
        data.pop("timeOptionsWithMinutes")
    elif case == "missing_selected_option":
        data["timeOptionsWithMinutes"] = [{"label": "20:45", "minutes": 1245}]
    elif case == "invalid_selected_minutes":
        data["timeOptionsWithMinutes"] = [{"label": "21:00", "minutes": "bad"}]

    with pytest.raises(trip_board.TripBoardError) as exc_info:
        trip_board.parse_trip_board(
            encode_status_payload(payload),
            airport="SVO",
            direction="departures",
            timezone_offset_minutes=-120,
            now=LOCAL_NOW,
        )

    assert exc_info.value.code == expected_code


def test_current_slice_uses_parse_clock_not_stale_payload_timestamp() -> None:
    trip_board = load_module()
    payload = status_payload()
    parse_now = datetime(2026, 7, 15, 0, 1, tzinfo=LOCAL_TIMEZONE)
    stale_page_time = datetime(2026, 7, 14, 23, 59, tzinfo=LOCAL_TIMEZONE)
    payload["currentTimestamp"] = int(stale_page_time.timestamp() * 1000)
    payload["data"]["defaultSelectedTime"] = "00:00"
    payload["data"]["timeOptionsWithMinutes"] = [{"label": "00:00", "minutes": 0}]
    payload["data"]["originData"]["flightStatusByAirport"] = [
        {
            "flightNo": "STALE100",
            "flightState": 1,
            "plannedDepartTime": "12:00",
            "plannedDepartTimeStamp": int(
                datetime(2026, 7, 14, 6, 0, tzinfo=timezone.utc).timestamp() * 1000
            ),
        }
    ]

    result = trip_board.parse_trip_board(
        encode_status_payload(payload),
        airport="SVO",
        direction="departures",
        timezone_offset_minutes=-120,
        now=parse_now,
    )

    assert result["rows"] == []


def test_current_slice_includes_timestamp_equal_to_cutoff() -> None:
    trip_board = load_module()
    payload = status_payload()
    threshold_before_adjustment = datetime(2026, 7, 14, 13, 0, tzinfo=timezone.utc)
    payload["data"]["originData"]["flightStatusByAirport"] = [
        {
            "flightNo": "BEFORE100",
            "flightState": 1,
            "plannedDepartTime": "20:59",
            "plannedDepartTimeStamp": int(
                (threshold_before_adjustment - timedelta(minutes=1)).timestamp() * 1000
            ),
        },
        {
            "flightNo": "EDGE100",
            "flightState": 1,
            "plannedDepartTime": "21:00",
            "plannedDepartTimeStamp": int(
                threshold_before_adjustment.timestamp() * 1000
            ),
        },
    ]

    result = trip_board.parse_trip_board(
        encode_status_payload(payload),
        airport="SVO",
        direction="departures",
        timezone_offset_minutes=-120,
        now=LOCAL_NOW,
    )

    assert [row["flight_number"] for row in result["rows"]] == ["EDGE100"]


@pytest.mark.parametrize(
    ("now", "expected_midnight_utc", "expected_adjustment_ms"),
    [
        (
            datetime(2026, 3, 8, 12, 0, tzinfo=ZoneInfo("America/New_York")),
            datetime(2026, 3, 8, 5, 0, tzinfo=timezone.utc),
            43_200_000,
        ),
        (
            datetime(2026, 11, 1, 12, 0, tzinfo=ZoneInfo("America/New_York")),
            datetime(2026, 11, 1, 4, 0, tzinfo=timezone.utc),
            46_800_000,
        ),
        (
            datetime(
                2026,
                11,
                1,
                0,
                30,
                tzinfo=ZoneInfo("America/Havana"),
                fold=0,
            ),
            datetime(2026, 11, 1, 4, 0, tzinfo=timezone.utc),
            43_200_000,
        ),
        (
            datetime(
                2026,
                11,
                1,
                0,
                30,
                tzinfo=ZoneInfo("America/Havana"),
                fold=1,
            ),
            datetime(2026, 11, 1, 4, 0, tzinfo=timezone.utc),
            46_800_000,
        ),
    ],
)
def test_trip_cutoff_uses_javascript_dst_disambiguation(
    now: datetime, expected_midnight_utc: datetime, expected_adjustment_ms: int
) -> None:
    trip_board = load_module()
    data = {
        "timeOptionsWithMinutes": [{"label": "00:00", "minutes": 0}],
    }

    cutoff_ms, adjustment_ms = trip_board._trip_filter_values(data, "00:00", None, now)

    assert (
        datetime.fromtimestamp(cutoff_ms / 1000, timezone.utc) == expected_midnight_utc
    )
    assert adjustment_ms == expected_adjustment_ms


def test_runtime_clock_path_uses_javascript_dst_disambiguation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trip_board = load_module()
    real_datetime = trip_board.datetime

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            value = real_datetime.fromtimestamp(1_793_511_000, timezone.utc)
            return value.astimezone(tz) if tz is not None else value.astimezone()

    previous_tz = os.environ.get("TZ")
    os.environ["TZ"] = "America/Havana"
    time.tzset()
    monkeypatch.setattr(trip_board, "datetime", FrozenDateTime)

    try:
        # Prime libc with the later midnight candidate: tm_isdst=-1 must not
        # inherit that choice because JavaScript always selects the earlier fold.
        time.mktime((2026, 11, 1, 0, 0, 0, 0, 0, 0))
        cutoff_ms, adjustment_ms = trip_board._trip_filter_values(
            {"timeOptionsWithMinutes": [{"label": "00:00", "minutes": 0}]},
            "00:00",
            None,
            None,
        )
    finally:
        if previous_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous_tz
        time.tzset()

    assert cutoff_ms == 1_793_505_600_000
    assert adjustment_ms == 46_800_000


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
            timezone_offset_minutes=-120,
            now=LOCAL_NOW,
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
            timezone_offset_minutes=-120,
            now=LOCAL_NOW,
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
            timezone_offset_minutes=-120,
            now=LOCAL_NOW,
        )

    assert exc_info.value.code == "trip_parser_changed"


def test_current_slice_is_limited_to_first_24_rows() -> None:
    trip_board = load_module()
    payload = status_payload()
    threshold_before_adjustment = datetime(2026, 7, 14, 13, 0, tzinfo=timezone.utc)
    payload["data"]["originData"]["flightStatusByAirport"] = [
        {
            "flightNo": f"TEST{index:02d}",
            "flightState": 1,
            "plannedDepartTime": "21:00",
            "plannedDepartTimeStamp": int(
                (threshold_before_adjustment + timedelta(minutes=index)).timestamp()
                * 1000
            ),
        }
        for index in range(25)
    ]

    result = trip_board.parse_trip_board(
        encode_status_payload(payload),
        airport="SVO",
        direction="departures",
        timezone_offset_minutes=-120,
        now=LOCAL_NOW,
    )

    assert len(result["rows"]) == 24
    assert result["rows"][0]["flight_number"] == "TEST00"
    assert result["rows"][-1]["flight_number"] == "TEST23"


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
        timezone_offset_minutes=-120,
        now=LOCAL_NOW,
    )

    text = trip_board.render_text(result)

    assert "SVO — DEPARTURES" in text
    assert "Airline" in text
    assert "00:05  SU6311  Kaliningrad  Aeroflot  B  Delayed until 18:27" in text
    assert "Trip.com; data: VariFlight" in text
