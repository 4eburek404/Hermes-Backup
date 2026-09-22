#!/usr/bin/env python3
"""Run github-code-review through the common agent-eval harness."""
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
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from consumer import GithubCodeReviewConsumer
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
    scenarios: list[str],
    versions: list[str],
    models: list[dict[str, str]],
    repeats: int,
    runtime_version: str,
) -> dict:
    scenario_metadata = {}
    rules = {}
    for scenario in scenarios:
        cfg = manifest["scenarios"][scenario]
        scenario_metadata[scenario] = {
            "fixture_version": (
                f'{cfg["fixture_base_sha"]}:{cfg["fixture_review_commit_sha"]}'
            ),
            "prompt_version": sha256(ROOT / cfg["prompt"]),
        }
        rules[scenario] = cfg.get("evaluation", {})

    return {
        "consumer": manifest["name"],
        "scenarios": scenarios,
        "models": models,
        "skill_versions": versions,
        "repeats": repeats,
        "fixture_version": "scenario-specific",
        "prompt_version": "scenario-specific",
        "runtime_version": runtime_version,
        "mode": manifest.get("mode", "recorded"),
        "scenario_metadata": scenario_metadata,
        "rules": rules,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--version", choices=("baseline", "candidate"))
    parser.add_argument(
        "--runs",
        type=int,
        default=None,
        help="number of configured scenarios to run; default: all",
    )
    parser.add_argument("--repeat", type=int, default=None)
    parser.add_argument("--model")
    parser.add_argument("--provider")
    args = parser.parse_args()

    manifest = load_manifest()
    configured_scenarios = list(manifest["scenarios"])
    count = args.runs if args.runs is not None else len(configured_scenarios)
    if count < 1 or count > len(configured_scenarios):
        parser.error(f"--runs must be between 1 and {len(configured_scenarios)}")
    scenarios = configured_scenarios[:count]

    hermes_command = [shutil.which("hermes") or "hermes"]
    consumer = GithubCodeReviewConsumer(
        ROOT,
        REPO_ROOT,
        manifest,
        hermes_command=hermes_command,
    )

    if args.prepare_only:
        output = {scenario: consumer.inspect_fixture(scenario) for scenario in scenarios}
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0

    if bool(args.model) != bool(args.provider):
        parser.error("--model and --provider must be supplied together")
    models = (
        [{"model": args.model, "provider": args.provider}]
        if args.model
        else list(manifest["models"])
    )
    versions = (
        [args.version]
        if args.version
        else list(manifest["skill_versions"])
    )
    repeats = args.repeat if args.repeat is not None else int(manifest.get("repeats", 1))
    if repeats < 1:
        parser.error("--repeat must be >= 1")

    runtime = hermes_version(hermes_command)
    case = build_case(manifest, scenarios, versions, models, repeats, runtime)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    batch_dir = ROOT / "runs" / stamp
    harness = Harness(consumer)
    batch = harness.run(case, batch_dir)

    print(f"batch={batch_dir}")
    bad_execution = [
        run for run in batch["runs"] if run["execution_status"] != "COMPLETED"
    ]
    return 1 if bad_execution else 0


if __name__ == "__main__":
    raise SystemExit(main())
