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
                    "maint",
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
        self.assertEqual(payload["command"], "maint check")
        self.assertEqual(payload["issues"], [])

        data = payload["data"]
        self.assertEqual(data["source"]["skill_path"], str(PROJECT.parent))
        self.assertTrue(data["source"]["exists"])
        self.assertIn(data["source"]["git"]["status"], {"ok", "not_git"})
        self.assertIn("branch", data["source"]["git"])
        self.assertIn("head", data["source"]["git"])

        self.assertEqual(data["runtime"]["skill_path"], str(missing_runtime))
        self.assertFalse(data["runtime"]["exists"])
        self.assertEqual(data["versions"], {"skill_md": "0.13.0", "cli": "0.10.0"})
        self.assertTrue(data["version_manifest"]["exists"])
        self.assertEqual(data["version_manifest"]["mismatches"], [])
        self.assertEqual(
            data["version_manifest"]["data"]["skill"],
            {"name": "flight-search", "version": "0.13.0"},
        )
        self.assertEqual(
            data["version_manifest"]["data"]["cli"],
            {"package": "flights-cli", "version": "0.10.0"},
        )
        self.assertEqual(
            data["version_manifest"]["data"]["command_surface"]["version"],
            "command_surface.v2",
        )
        self.assertEqual(data["source_runtime_parity"]["status"], "runtime_missing")
        workflow = data["branch_workflow"]
        self.assertEqual(workflow["source"]["path"], str(PROJECT.parent))
        self.assertEqual(workflow["source"]["branch"], data["source"]["git"]["branch"])
        self.assertEqual(workflow["source"]["head"], data["source"]["git"]["head"])
        self.assertEqual(workflow["source"]["dirty"], data["source"]["git"]["dirty"])
        self.assertEqual(workflow["runtime"]["path"], str(missing_runtime))
        self.assertFalse(workflow["runtime"]["exists"])
        self.assertEqual(workflow["manifest"]["skill_version"], "0.13.0")
        self.assertEqual(workflow["manifest"]["cli_version"], "0.10.0")
        self.assertEqual(
            workflow["manifest"]["command_surface_version"], "command_surface.v2"
        )
        self.assertEqual(workflow["manifest"]["mismatches"], [])
        self.assertEqual(workflow["command_surface"]["version"], "command_surface.v2")
        self.assertEqual(
            workflow["command_surface"]["canonical_path"], "search --request"
        )
        self.assertIn(
            "diagnose plan", workflow["command_surface"]["diagnostic_commands"]
        )
        self.assertIn(
            "diagnose trace", workflow["command_surface"]["diagnostic_commands"]
        )
        self.assertEqual(workflow["parity"]["status"], "runtime_missing")
        self.assertFalse(workflow["parity"]["runtime_claims_allowed"])
        self.assertEqual(
            workflow["parity"]["claim_basis"], "source_only_not_runtime_proven"
        )
        self.assertEqual(data["doctor"]["status"], "ok")
        self.assertGreaterEqual(data["references"]["source_count"], 5)
        self.assertIn("runtime_count", data["references"])
        self.assertIn("source_count", data["generated_artifacts"])
        self.assertIn("runtime_count", data["generated_artifacts"])

    def test_user_text_maintenance_check_is_compact_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing_runtime = Path(tmp_dir) / "missing-runtime-flight-search"
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "flights_cli",
                    "maint",
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
        self.assertEqual(proc.stderr, "")
        self.assertFalse(proc.stdout.lstrip().startswith("{"))


if __name__ == "__main__":
    unittest.main()
