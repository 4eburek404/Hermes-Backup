#!/usr/bin/env python3
"""Re-score the published evidence deterministically; never launches Hermes."""
from __future__ import annotations

import json
import sys
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent
REPO = BUNDLE.parents[4]
EVAL_ROOT = REPO / "evals" / "development-workflow"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(EVAL_ROOT))
from consumer import DevelopmentWorkflowConsumer
from run_eval import build_case

manifest = json.loads((BUNDLE / "source" / "manifest.json").read_text())
consumer = DevelopmentWorkflowConsumer(EVAL_ROOT, REPO, manifest)
for run_dir in sorted((BUNDLE / "runs").iterdir()):
    if not run_dir.is_dir():
        continue
    evidence = json.loads((run_dir / "evidence.json").read_text())
    metadata = json.loads((run_dir / "metadata.json").read_text())
    case = build_case(
        manifest,
        [evidence["scenario"]],
        [evidence["skill_version"]],
        [{"model": evidence["model"], "provider": evidence["provider"]}],
        1,
        evidence["runtime_version"],
        "skill-behavior",
    )
    rules = case["rules"][evidence["scenario"]]
    scores = {
        dimension: consumer.evaluate_dimension_diagnostic(
            dimension, evidence, rules.get(dimension, {})
        )
        for dimension in ("outcome", "trajectory", "privacy")
    }
    saved = json.loads((run_dir / "score.json").read_text())["score"]
    actual = {key: value["status"] for key, value in scores.items()}
    if actual != saved:
        raise SystemExit(f"score mismatch for {run_dir.name}: {actual} != {saved}")
    print(json.dumps({"run": run_dir.name, "score": actual,
                      "reasons": {key: value["reason"] for key, value in scores.items()}},
                     ensure_ascii=False, sort_keys=True))
