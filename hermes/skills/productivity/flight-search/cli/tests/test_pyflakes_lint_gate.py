"""Lint gate: pyflakes must pass with zero warnings on flights_cli/."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_CLI_ROOT = Path(__file__).resolve().parent.parent / "flights_cli"


def _run_pyflakes() -> tuple[int, str]:
    """Run pyflakes on the flights_cli package; return (exit_code, combined_output)."""
    proc = subprocess.run(
        [sys.executable, "-m", "pyflakes", str(_CLI_ROOT)],
        capture_output=True,
        text=True,
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def test_flights_cli_has_no_pyflakes_warnings() -> None:
    """Fail if pyflakes reports any unused imports or undefined names in flights_cli/."""
    code, output = _run_pyflakes()
    if code != 0:
        pytest.fail(
            f"pyflakes found {len(output.splitlines())} warning(s) in flights_cli/:\n{output}"
        )