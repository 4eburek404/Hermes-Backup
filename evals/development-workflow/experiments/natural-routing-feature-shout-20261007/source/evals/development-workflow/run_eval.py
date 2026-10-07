#!/usr/bin/env python3
"""Run the BDD development-workflow agent evaluation."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from consumer import DevelopmentWorkflowConsumer, canonical_sha256, fixture_fingerprint_payload
from evals.harness.core import Harness


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
            f"Hermes runtime unavailable: exit={proc.returncode} "
            f"stderr={proc.stderr.strip()}"
        )
    return proc.stdout.strip()


def build_case(
    manifest: dict,
    scenarios: list[str],
    versions: list[str],
    models: list[dict[str, str]],
    repeats: int,
    runtime_version: str,
    evaluation_mode: str = "skill-behavior",
) -> dict:
    scenario_metadata: dict[str, dict[str, str]] = {}
    rules: dict[str, dict] = {}
    global_trajectory = manifest.get("evaluation", {}).get("trajectory", {})

    for scenario in scenarios:
        cfg = manifest["scenarios"][scenario]
        scenario_metadata[scenario] = {
            "fixture_version": canonical_sha256(fixture_fingerprint_payload(cfg)),
            "prompt_version": canonical_sha256(cfg["prompt"]),
        }
        rules[scenario] = {
            "outcome": {
                "require_repository_change": bool(
                    cfg.get("require_repository_change", False)
                ),
                "review_only": bool(cfg.get("review_only", False)),
            },
            "trajectory": {
                **dict(global_trajectory),
                "requires_red": scenario not in {"refactor-preserve"} and not cfg.get("mechanical", False),
                "mechanical": bool(cfg.get("mechanical", False)),
                "preserved_probe_count": len(cfg.get("preserved_behavior_probes", [])),
                "current_probe_count": len(cfg.get("current_behavior_probes", [])),
                "review_only": bool(cfg.get("review_only", False)),
                "target_failure_signal": (cfg.get("target_check_signals") or [None])[0],
            },
        }

    return {
        "consumer": manifest["name"],
        "scenarios": scenarios,
        "models": models,
        "skill_versions": versions,
        "repeats": repeats,
        "fixture_version": "scenario-specific",
        "prompt_version": "scenario-specific",
        "runtime_version": runtime_version,
        "mode": evaluation_mode,
        "scenario_metadata": scenario_metadata,
        "rules": rules,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario")
    parser.add_argument("--version", choices=("baseline", "candidate"))
    parser.add_argument("--repeat", type=int, default=None)
    parser.add_argument("--model")
    parser.add_argument("--provider")
    parser.add_argument(
        "--mode",
        choices=("skill-behavior", "natural-routing"),
        default="skill-behavior",
    )
    args = parser.parse_args()

    manifest = load_manifest()
    configured = list(manifest["scenarios"])
    if args.scenario is not None and args.scenario not in configured:
        parser.error("--scenario must be one of: " + ", ".join(configured))
    scenarios = [args.scenario] if args.scenario else configured

    if bool(args.model) != bool(args.provider):
        parser.error("--model and --provider must be supplied together")
    models = (
        [{"model": args.model, "provider": args.provider}]
        if args.model
        else list(manifest["models"])
    )
    versions = [args.version] if args.version else list(manifest["skill_versions"])
    repeats = (
        args.repeat
        if args.repeat is not None
        else int(manifest.get("repeats", 1))
    )
    if repeats < 1:
        parser.error("--repeat must be >= 1")

    hermes_command = [shutil.which("hermes") or "hermes"]
    runtime = hermes_version(hermes_command)
    consumer = DevelopmentWorkflowConsumer(
        ROOT,
        REPO_ROOT,
        manifest,
        hermes_command=hermes_command,
    )
    case = build_case(
        manifest,
        scenarios,
        versions,
        models,
        repeats,
        runtime,
        args.mode,
    )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    batch_dir = ROOT / "runs" / stamp
    batch = Harness(consumer).run(case, batch_dir)

    routing_diagnostics = []
    if args.mode == "natural-routing":
        for run in batch["runs"]:
            if run["scenario"] != "feature-shout":
                continue
            evidence_path = Path(run["evidence_path"])
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            routing = consumer.routing_diagnostics(evidence)
            (evidence_path.parent / "routing.json").write_text(
                json.dumps(routing, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            routing_diagnostics.append((run["run_id"], routing))

    if routing_diagnostics:
        report_path = batch_dir / "report.md"
        with report_path.open("a", encoding="utf-8") as report:
            report.write("\n## NATURAL ROUTING\n\n")
            for run_id, routing in routing_diagnostics:
                before = [
                    str(item.get("skill", ""))
                    for item in routing["skill_reads_before_production"]
                ]
                observed = ", ".join(before) if before else "none observed"
                report.write(
                    f"- `{run_id}`: skills read before first production change: "
                    f"{observed}\n"
                )

    print(f"batch={batch_dir}")
    if routing_diagnostics:
        print("routing=" + json.dumps(routing_diagnostics, ensure_ascii=False))
    bad = [
        run
        for run in batch["runs"]
        if run.get("execution_status") != "COMPLETED"
        or run.get("score", {}).get("outcome") != "PASS"
        or run.get("score", {}).get("trajectory") != "PASS"
    ]
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
