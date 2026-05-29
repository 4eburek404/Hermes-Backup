from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import PROJECT, TEST_ENV


class MaintenanceCheckTests(unittest.TestCase):
    def test_json_maintenance_check_reports_provenance_and_runtime_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing_runtime = Path(tmp_dir) / "missing-runtime-flight-search"
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "flights_cli",
                    "--json",
                    "maintenance",
                    "check",
                    "--runtime-path",
                    str(missing_runtime),
                ],
                cwd=PROJECT,
                env=TEST_ENV,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "maintenance check")
        self.assertEqual(payload["issues"], [])

        data = payload["data"]
        self.assertEqual(data["source"]["skill_path"], str(PROJECT.parent))
        self.assertTrue(data["source"]["exists"])
        self.assertIn(data["source"]["git"]["status"], {"ok", "not_git"})
        self.assertIn("branch", data["source"]["git"])
        self.assertIn("head", data["source"]["git"])

        self.assertEqual(data["runtime"]["skill_path"], str(missing_runtime))
        self.assertFalse(data["runtime"]["exists"])
        self.assertEqual(data["versions"], {"skill_md": "0.10.11", "cli": "0.10.11"})
        self.assertEqual(data["source_runtime_parity"]["status"], "runtime_missing")
        self.assertEqual(data["doctor"]["status"], "ok")
        self.assertGreaterEqual(data["references"]["source_count"], 5)
        self.assertIn("runtime_count", data["references"])
        self.assertIn("source_count", data["generated_artifacts"])
        self.assertIn("runtime_count", data["generated_artifacts"])

    def test_human_maintenance_check_is_compact_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing_runtime = Path(tmp_dir) / "missing-runtime-flight-search"
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "flights_cli",
                    "maintenance",
                    "check",
                    "--runtime-path",
                    str(missing_runtime),
                ],
                cwd=PROJECT,
                env=TEST_ENV,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        self.assertLessEqual(len(lines), 12)
        summary = "\n".join(lines)
        self.assertIn("flight-search maintenance", summary)
        self.assertIn("branch:", summary)
        self.assertIn("HEAD:", summary)
        self.assertIn("source:", summary)
        self.assertIn("runtime:", summary)
        self.assertIn("versions:", summary)
        self.assertIn("parity: runtime_missing", summary)
        self.assertIn("doctor: ok", summary)
        self.assertIn("references:", summary)
        self.assertIn("generated artifacts:", summary)


if __name__ == "__main__":
    unittest.main()
