from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EVAL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EVAL_ROOT.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_consumer() -> Any:
    consumer_path = EVAL_ROOT / "consumer.py"
    spec = importlib.util.spec_from_file_location("tutu_search_flights_consumer", consumer_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load consumer: {consumer_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = json.loads((EVAL_ROOT / "manifest.json").read_text(encoding="utf-8"))
    return module.TutuSearchFlightsConsumer(EVAL_ROOT, REPO_ROOT, manifest)


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return proc.stdout.strip()


def _runtime_version() -> str:
    proc = subprocess.run(["hermes", "--version"], check=True, text=True, capture_output=True)
    return (proc.stdout or proc.stderr).strip()


def _case(
    manifest: dict[str, Any],
    scenario: str | None = None,
    skill_version: str = "candidate",
) -> dict[str, Any]:
    scenario = scenario or next(iter(manifest["scenarios"]))
    if scenario not in manifest["scenarios"]:
        raise ValueError(f"unknown scenario: {scenario}")
    scenario_config = manifest["scenarios"][scenario]
    prompt_sha = _load_consumer().sha256(EVAL_ROOT / scenario_config["prompt"])
    fixture_sha = _load_consumer().sha256(EVAL_ROOT / scenario_config["fixture"])
    return {
        "consumer": manifest["name"],
        "mode": manifest["mode"],
        "skill_versions": [skill_version],
        "scenarios": [scenario],
        "models": manifest["models"],
        "repeats": int(manifest["repeats"]),
        "fixture_version": fixture_sha,
        "prompt_version": prompt_sha,
        "scenario_metadata": {
            scenario: {"fixture_version": fixture_sha, "prompt_version": prompt_sha}
        },
        "runtime_version": _runtime_version(),
        "report": manifest.get("report", {}),
        "rules": {scenario: scenario_config["evaluation"]},
    }


def main() -> int:
    manifest = json.loads((EVAL_ROOT / "manifest.json").read_text(encoding="utf-8"))
    scenarios = manifest["scenarios"]
    parser = argparse.ArgumentParser(description="Run one recorded Tutu agent scenario")
    parser.add_argument(
        "--scenario",
        choices=list(scenarios),
        default=next(iter(scenarios)),
        help="scenario to evaluate (default: the original Scenario 1)",
    )
    parser.add_argument(
        "--skill-version",
        choices=list(manifest["skill_versions"]),
        default="candidate",
        help="skill source to evaluate (default: candidate)",
    )
    parser.add_argument("--output-dir", type=Path, help="persistent evidence directory (default: ~/.hermes/evals/...)")
    args = parser.parse_args()

    if manifest["repeats"] != 1 or len(manifest["models"]) != 1:
        raise SystemExit("this consumer is intentionally limited to one scenario, model, and repeat")
    source = manifest["skill_versions"][args.skill_version]
    if args.skill_version == "candidate":
        _git("fetch", "origin", "new-tutu")
    resolved = _git("rev-parse", f"{source['ref']}^{{commit}}")
    pinned_commit = source.get("reference_commit")
    if pinned_commit and resolved != pinned_commit:
        raise SystemExit(
            f"candidate source moved: {resolved} != pinned {pinned_commit}; update the eval baseline deliberately"
        )
    baseline_source = manifest["skill_versions"].get("baseline")
    baseline_commit = None
    if baseline_source:
        baseline_commit = _git("rev-parse", f"{baseline_source['ref']}^{{commit}}")
        expected_baseline = baseline_source.get("reference_commit")
        if expected_baseline and baseline_commit != expected_baseline:
            raise SystemExit(
                f"baseline source moved: {baseline_commit} != pinned {expected_baseline}"
            )

    output_dir = args.output_dir or (
        Path.home()
        / ".hermes"
        / "evals"
        / "tutu-search-flights"
        / "runs"
        / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    os.chmod(output_dir, 0o700)
    os.umask(0o077)

    baseline = {
        "branch": _git("branch", "--show-current"),
        "head": _git("rev-parse", "HEAD"),
        "skill_version": args.skill_version,
        "evaluated_skill_commit": resolved,
        "pinned_baseline_commit": baseline_commit,
        "worktree_status": _git("status", "--porcelain=v1", "--untracked-files=all"),
    }
    (output_dir / "baseline.json").write_text(
        json.dumps(baseline, indent=2) + "\n", encoding="utf-8"
    )
    case = _case(manifest, args.scenario, args.skill_version)
    consumer = _load_consumer()
    consumer.manifest["skill_versions"][args.skill_version] = {
        **source,
        "ref": resolved,
        "reference_commit": resolved,
    }
    from evals.harness.core import Harness

    batch = Harness(consumer).run(case, output_dir)
    statuses = [run.get("execution_status") for run in batch["runs"]]
    print(json.dumps({
        "output_dir": str(output_dir),
        "baseline": baseline,
        "expected_run_ids": batch["expected_run_ids"],
        "executed_run_ids": batch["executed_run_ids"],
        "agent_execution_count": batch["agent_execution_count"],
        "execution_statuses": statuses,
        "scores": [run.get("score") for run in batch["runs"]],
        "evidence_paths": [run.get("evidence_path") for run in batch["runs"]],
        "report_path": batch.get("report_path"),
    }, indent=2, ensure_ascii=False))
    return 0 if statuses and all(status in {"COMPLETED", "AGENT_FAILURE"} for status in statuses) else 2


if __name__ == "__main__":
    raise SystemExit(main())
