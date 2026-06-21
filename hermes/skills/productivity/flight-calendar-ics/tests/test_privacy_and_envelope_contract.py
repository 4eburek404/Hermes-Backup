#!/usr/bin/env python3
"""Focused contracts for privacy redaction and CLI envelope helpers."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from helpers import CliRunnerMixin, ScriptPathMixin


class PrivacyAndEnvelopeContractTests(CliRunnerMixin, ScriptPathMixin, unittest.TestCase):
    maxDiff = None

    def test_redact_replaces_private_url_query_values(self) -> None:
        from flight_calendar.privacy import redact

        raw = (
            "https://example.invalid/manage?pnrLocator=ABC123&lastName=ORLOV&pnrKey="
            "0123456789abcdef0123456789abcdef&ticket=5555555555555 "
            "Authorization: Bearer secret-token"
        )
        redacted = redact(raw)

        self.assertIn("pnrLocator=[REDACTED]", redacted)
        self.assertIn("lastName=[REDACTED]", redacted)
        self.assertIn("pnrKey=[REDACTED]", redacted)
        self.assertIn("ticket=[REDACTED]", redacted)
        self.assertIn("Authorization: Bearer [REDACTED]", redacted)
        self.assertNotIn("ABC123", redacted)
        self.assertNotIn("ORLOV", redacted)
        self.assertNotIn("secret-token", redacted)

    def test_envelope_shape_preserves_schema_version_ok_command_process_data(self) -> None:
        from flight_calendar.envelope import add_step, envelope

        process: list[dict[str, object]] = []
        add_step(process, "parse_args")
        obj = envelope(ok=True, command="diagnose", process=process, data={"surface": "diagnostic", "subcommand": "doctor"})

        self.assertEqual(obj["schema_version"], "flight-calendar-ics-cli.v1")
        self.assertTrue(obj["ok"])
        self.assertEqual(obj["command"], "diagnose")
        self.assertEqual(obj["process"], [{"step": "parse_args", "status": "ok"}])
        self.assertEqual(obj["data"], {"surface": "diagnostic", "subcommand": "doctor"})
        self.assertNotIn("error", obj)

    def test_usage_failure_envelope_does_not_print_private_argv_values(self) -> None:
        result = self.run_cli("--json", "build", "auto", "--url", "https://example.invalid/?pnrLocator=ABC123&lastName=ORLOV", "--url-file", "/tmp/source-url.txt")

        self.assertNotEqual(result.returncode, 0)
        obj = json.loads(result.stdout)
        self.assertFalse(obj["ok"])
        serialized = json.dumps(obj, ensure_ascii=False)
        self.assertNotIn("ABC123", serialized)
        self.assertNotIn("ORLOV", serialized)
        self.assertNotIn("ABC123", result.stderr)
        self.assertNotIn("ORLOV", result.stderr)

    def test_successful_build_envelope_can_be_persisted_to_private_bundle(self) -> None:
        from flight_calendar.envelope import envelope, write_envelope_artifact_if_requested

        with tempfile.TemporaryDirectory(prefix="flight-envelope-test.") as tmp:
            envelope_path = Path(tmp) / "envelope.json"
            obj = envelope(
                ok=True,
                command="build",
                process=[{"step": "parse_args", "status": "ok"}],
                data={"envelope_path": str(envelope_path), "segments_count": 1},
            )
            write_envelope_artifact_if_requested(obj["data"], obj)

            persisted = json.loads(envelope_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted, obj)
            self.assertEqual(format(envelope_path.stat().st_mode & 0o777, "03o"), "644")

    def test_emit_json_and_human_are_stable_entrypoints(self) -> None:
        from flight_calendar.envelope import emit_human, emit_json, envelope

        obj = envelope(
            ok=True,
            command="build",
            process=[{"step": "parse_args", "status": "ok"}],
            data={"segments_count": 1, "ics_path": "/tmp/flights.ics"},
        )
        json_buf = io.StringIO()
        human_buf = io.StringIO()
        with contextlib.redirect_stdout(json_buf):
            emit_json(obj)
        with contextlib.redirect_stdout(human_buf):
            emit_human(obj)

        self.assertEqual(json.loads(json_buf.getvalue()), obj)
        self.assertIn("OK: build", human_buf.getvalue())
        self.assertIn("segments: 1", human_buf.getvalue())
        self.assertIn("ics: /tmp/flights.ics", human_buf.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
