"""Contract test for WP-3 (scripts restructure), WP-4 (legacy removal) and
WP-7 (single command truth table).

Assertions are filesystem/CLI based so they flip from RED (before) to GREEN
(after) without depending on intermediate import state.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
PACKAGE = SCRIPTS / "flight_calendar"
CARRIERS = PACKAGE / "carriers"
CLI = SCRIPTS / "flight_calendar_ics.py"

# timezone_catalog keeps a __main__ guard: it is the documented catalog
# (re)generator, invoked as `python3 -m flight_calendar.timezone_catalog`.
MAIN_GUARD_ALLOWED = {"timezone_catalog.py"}


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=SKILL_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
    )


class ScriptsStructureContract(unittest.TestCase):
    def test_scripts_root_contains_only_the_public_wrapper(self) -> None:
        root_py = sorted(p.name for p in SCRIPTS.glob("*.py"))
        self.assertEqual(root_py, ["flight_calendar_ics.py"])

    def test_package_owns_carriers_and_shared_modules(self) -> None:
        expected_carriers = {"__init__.py", "aeroflot.py", "ural.py", "utair.py", "redwings.py"}
        self.assertTrue(CARRIERS.is_dir(), "flight_calendar/carriers package must exist")
        self.assertEqual({p.name for p in CARRIERS.glob("*.py")}, expected_carriers)
        for module in ["common.py", "ics_render.py", "itinerary_contract.py", "timezone_catalog.py"]:
            self.assertTrue((PACKAGE / module).exists(), f"flight_calendar/{module} must exist")

    def test_no_main_guards_inside_package_except_catalog_generator(self) -> None:
        offenders = []
        for path in PACKAGE.rglob("*.py"):
            if "__pycache__" in path.parts or path.name in MAIN_GUARD_ALLOWED:
                continue
            if '__name__ == "__main__"' in path.read_text(encoding="utf-8"):
                offenders.append(path.relative_to(SKILL_ROOT).as_posix())
        self.assertEqual(offenders, [], f"package modules must not be direct-run entrypoints: {offenders}")


class LegacySurfaceRemovalContract(unittest.TestCase):
    def test_wrapper_is_thin_and_has_no_compat_shim(self) -> None:
        source = CLI.read_text(encoding="utf-8")
        self.assertNotIn("_CARRIER_HANDLER_NAMES", source)
        self.assertNotIn("Compatibility shim", source)
        self.assertLessEqual(len(source.splitlines()), 25)

    def test_root_legacy_commands_are_rejected(self) -> None:
        for legacy in ["aeroflot", "ural", "utair", "redwings", "make", "validate"]:
            with self.subTest(command=legacy):
                result = run_cli("--json", legacy)
                self.assertNotEqual(result.returncode, 0, f"root '{legacy}' must no longer exist")

    def test_doctor_reports_single_truth_table_without_legacy(self) -> None:
        result = run_cli("--json", "doctor")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)["data"]
        self.assertNotIn("legacy_scripts", data)
        self.assertEqual(data["commands"], ["doctor", "build", "diagnose", "maint"])
        self.assertNotIn("compatibility", data["command_registry"])


if __name__ == "__main__":
    unittest.main()
