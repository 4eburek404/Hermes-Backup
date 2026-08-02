from __future__ import annotations

import importlib.util
from http.client import IncompleteRead
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "sheremetyevo.py"


def load_module():
    spec = importlib.util.spec_from_file_location("sheremetyevo", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def airport(
    iata: str,
    city: str,
    airport_name: str,
    timezone_name: str,
) -> dict[str, str]:
    return {
        "iata": iata,
        "city": city,
        "airport": airport_name,
        "timezone": timezone_name,
    }


def flight_row(
    operating_date: str,
    *,
    flight_number: str = "1404",
    status: str = "Регистрация в 09:25",
) -> dict:
    return {
        "i_id": f"id-{operating_date}-{flight_number}",
        "ad": "D",
        "co": {"code": "SU", "name": "Аэрофлот"},
        "flt": flight_number,
        "dat": f"{operating_date}T00:00:00+03:00",
        "t_st": f"{operating_date}T15:25:00+03:00",
        "t_et": None,
        "t_st_mar": f"{operating_date}T17:50:00+03:00",
        "term": "B",
        "gate_id": "",
        "chin_id": "",
        "estimated_chin_start": f"{operating_date}T09:25:00+03:00",
        "estimated_chin_finish": f"{operating_date}T14:45:00+03:00",
        "vip_status_rus": status,
        "vip_status_eng": "Check-in 09:25",
        "mar1": airport("SVO", "Москва", "Шереметьево", "Europe/Moscow"),
        "mar2": airport("SVX", "Екатеринбург", "Кольцово", "Asia/Yekaterinburg"),
    }


def timetable_payload() -> dict:
    return {
        "items": [
            flight_row("2026-07-13"),
            flight_row("2026-07-16", flight_number="140"),
            flight_row("2026-07-16"),
        ],
        "pagination": {"totalItems": 3},
    }


def arrival_row() -> dict:
    return {
        "i_id": "arrival-2026-07-14-SU1867",
        "ad": "A",
        "co": {"code": "SU", "name": "Аэрофлот"},
        "flt": "1867",
        "dat": "2026-07-14T00:00:00+03:00",
        "t_st": "2026-07-14T18:00:00+03:00",
        "t_et": "2026-07-14T18:08:00+03:00",
        "t_st_mar": "2026-07-14T14:37:00+03:00",
        "term": "C",
        "gate_id": "",
        "chin_id": "",
        "estimated_chin_start": None,
        "estimated_chin_finish": None,
        "vip_status_rus": "Совершил посадку в 18:09",
        "vip_status_eng": "Landed at 18:09",
        "mar1": airport("EVN", "Ереван", "Звартноц", "Asia/Yerevan"),
        "mar2": airport("SVO", "Москва", "Шереметьево", "Europe/Moscow"),
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("SU1404", "SU1404"),
        ("su 1404", "SU1404"),
        ("SU-1404", "SU1404"),
        ("5N 293", "5N293"),
    ],
)
def test_normalize_flight_number(value: str, expected: str) -> None:
    sheremetyevo = load_module()
    assert sheremetyevo.normalize_flight_number(value) == expected


@pytest.mark.parametrize("value", ["1404", "SU", "SU_1404", "SU140400", ""])
def test_rejects_invalid_flight_number(value: str) -> None:
    sheremetyevo = load_module()
    with pytest.raises(sheremetyevo.SheremetyevoError) as exc_info:
        sheremetyevo.normalize_flight_number(value)
    assert exc_info.value.code == "invalid_flight_number"


def test_selects_exact_flight_and_date_from_official_timetable() -> None:
    sheremetyevo = load_module()

    result = sheremetyevo.parse_timetable(
        timetable_payload(),
        flight_number="su 1404",
        operating_date="2026-07-16",
        source_updated_at="Tue, 14 Jul 2026 19:57:31 GMT",
    )

    assert result == {
        "ok": True,
        "flight_number": "SU1404",
        "date": "2026-07-16",
        "direction": "departure",
        "airline": "Аэрофлот",
        "route": {
            "origin": {
                "iata": "SVO",
                "city": "Москва",
                "airport": "Шереметьево",
                "timezone": "Europe/Moscow",
            },
            "destination": {
                "iata": "SVX",
                "city": "Екатеринбург",
                "airport": "Кольцово",
                "timezone": "Asia/Yekaterinburg",
            },
        },
        "schedule": {
            "departure": "2026-07-16T15:25:00+03:00",
            "revised_departure": None,
            "arrival": "2026-07-16T19:50:00+05:00",
            "revised_arrival": None,
        },
        "terminal": "B",
        "gate": None,
        "check_in": {
            "desks": None,
            "opens_at": "2026-07-16T09:25:00+03:00",
            "closes_at": "2026-07-16T14:45:00+03:00",
        },
        "status": {
            "ru": "Регистрация в 09:25",
            "en": "Check-in 09:25",
        },
        "source": {
            "name": "Sheremetyevo International Airport",
            "kind": "official_airport_board",
            "url": "https://www.svo.aero/bitrix/timetable/?search=SU1404&perPage=9999&page=0",
            "updated_at": "Tue, 14 Jul 2026 19:57:31 GMT",
        },
    }

    arrival_result = sheremetyevo.parse_timetable(
        {"items": [arrival_row()]},
        flight_number="SU1867",
        operating_date="2026-07-14",
    )
    assert arrival_result["direction"] == "arrival"
    assert arrival_result["schedule"] == {
        "departure": "2026-07-14T15:37:00+04:00",
        "revised_departure": None,
        "arrival": "2026-07-14T18:00:00+03:00",
        "revised_arrival": "2026-07-14T18:08:00+03:00",
    }


@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        ("not_object", "svo_parser_changed"),
        ("items_not_list", "svo_parser_changed"),
        ("row_not_object", "svo_parser_changed"),
        ("malformed_date", "svo_parser_changed"),
        ("missing_origin_timezone", "svo_parser_changed"),
        ("malformed_destination_timezone", "svo_parser_changed"),
        ("not_found", "svo_flight_not_found"),
        ("ambiguous", "svo_ambiguous_flight"),
    ],
)
def test_timetable_selection_is_fail_closed(case: str, expected_code: str) -> None:
    sheremetyevo = load_module()
    payload: object = timetable_payload()

    if case == "not_object":
        payload = []
    elif case == "items_not_list":
        payload["items"] = "bad"
    elif case == "row_not_object":
        payload["items"].append("bad")
    elif case == "malformed_date":
        payload["items"][0]["dat"] = "not-a-date"
    elif case == "missing_origin_timezone":
        payload["items"][2]["mar1"].pop("timezone")
    elif case == "malformed_destination_timezone":
        payload["items"][2]["mar2"]["timezone"] = "/etc/passwd"
    elif case == "not_found":
        payload["items"] = [flight_row("2026-07-15")]
    elif case == "ambiguous":
        payload["items"].append(flight_row("2026-07-16"))

    with pytest.raises(sheremetyevo.SheremetyevoError) as exc_info:
        sheremetyevo.parse_timetable(
            payload,
            flight_number="SU1404",
            operating_date="2026-07-16",
        )

    assert exc_info.value.code == expected_code


def test_incomplete_response_is_a_named_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sheremetyevo = load_module()

    class IncompleteResponse:
        status = 200
        headers: dict[str, str] = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            raise IncompleteRead(b"{", 1)

    monkeypatch.setattr(
        sheremetyevo,
        "urlopen",
        lambda request, timeout: IncompleteResponse(),
    )

    with pytest.raises(sheremetyevo.SheremetyevoError) as exc_info:
        sheremetyevo.fetch_timetable("SU1404")

    assert exc_info.value.code == "svo_network_error"
    assert exc_info.value.detail == "IncompleteRead"


def test_text_render_is_compact_and_officially_source_labelled() -> None:
    sheremetyevo = load_module()
    result = sheremetyevo.parse_timetable(
        timetable_payload(),
        flight_number="SU1404",
        operating_date="2026-07-16",
        source_updated_at="Tue, 14 Jul 2026 19:57:31 GMT",
    )

    text = sheremetyevo.render_text(result)

    assert text.splitlines()[0] == "SU1404 — 2026-07-16 — Регистрация в 09:25"
    assert "Route: SVO Москва → SVX Екатеринбург" in text
    assert "Scheduled: 15:25 MSK → 19:50 +05" in text
    assert "Terminal / gate: B / not assigned" in text
    assert "Check-in: 09:25–14:45 MSK; desks not assigned" in text
    assert "Source: Sheremetyevo official airport board" in text

    arrival_result = sheremetyevo.parse_timetable(
        {"items": [arrival_row()]},
        flight_number="SU1867",
        operating_date="2026-07-14",
    )
    arrival_text = sheremetyevo.render_text(arrival_result)
    assert "Scheduled: 15:37 +04 → 18:00 MSK" in arrival_text
    assert "Revised arrival: 18:08 MSK" in arrival_text


def test_json_cli_success_and_validation_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sheremetyevo = load_module()

    monkeypatch.setattr(
        sheremetyevo,
        "fetch_timetable",
        lambda flight_number, timeout=30: (
            timetable_payload(),
            "Tue, 14 Jul 2026 19:57:31 GMT",
        ),
    )

    return_code = sheremetyevo.main(["su 1404", "--date", "2026-07-16", "--json"])
    captured = capsys.readouterr()
    assert return_code == 0
    assert json.loads(captured.out)["flight_number"] == "SU1404"
    assert captured.err == ""

    return_code = sheremetyevo.main(["1404", "--date", "2026-07-16", "--json"])
    captured = capsys.readouterr()
    assert return_code == 2
    assert json.loads(captured.out) == {
        "ok": False,
        "error": {"code": "invalid_flight_number", "detail": None},
    }
    assert captured.err == ""

    return_code = sheremetyevo.main(
        ["SU1404", "--date", "2026-07-16", "--timeout", "0", "--json"]
    )
    captured = capsys.readouterr()
    assert return_code == 2
    assert json.loads(captured.out) == {
        "ok": False,
        "error": {"code": "invalid_timeout", "detail": None},
    }
    assert captured.err == ""
