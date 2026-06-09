#!/usr/bin/env python3
"""maint namespace read-only CLI contracts for flight-calendar-ics."""
from __future__ import annotations

import json
import importlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "flight_calendar_ics.py"
SCHEMA = ROOT / "schemas" / "cli-envelope.v1.schema.json"


class MaintNamespaceContractTests(unittest.TestCase):
    maxDiff = None

    def _run_json(self, *args: str) -> dict:
        result = subprocess.run(
            [sys.executable, str(CLI), "--json", *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def test_maint_contracts_returns_schema_valid_read_only_registry_report(self) -> None:
        from jsonschema import Draft202012Validator

        payload = self._run_json("maint", "contracts")

        Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(payload)
        self.assertEqual(payload["command"], "maint")
        self.assertEqual(payload["data"]["surface"], "maintenance")
        self.assertEqual(payload["data"]["subcommand"], "contracts")
        self.assertEqual(payload["data"]["write_performed"], False)
        self.assertIn("build auto", payload["data"]["command_registry"]["production"])
        self.assertIn("maint source-runtime-sync", payload["data"]["command_registry"]["maintenance"])
        self.assertEqual(payload["data"]["checks"]["command_registry_present"], True)
        self.assertEqual([step["step"] for step in payload["process"]], ["parse_args", "no_write", "emit_json"])

    def test_maint_source_runtime_sync_reports_drift_without_file_contents_or_writes(self) -> None:
        from jsonschema import Draft202012Validator

        with tempfile.TemporaryDirectory(prefix="flight-maint-sync.") as tmp:
            root = Path(tmp)
            source = root / "source"
            runtime = root / "runtime"
            source.mkdir()
            runtime.mkdir()
            (source / "same.txt").write_text("same\n", encoding="utf-8")
            (runtime / "same.txt").write_text("same\n", encoding="utf-8")
            (source / "changed.txt").write_text("source-secret-value\n", encoding="utf-8")
            (runtime / "changed.txt").write_text("runtime-secret-value\n", encoding="utf-8")
            (source / "source-only.txt").write_text("source-only-secret\n", encoding="utf-8")
            (runtime / "runtime-only.txt").write_text("runtime-only-secret\n", encoding="utf-8")

            payload = self._run_json(
                "maint",
                "source-runtime-sync",
                "--source-dir",
                str(source),
                "--runtime-dir",
                str(runtime),
            )

        Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(payload)
        data = payload["data"]
        self.assertEqual(data["surface"], "maintenance")
        self.assertEqual(data["subcommand"], "source-runtime-sync")
        self.assertEqual(data["write_performed"], False)
        self.assertEqual(data["source_only"], ["source-only.txt"])
        self.assertEqual(data["runtime_only"], ["runtime-only.txt"])
        self.assertEqual(data["changed_shared"], ["changed.txt"])
        self.assertEqual(data["same_count"], 1)
        serialized = json.dumps(payload, ensure_ascii=False)
        for secret in ["source-secret-value", "runtime-secret-value", "source-only-secret", "runtime-only-secret"]:
            self.assertNotIn(secret, serialized)
        self.assertEqual([step["step"] for step in payload["process"]], ["parse_args", "scan_source_runtime", "no_write", "emit_json"])

    def test_maint_doctor_returns_maintenance_surface(self) -> None:
        payload = self._run_json("maint", "doctor")

        self.assertEqual(payload["command"], "maint")
        self.assertEqual(payload["data"]["surface"], "maintenance")
        self.assertEqual(payload["data"]["subcommand"], "doctor")
        self.assertEqual(payload["data"]["write_performed"], False)
        self.assertEqual(payload["data"]["checks"]["command_registry_present"], True)

    def test_maint_source_runtime_diff_reports_paths_and_ignored_generated_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="flight-maint-diff.") as tmp:
            root = Path(tmp)
            source = root / "source"
            runtime = root / "runtime"
            source.mkdir()
            runtime.mkdir()
            (source / "same.txt").write_text("same\n", encoding="utf-8")
            (runtime / "same.txt").write_text("same\n", encoding="utf-8")
            (source / "changed.txt").write_text("source-secret-value\n", encoding="utf-8")
            (runtime / "changed.txt").write_text("runtime-secret-value\n", encoding="utf-8")
            (source / "__pycache__").mkdir()
            (source / "__pycache__" / "ignored.pyc").write_bytes(b"ignored")

            payload = self._run_json(
                "maint",
                "source-runtime",
                "diff",
                "--source-dir",
                str(source),
                "--runtime-dir",
                str(runtime),
            )

        data = payload["data"]
        self.assertEqual(data["surface"], "maintenance")
        self.assertEqual(data["subcommand"], "source-runtime diff")
        self.assertEqual(data["write_performed"], False)
        self.assertEqual(data["file_contents_included"], False)
        self.assertIn("__pycache__/", data["generated_ignored"])
        self.assertEqual(data["changed_shared"], ["changed.txt"])
        self.assertNotIn("source-secret-value", json.dumps(payload, ensure_ascii=False))

    def test_maint_refs_registry_check_reports_reference_ownership(self) -> None:
        payload = self._run_json("maint", "refs", "registry-check")

        data = payload["data"]
        self.assertEqual(data["surface"], "maintenance")
        self.assertEqual(data["subcommand"], "refs registry-check")
        self.assertEqual(data["write_performed"], False)
        self.assertEqual(data["ok"], True)
        self.assertIn("core/cli-contract.md", data["references_seen"])
        self.assertEqual(data["unregistered"], [])
        self.assertEqual(data["duplicate_owners"], [])
        self.assertEqual(data["broken_links"], [])
        self.assertEqual(data["broken_markdown_links"], [])

    def test_maint_refs_registry_check_detects_missing_markdown_link_targets(self) -> None:
        script_dir = str((ROOT / "scripts").resolve())
        old_path = list(sys.path)
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        try:
            maintenance = importlib.import_module("flight_calendar.maintenance")
        finally:
            sys.path[:] = old_path

        with tempfile.TemporaryDirectory(prefix="flight-maint-refs.") as tmp:
            skill_root = Path(tmp)
            references = skill_root / "references"
            references.mkdir()
            (references / "registry.md").write_text(
                "# Registry\n\n"
                "## Canonical owners\n\n"
                "- `owner.md` — owner.\n\n"
                "## Add/change rules\n",
                encoding="utf-8",
            )
            (references / "owner.md").write_text(
                "# Owner\n\nSee [missing](missing.md) and [ok](owner.md).\n",
                encoding="utf-8",
            )

            data = maintenance.refs_registry_check_report(skill_root)

        self.assertEqual(data["references_seen"], ["owner.md"])
        self.assertEqual(data["unregistered"], [])
        self.assertEqual(data["broken_links"], [])
        self.assertEqual(
            data["broken_markdown_links"],
            [{"source": "owner.md", "target": "missing.md"}],
        )
        self.assertEqual(data["ok"], False)

    def test_maint_clean_dry_run_never_deletes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="flight-maint-clean.") as tmp:
            root = Path(tmp)
            pycache = root / "__pycache__"
            pycache.mkdir()
            artifact = pycache / "module.pyc"
            artifact.write_bytes(b"cached")

            payload = self._run_json("maint", "clean", "--dry-run", "--target-dir", str(root))

            self.assertTrue(artifact.exists())

        data = payload["data"]
        self.assertEqual(data["surface"], "maintenance")
        self.assertEqual(data["subcommand"], "clean")
        self.assertEqual(data["dry_run"], True)
        self.assertEqual(data["deletions_performed"], False)
        self.assertTrue(any(candidate.endswith("__pycache__/") for candidate in data["candidates"]))

    def test_maint_audit_aggregates_read_only_reports(self) -> None:
        payload = self._run_json("maint", "audit")

        data = payload["data"]
        self.assertEqual(data["surface"], "maintenance")
        self.assertEqual(data["subcommand"], "audit")
        self.assertEqual(data["write_performed"], False)
        self.assertIn("contracts", data["reports"])
        self.assertIn("refs_registry", data["reports"])
        self.assertIn("timezone_catalog", data["reports"])

    def test_maint_timezone_catalog_inspect_reports_metadata_only(self) -> None:
        payload = self._run_json("maint", "timezone-catalog", "inspect")

        data = payload["data"]
        self.assertEqual(data["surface"], "maintenance")
        self.assertEqual(data["subcommand"], "timezone-catalog inspect")
        self.assertEqual(data["write_performed"], False)
        self.assertGreater(data["airports_count"], 0)
        self.assertGreater(data["timezones_count"], 0)
        self.assertTrue(data["sample_airports"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
