from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SPECS = ROOT / "specs"
SPEC_FILES = (
    "url_cli_spec.py",
    "itinerary_input_spec.py",
    "aeroflot_spec.py",
    "utair_spec.py",
    "passenger_display_spec.py",
)


class StandaloneSpecsOfflineTests(unittest.TestCase):
    def test_all_standalone_specs_are_isolated_from_live_network(self) -> None:
        env = {
            **os.environ,
            "PYTHONPATH": os.pathsep.join((str(SPECS), str(SCRIPTS))),
        }
        env.pop("FLIGHT_CALENDAR_CACHE_DIR", None)

        for spec_name in SPEC_FILES:
            with self.subTest(spec=spec_name):
                result = subprocess.run(
                    [sys.executable, str(SPECS / spec_name)],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    env=env,
                    timeout=60,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    f"{spec_name}:\nstdout={result.stdout}\nstderr={result.stderr}",
                )


if __name__ == "__main__":
    unittest.main()
