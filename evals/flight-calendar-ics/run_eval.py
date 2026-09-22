#!/usr/bin/env python3
"""Run the minimal flight-calendar-ics agent eval."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from consumer import FlightCalendarIcsConsumer
from evals.harness.core import Harness


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest() -> dict:
    return json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))


def hermes_version(command: list[str]) -> str:
    proc = subprocess.run(
        [*command, "--version"],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Hermes runtime unavailable: exit={proc.returncode} stderr={proc.stderr.strip()}"
        )
    return proc.stdout.strip()


def build_case(
    manifest: dict,
    eval_root: Path,
    *,
    runtime_version: str,
) -> dict:
    models = list(manifest["models"])
    if len(models) != 3 or len({entry["provider"] for entry in models}) != 3:
        raise ValueError("minimal flight-calendar eval requires exactly three distinct providers")

    scenarios = list(manifest["scenarios"])
    if scenarios != ["url-success"]:
        raise ValueError("minimal flight-calendar eval requires only url-success")

    scenario = scenarios[0]
    cfg = manifest["scenarios"][scenario]
    return {
        "consumer": manifest["name"],
        "scenarios": scenarios,
        "models": models,
        "skill_versions": ["candidate"],
        "repeats": 1,
        "fixture_version": sha256(eval_root / cfg["fixture"]),
        "prompt_version": sha256(eval_root / cfg["prompt"]),
        "runtime_version": runtime_version,
        "mode": manifest.get("mode", "recorded"),
        "report": manifest.get("report", {}),
        "rules": {scenario: cfg.get("evaluation", {})},
    }


def main() -> int:
    manifest = load_manifest()
    hermes_command = [shutil.which("hermes") or "hermes"]
    runtime = hermes_version(hermes_command)
    case = build_case(manifest, ROOT, runtime_version=runtime)

    consumer = FlightCalendarIcsConsumer(
        ROOT,
        REPO_ROOT,
        manifest,
        hermes_command=hermes_command,
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    batch_dir = ROOT / "runs" / stamp
    batch = Harness(consumer).run(case, batch_dir)

    print(f"batch={batch_dir}")
    if batch.get("report_path"):
        print(f"report={batch['report_path']}")
    failed = [
        run
        for run in batch["runs"]
        if run["execution_status"] != "COMPLETED"
        or any(run["score"][name] != "PASS" for name in ("outcome", "trajectory", "privacy"))
    ]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
