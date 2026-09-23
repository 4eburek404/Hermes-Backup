#!/usr/bin/env python3
"""Run or re-evaluate the flight-calendar-ics agent eval."""
from __future__ import annotations

import argparse
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

from consumer import EvaluatorPreflightError, FlightCalendarIcsConsumer
from evals.harness.core import Harness, build_matrix
from evals.harness.report import format_run_duration


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest() -> dict:
    return json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))


def hermes_version(command: list[str]) -> str:
    proc = subprocess.run([*command, "--version"], text=True, capture_output=True, check=False)
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
    selected_scenarios: list[str] | None = None,
) -> dict:
    models = list(manifest["models"])
    if len(models) != 3 or len({entry["provider"] for entry in models}) != 3:
        raise ValueError("minimal flight-calendar eval requires exactly three distinct providers")

    scenarios = selected_scenarios or list(manifest["scenarios"])
    unknown = [name for name in scenarios if name not in manifest["scenarios"]]
    if unknown:
        raise ValueError(f"unknown scenario(s): {', '.join(unknown)}")
    if not scenarios:
        raise ValueError("at least one scenario is required")

    metadata = {
        scenario: {
            "fixture_version": sha256(eval_root / manifest["scenarios"][scenario]["fixture"]),
            "prompt_version": sha256(eval_root / manifest["scenarios"][scenario]["prompt"]),
        }
        for scenario in scenarios
    }
    first = metadata[scenarios[0]]
    return {
        "consumer": manifest["name"],
        "scenarios": scenarios,
        "models": models,
        "skill_versions": ["candidate"],
        "repeats": 1,
        "fixture_version": first["fixture_version"],
        "prompt_version": first["prompt_version"],
        "scenario_metadata": metadata,
        "runtime_version": runtime_version,
        "mode": manifest.get("mode", "recorded"),
        "report": manifest.get("report", {}),
        "rules": {
            scenario: manifest["scenarios"][scenario].get("evaluation", {})
            for scenario in scenarios
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenarios",
        help="run only this configured scenario; repeat for multiple scenarios",
    )
    parser.add_argument(
        "--reevaluate",
        type=Path,
        help="re-evaluate an existing batch from saved evidence without launching Hermes",
    )
    return parser


def _result_label(run: dict) -> str:
    if run.get("execution_status") in {
        "RUNTIME_FAILURE",
        "SETUP_FAILURE",
        "FIXTURE_FAILURE",
    }:
        return run["execution_status"]
    score = run.get("score") or {}
    if any(value in {"FAIL", "ERROR"} for value in score.values()):
        return "FAIL"
    return "PASS"


def _progress(event: dict) -> None:
    spec = event["spec"]
    prefix = f"[{event['index']}/{event['total']}]"
    label = f"{spec.model} / {spec.scenario}"
    if event["phase"] == "start":
        print(f"{prefix} START  {label}", flush=True)
        return
    run = event["run"]
    duration = format_run_duration((run.get("metrics") or {}).get("duration_seconds"))
    result = _result_label(run)
    diagnostics = run.get("diagnostics") or {}
    reason = next(
        (
            detail.get("reason")
            for detail in diagnostics.values()
            if isinstance(detail, dict) and detail.get("status") not in {None, "PASS"} and detail.get("reason")
        ),
        None,
    )
    suffix = f" — {reason}" if reason else ""
    print(f"{prefix} {result:<9} {duration}{suffix}", flush=True)


def _write_preflight_failure(batch_dir: Path, error: str, scenarios: list[str]) -> None:
    batch_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "EVALUATOR_PREFLIGHT_FAILURE",
        "agent_execution_count": 0,
        "scenarios": scenarios,
        "reason": error,
    }
    (batch_dir / "preflight.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (batch_dir / "report.md").write_text(
        "# EVAL REPORT\n\n## STATUS\n\n"
        "Result: EVALUATOR_PREFLIGHT_FAILURE\n"
        "Runs: 0/0 PASS\n\n"
        f"Reason: {error}\n",
        encoding="utf-8",
    )


def run_reevaluation(
    source_batch: Path,
    manifest: dict,
    consumer: FlightCalendarIcsConsumer,
) -> int:
    source_manifest = json.loads((source_batch / "batch_manifest.json").read_text(encoding="utf-8"))
    scenarios: list[str] = []
    for run in source_manifest.get("runs", []):
        scenario = str(run.get("scenario", ""))
        if scenario not in scenarios:
            scenarios.append(scenario)
    runtime = str((source_manifest.get("runs") or [{}])[0].get("runtime_version", "reevaluation"))
    case = build_case(manifest, ROOT, runtime_version=runtime, selected_scenarios=scenarios)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = ROOT / "reevaluations" / stamp
    batch = consumer.reevaluate_batch(source_batch, case, output_dir)
    print(f"reevaluation={output_dir}")
    print(f"report={batch['report_path']}")
    print(f"agent_execution_count={batch['agent_execution_count']}")
    return 0 if all(_result_label(run) == "PASS" for run in batch["runs"]) else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    manifest = load_manifest()
    hermes_command = [shutil.which("hermes") or "hermes"]
    consumer = FlightCalendarIcsConsumer(ROOT, REPO_ROOT, manifest, hermes_command=hermes_command)

    if args.reevaluate is not None:
        return run_reevaluation(args.reevaluate, manifest, consumer)

    runtime = hermes_version(hermes_command)
    case = build_case(
        manifest,
        ROOT,
        runtime_version=runtime,
        selected_scenarios=args.scenarios,
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    batch_dir = ROOT / "runs" / stamp
    specs = build_matrix(case)
    print(f"Batch: {batch_dir}", flush=True)
    print(f"Matrix: {len(specs)} runs", flush=True)
    try:
        preflight = consumer.preflight(case["scenarios"])
    except EvaluatorPreflightError as exc:
        _write_preflight_failure(batch_dir, str(exc), case["scenarios"])
        print(f"EVALUATOR_PREFLIGHT_FAILURE: {exc}", flush=True)
        return 2

    batch = Harness(consumer).run(case, batch_dir, progress=_progress)
    batch["preflight"] = preflight
    (batch_dir / "batch_manifest.json").write_text(
        json.dumps(batch, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"batch={batch_dir}")
    if batch.get("report_path"):
        print(f"report={batch['report_path']}")
    failed = [run for run in batch["runs"] if _result_label(run) != "PASS"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
