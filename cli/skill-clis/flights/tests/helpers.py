from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
TEST_ENV = {"PYTHONPATH": str(PROJECT), "FLIGHTS_CATALOG_REFRESH": "never"}


class CliSubprocessMixin:
    def _rank(self, payload: dict, profile: str, *extra_args: str) -> dict:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "flights_cli",
                "--json",
                "route",
                "rank",
                "--profile",
                profile,
                "--input",
                "-",
                *extra_args,
            ],
            cwd=PROJECT,
            env=TEST_ENV,
            input=json.dumps(payload),
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return json.loads(proc.stdout)

    def _parse_raw(
        self,
        payload: dict,
        leg: str,
        origin: str | None,
        destination: str | None,
        *,
        direction: str = "outbound",
        date: str = "2026-07-19",
    ) -> dict:
        cmd = [
            sys.executable,
            "-m",
            "flights_cli",
            "--json",
            "results",
            "parse",
            "--direction",
            direction,
            "--leg",
            leg,
            "--date",
            date,
            "--currency",
            "RUB",
            "--input",
            "-",
        ]
        if origin is not None:
            cmd.extend(["--origin", origin])
        if destination is not None:
            cmd.extend(["--destination", destination])
        proc = subprocess.run(
            cmd,
            cwd=PROJECT,
            env=TEST_ENV,
            input=json.dumps(payload),
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return json.loads(proc.stdout)

    def _assemble(self, payload: dict, *extra_args: str) -> dict:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "flights_cli",
                "--json",
                "route",
                "assemble",
                "--profile",
                "safe",
                "--input",
                "-",
                *extra_args,
            ],
            cwd=PROJECT,
            env=TEST_ENV,
            input=json.dumps(payload),
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return json.loads(proc.stdout)
