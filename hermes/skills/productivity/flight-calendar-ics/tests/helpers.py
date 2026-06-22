"""Shared unittest helpers for flight-calendar-ics contract tests."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CLI = SCRIPTS / "flight_calendar_ics.py"
SCHEMA = ROOT / "schemas" / "cli-envelope.v1.schema.json"


class ScriptPathMixin:
    def setUp(self) -> None:
        super().setUp()
        self._old_path = list(sys.path)
        script_dir = str(SCRIPTS.resolve())
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)

    def tearDown(self) -> None:
        sys.path[:] = self._old_path
        super().tearDown()


class CliRunnerMixin:
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=20,
        )


class JsonEnvelopeAssertionsMixin:
    def parse_stdout_json(self, result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        try:
            obj = json.loads(result.stdout)
        except json.JSONDecodeError as exc:  # pragma: no cover - assertion helper
            self.fail(
                f"stdout is not valid JSON: {exc}\n"
                f"exit={result.returncode}\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
            )
        self.assertIsInstance(obj, dict)
        return obj

    def assert_matches_cli_schema(self, obj: dict[str, Any]) -> None:
        from jsonschema import Draft202012Validator

        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(obj), key=lambda error: list(error.path))
        self.assertEqual(
            [],
            [f"{'/'.join(map(str, error.absolute_path))}: {error.message}" for error in errors],
        )
