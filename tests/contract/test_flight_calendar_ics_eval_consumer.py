#!/usr/bin/env python3
"""Minimal executable contract for the flight-calendar-ics agent eval."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from evals.harness.core import Harness


SOURCE_REPO = Path(__file__).resolve().parents[2]
CONSUMER_PATH = SOURCE_REPO / "evals" / "flight-calendar-ics" / "consumer.py"
RUNNER_PATH = SOURCE_REPO / "evals" / "flight-calendar-ics" / "run_eval.py"
SKILL_PATH = Path("hermes/skills/travel/flight-calendar-ics")
BOOKING_URL = "https://www.aeroflot.ru/sb/pnr/app/ru-ru#/pnr?pnr_key=0000000000000000000000000000000000000000000000000000000000000000&pnr_locator=ABC123"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_repo(root: Path) -> Path:
    repo = root / "repo"
    skill = repo / SKILL_PATH
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: flight-calendar-ics\n---\n# Synthetic skill\n",
        encoding="utf-8",
    )
    (skill / "scripts" / "flight_calendar_ics.py").write_text(
        "print('synthetic')\n",
        encoding="utf-8",
    )
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Eval Contract")
    git(repo, "config", "user.email", "eval@example.invalid")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "candidate")
    git(repo, "branch", "candidate")
    return repo


def make_eval_root(root: Path) -> Path:
    eval_root = root / "eval"
    (eval_root / "prompt").mkdir(parents=True)
    (eval_root / "fixtures").mkdir()
    (eval_root / "expected").mkdir()

    (eval_root / "prompt" / "url-success.txt").write_text(
        f"Создай .ics по ссылке бронирования:\n{BOOKING_URL}\n",
        encoding="utf-8",
    )
    (eval_root / "fixtures" / "aeroflot-pnr-view-v3.json").write_text(
        "{\"success\": true}\n",
        encoding="utf-8",
    )
    oracle = {
        "expected_event_count": 2,
        "events": [
            {
                "dtstart": "20370923T083000Z",
                "dtend": "20370923T105000Z",
                "description_fragments": [
                    "23.09 Екатеринбург -> Москва 13:30 13:50",
                    "Самолет: Airbus A330-300",
                ],
            },
            {
                "dtstart": "20370925T122500Z",
                "dtend": "20370925T145000Z",
                "description_fragments": [
                    "25.09 Москва -> Екатеринбург 15:25 19:50",
                    "Самолет: Boeing 737-800",
                ],
            },
        ],
        "privacy_forbidden_final_answer": [BOOKING_URL, "ABC123"],
    }
    (eval_root / "expected" / "url-success.json").write_text(
        json.dumps(oracle, ensure_ascii=False),
        encoding="utf-8",
    )
    return eval_root


def make_manifest() -> dict:
    return {
        "name": "flight-calendar-ics-agent-level-eval",
        "mode": "recorded",
        "skill": {
            "name": "flight-calendar-ics",
            "path": "hermes/skills/travel/flight-calendar-ics/SKILL.md",
        },
        "skill_versions": {
            "candidate": {"source": "git", "ref": "candidate"},
        },
        "models": [
            {"model": "model-a", "provider": "provider-a"},
            {"model": "model-b", "provider": "provider-b"},
            {"model": "model-c", "provider": "provider-c"},
        ],
        "repeats": 1,
        "execution": {
            "toolsets": ["terminal", "file", "skills"],
            "max_turns": 10,
            "run_budget": 90,
            "yolo": True,
            "source": "eval",
        },
        "scenarios": {
            "url-success": {
                "prompt": "prompt/url-success.txt",
                "fixture": "fixtures/aeroflot-pnr-view-v3.json",
                "oracle": "expected/url-success.json",
                "evaluation": {
                    "trajectory": {
                        "required_cli_fragments": [
                            "flight_calendar_ics.py",
                            "--json",
                            "build",
                            "--url",
                        ],
                        "forbidden_command_patterns": [
                            "--url-file",
                            "--url-stdin",
                            r"\bmktemp\b",
                            r"\becho\b",
                            r"\bprintf\b",
                        ],
                        "forbidden_tool_names": ["write_file", "patch"],
                        "require_single_terminal_call": True,
                        "stop_after_cli": True,
                    }
                },
            }
        },
    }


def fake_hermes(root: Path) -> list[str]:
    script = root / "fake_hermes.py"
    script.write_text(
        r"""
import json
import tempfile
from pathlib import Path
import sys

if "--version" in sys.argv:
    print("fake-hermes 1.0")
    raise SystemExit(0)

artifact_dir = Path(tempfile.mkdtemp(prefix="fake-flight-ics."))
artifact = artifact_dir / "flights.ics"
artifact.write_text(
    "BEGIN:VCALENDAR\r\n"
    "VERSION:2.0\r\n"
    "BEGIN:VEVENT\r\n"
    "DTSTART:20370923T083000Z\r\n"
    "DTEND:20370923T105000Z\r\n"
    "DESCRIPTION:23.09 Екатеринбург -> Москва 13:30 13:50\\nСамолет: Airbus A330-300\r\n"
    "END:VEVENT\r\n"
    "BEGIN:VEVENT\r\n"
    "DTSTART:20370925T122500Z\r\n"
    "DTEND:20370925T145000Z\r\n"
    "DESCRIPTION:25.09 Москва -> Екатеринбург 15:25 19:50\\nСамолет: Boeing 737-800\r\n"
    "END:VEVENT\r\n"
    "END:VCALENDAR\r\n",
    encoding="utf-8",
)
command = (
    '"$HERMES_HOME/skills/travel/flight-calendar-ics/scripts/flight_calendar_ics.py" '
    "--json build --url '<booking-url>'"
)
print(json.dumps({"type": "tool_use", "name": "skill_view", "input": {"name": "flight-calendar-ics"}}))
print(json.dumps({"type": "tool_use", "name": "terminal", "input": {"command": command}}))
print(json.dumps({
    "type": "tool_result",
    "name": "terminal",
    "content": json.dumps({
        "ok": True,
        "media": f"MEDIA:{artifact}",
        "segments_count": 2,
        "no_further_action_needed": True,
    }),
}))
print(json.dumps({"type": "result", "text": f"Готово: MEDIA:{artifact}"}))
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return [sys.executable, str(script)]


class FlightCalendarEvalContract(unittest.TestCase):
    def test_minimal_matrix_runs_three_models_and_scores_same_success_scenario(self) -> None:
        if not CONSUMER_PATH.is_file():
            self.fail("flight-calendar-ics eval consumer is absent")
        if not RUNNER_PATH.is_file():
            self.fail("flight-calendar-ics eval runner is absent")

        consumer_type = load_module(
            CONSUMER_PATH,
            "flight_calendar_eval_consumer",
        ).FlightCalendarIcsConsumer
        runner = load_module(RUNNER_PATH, "flight_calendar_eval_runner")

        with tempfile.TemporaryDirectory(prefix="flight-calendar-eval-contract-") as temp:
            root = Path(temp)
            repo = make_repo(root)
            eval_root = make_eval_root(root)
            manifest = make_manifest()
            consumer = consumer_type(
                eval_root,
                repo,
                manifest,
                hermes_command=fake_hermes(root),
            )
            case = runner.build_case(
                manifest,
                eval_root,
                runtime_version="fake-hermes 1.0",
            )
            batch = Harness(consumer).run(case, root / "batch")

            self.assertEqual(3, len(batch["expected_run_ids"]))
            self.assertEqual(3, len(batch["runs"]))
            self.assertEqual(
                {"provider-a", "provider-b", "provider-c"},
                {run["provider"] for run in batch["runs"]},
            )
            for run in batch["runs"]:
                self.assertEqual("COMPLETED", run["execution_status"])
                self.assertEqual("PASS", run["score"]["outcome"])
                self.assertEqual("PASS", run["score"]["trajectory"])
                self.assertEqual("PASS", run["score"]["privacy"])
                self.assertEqual(1, run["metrics"]["cli_build_calls"])
                self.assertTrue(Path(run["artifact_evidence_path"]).is_file())
                self.assertEqual(
                    "git",
                    run["skill_source"]["source"],
                )
                self.assertEqual(
                    git(repo, "rev-parse", "candidate"),
                    run["skill_source"]["resolved_commit"],
                )


if __name__ == "__main__":
    unittest.main()
