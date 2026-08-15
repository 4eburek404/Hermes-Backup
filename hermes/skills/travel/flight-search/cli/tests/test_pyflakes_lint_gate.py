"""Lint gates for static checks that must pass in routine test runs."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

_CLI_ROOT = Path(__file__).resolve().parent.parent / "flights_cli"
_CLI_PACKAGE_ROOT = _CLI_ROOT.parent
_TESTS_ROOT = Path(__file__).resolve().parent


def _run_python_module(
    module: str,
    *args: str,
    cwd: Path | None = None,
) -> tuple[int, str, str]:
    commands = [
        [sys.executable, "-m", module, *args],
        ["python3", "-m", module, *args],
    ]
    last_code = 1
    last_output = ""
    last_command = ""
    for command in commands:
        proc = subprocess.run(
            command,
            capture_output=True,
            cwd=cwd,
            text=True,
        )
        output = (proc.stdout + proc.stderr).strip()
        rendered_command = " ".join(command)
        if cwd is not None:
            rendered_command = f"(cd {cwd} && {rendered_command})"
        if f"No module named {module}" not in output:
            return proc.returncode, output, rendered_command
        last_code = proc.returncode
        last_output = output
        last_command = rendered_command
    return last_code, last_output, last_command


def _run_pyflakes() -> tuple[int, str, str]:
    """Run pyflakes on the flights_cli package; return (exit_code, combined_output)."""
    return _run_python_module("pyflakes", str(_CLI_ROOT))


def _run_ruff_check() -> tuple[int, str, str]:
    """Run ruff check on source and tests; return (exit_code, combined_output)."""
    return _run_python_module(
        "ruff",
        "check",
        str(_CLI_ROOT),
        str(_TESTS_ROOT),
    )


def _run_vulture() -> tuple[int, str, str]:
    """Run vulture on the flights_cli package; return (exit_code, combined_output)."""
    return _run_python_module(
        "vulture",
        "flights_cli",
        "--min-confidence",
        "80",
        cwd=_CLI_PACKAGE_ROOT,
    )


class PyflakesLintGateTests(unittest.TestCase):
    def test_flights_cli_has_no_pyflakes_warnings(self) -> None:
        """Fail if pyflakes reports any unused imports or undefined names in flights_cli/."""
        code, output, command = _run_pyflakes()
        if "No module named pyflakes" in output:
            self.skipTest("pyflakes is not installed")
        self.assertEqual(
            code,
            0,
            f"{command} found {len(output.splitlines())} warning(s) in flights_cli/:\n{output}",
        )


class RuffLintGateTests(unittest.TestCase):
    def test_ruff_check_passes_for_source_and_tests(self) -> None:
        """Fail if ruff reports lint violations in flights_cli/ or tests/."""
        code, output, command = _run_ruff_check()
        self.assertNotIn(
            "No module named ruff",
            output,
            "ruff is required for the lint gate; install the dev extra with `pip install -e '.[dev]'`.",
        )
        self.assertEqual(
            code,
            0,
            f"{command} found ruff violations in flights_cli/ or tests/:\n{output}",
        )


class VultureLintGateTests(unittest.TestCase):
    def test_vulture_has_no_dead_code_candidates(self) -> None:
        """Fail if vulture reports high-confidence dead code candidates in flights_cli/."""
        code, output, command = _run_vulture()
        self.assertNotIn(
            "No module named vulture",
            output,
            "vulture is required for the lint gate; install the dev extra with `pip install -e '.[dev]'`.",
        )
        self.assertEqual(
            code,
            0,
            f"{command} found vulture dead-code candidates in flights_cli/:\n{output}",
        )


if __name__ == "__main__":
    unittest.main()
