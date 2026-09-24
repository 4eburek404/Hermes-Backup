from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "evals" / "flight-calendar-ics"
CANDIDATE = ROOT.parent / "Hermes-Backup"


def load_run_eval():
    path = EVAL / "run_eval.py"
    spec = importlib.util.spec_from_file_location("flight_calendar_eval_run_eval", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_replay():
    path = EVAL / "replay" / "carrier_http.py"
    spec = importlib.util.spec_from_file_location("flight_calendar_eval_replay", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_selected_matrix_matches_configured_repeats_and_scenario_hashes_are_independent():
    run_eval = load_run_eval()
    manifest = run_eval.load_manifest()
    selected_scenarios = ["ural-url-success", "pdf-success"]
    assert list(manifest["scenarios"]) == ["url-success", "ural-url-success", "pdf-success"]
    case = run_eval.build_case(
        manifest,
        EVAL,
        runtime_version="test-runtime",
        selected_scenarios=selected_scenarios,
    )
    from evals.harness.core import build_matrix

    specs = build_matrix(case)
    expected_matrix = {
        (scenario, model["model"], repeat)
        for scenario in selected_scenarios
        for model in manifest["models"]
        for repeat in range(1, manifest["repeats"] + 1)
    }
    actual_matrix = {(spec.scenario, spec.model, spec.repeat) for spec in specs}
    assert actual_matrix == expected_matrix
    assert len(specs) == len(expected_matrix) == 12
    assert {spec.scenario for spec in specs} == set(selected_scenarios)
    assert len({spec.prompt_version for spec in specs}) == 2
    assert len({spec.fixture_version for spec in specs}) == 2
    assert {spec.repeat for spec in specs} == {1, 2}


def test_ural_replay_is_offline_and_returns_raw_reservation():
    replay = load_replay()
    fixture = EVAL / "fixtures" / "ural" / "reservation.json"
    old = dict(os.environ)
    try:
        os.environ.update(
            {
                "FLIGHT_CALENDAR_EVAL_SCENARIO": "ural-url-success",
                "FLIGHT_CALENDAR_EVAL_HTTP_FIXTURE": str(fixture),
            }
        )
        assert "/12345/js/app.synthetic.js" in replay.request_text(
            "https://service.uralairlines.ru/", headers={"Accept": "text/html"}
        )
        env = replay.request_json(
            "https://service.uralairlines.ru/12345/env/env.json",
            headers={"Accept": "application/json"},
        )
        assert env == {
            "API_URL": "https://ural-api.test/api/",
            "API_KEY": "synthetic-api-key-001",
        }
        assert replay.request_text(
            "https://ural-api.test/api/settings/CurrentDateUtc",
            headers={"Accept": "application/json"},
        ) == "1700000000"
        raw = replay.request_json(
            "https://ural-api.test/api/Reservation?pnrNumber=ABC123&lastName=IVANOV",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": "https://service.uralairlines.ru",
                "Referer": "https://service.uralairlines.ru/",
                "User-Agent": "Mozilla/5.0",
                "X-Api-Key": "synthetic-api-key-001",
            },
        )
        expected = json.loads(fixture.read_text(encoding="utf-8"))
        assert raw == expected
        assert "flights" not in raw
        try:
            replay.request_raw("https://unexpected.example/")
        except replay.TransportError:
            pass
        else:
            raise AssertionError("unexpected replay endpoint was accepted")
    finally:
        os.environ.clear()
        os.environ.update(old)


def test_ural_and_pdf_timezones_match_candidate_catalog():
    catalog = json.loads(
        (
            CANDIDATE
            / "hermes/skills/travel/flight-calendar-ics/data/airport-timezones.json"
        ).read_text(encoding="utf-8")
    )["timezones"]
    assert {code: catalog[code] for code in ("DME", "SVO", "SVX")} == {
        "DME": "Europe/Moscow",
        "SVO": "Europe/Moscow",
        "SVX": "Asia/Yekaterinburg",
    }
    cases = [
        ("DME", "2026-09-21T08:25", "20260921T052500Z"),
        ("SVX", "2026-09-24T20:30", "20260924T153000Z"),
        ("SVO", "2037-10-03T09:15", "20371003T061500Z"),
        ("SVX", "2037-10-06T18:10", "20371006T131000Z"),
    ]
    for airport, value, expected in cases:
        actual = datetime.fromisoformat(value).replace(
            tzinfo=ZoneInfo(catalog[airport])
        ).astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")
        assert actual == expected


def test_pdf_fixture_and_anydoc_shim_are_recorded_and_strict():
    pdf = EVAL / "fixtures" / "pdf" / "ticket.pdf"
    markdown = EVAL / "fixtures" / "pdf" / "anydoc.md"
    shim = EVAL / "replay" / "pdf" / "npx"
    assert pdf.read_bytes().startswith(b"%PDF")
    assert pdf.read_bytes()[:1] != b"{"
    with TemporaryDirectory(prefix="flight-pdf-replay-") as temp:
        output = Path(temp) / "ticket.md"
        env = {
            **os.environ,
            "FLIGHT_CALENDAR_EVAL_ANYDOC_FIXTURE": str(markdown),
        }
        result = subprocess.run(
            [str(shim), "-y", "@firecrawl/anydoc", str(pdf), "-o", str(output)],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert output.read_text(encoding="utf-8") == markdown.read_text(encoding="utf-8")
        bad = subprocess.run(
            [str(shim), "--version"],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert bad.returncode != 0
