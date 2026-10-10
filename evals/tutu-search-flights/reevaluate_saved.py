#!/usr/bin/env python3
"""Offline reassessment of saved Tutu traces through the shared harness."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

EVAL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EVAL_ROOT.parents[1]
DEFAULT_SOURCE = Path.home() / ".hermes/evals/tutu-search-flights/runs/20261009-comparison"
DEFAULT_OUTPUT = EVAL_ROOT / "reassessments/evaluator-v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_consumer() -> Any:
    sys.path.insert(0, str(REPO_ROOT))
    spec = importlib.util.spec_from_file_location("tutu_search_flights_consumer", EVAL_ROOT / "consumer.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Tutu evaluator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = json.loads((EVAL_ROOT / "manifest.json").read_text(encoding="utf-8"))
    return module.TutuSearchFlightsConsumer(EVAL_ROOT, REPO_ROOT, manifest, hermes_command=["not-used"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"refusing to overwrite non-empty output directory: {output}")

    sys.path.insert(0, str(REPO_ROOT))
    from evals.harness.core import Harness, evaluate_dimension_details

    consumer = load_consumer()
    evaluator_version = sha256(EVAL_ROOT / "consumer.py")
    manifest = consumer.manifest
    output.mkdir(parents=True, exist_ok=True)
    batch_runs = []
    refs_by_run = {}
    original_scores = {}
    scenarios = manifest["scenarios"]
    run_dirs = sorted(source.glob("*/*/*--r1"))
    if len(run_dirs) != 6:
        raise SystemExit(f"expected exactly six saved traces, found {len(run_dirs)}")

    for run_dir in run_dirs:
        evidence_path = run_dir / "evidence.json"
        score_path = run_dir / "score.json"
        trace_path = run_dir / "raw_stream.jsonl"
        boundary_path = run_dir / "mcp-boundary.jsonl"
        if not all(path.is_file() for path in (evidence_path, score_path, trace_path)):
            raise SystemExit(f"required saved evidence missing from {run_dir}")
        old_evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        original_score = json.loads(score_path.read_text(encoding="utf-8"))
        evidence = dict(old_evidence)
        raw = trace_path.read_text(encoding="utf-8")
        summary = consumer._event_summary(raw)
        for key in ("tool_uses", "tool_names", "terminal_commands", "terminal_invocations", "final_event_index", "final_answer"):
            evidence[key] = summary[key]
        evidence["raw_stream_path"] = str(trace_path)
        evidence["raw_stderr_path"] = str(run_dir / "raw_stderr.txt")
        evidence["raw_final_answer_path"] = str(run_dir / "raw_final_answer.txt")
        if boundary_path.is_file():
            evidence["mcp_boundary_requests"] = [
                json.loads(line) for line in boundary_path.read_text(encoding="utf-8").splitlines() if line.strip()
            ]
        calls = [item for item in evidence.get("mcp_boundary_requests", []) if item.get("jsonrpc_method") == "tools/call"]
        served = [item for item in calls if item.get("replay_status") == "fixture-served"]
        evidence["actual_search_arguments"] = served[0].get("arguments") if len(served) == 1 else None

        scenario = str(evidence["scenario"])
        rules = scenarios[scenario]["evaluation"]
        case_evidence = output / "_work" / f"{run_dir.name}.json"
        write_json(case_evidence, evidence)
        reevaluated = Harness(consumer).reevaluate(case_evidence, rules)
        diagnostics = evaluate_dimension_details(consumer, evidence, rules)
        score = {key: value["status"] for key, value in diagnostics.items()}
        derived_evidence = {
            **evidence,
            "diagnostics": diagnostics,
            "reevaluation": {
                "method": "shared evals.harness.core.Harness.reevaluate; event facts re-extracted from saved raw_stream.jsonl",
                "execution": "offline only; no Hermes process, agent, semantic-judge call, or Tutu request",
                "source_raw_trace": os.path.relpath(trace_path, output).replace(os.sep, "/"),
                "source_raw_trace_sha256": sha256(trace_path),
                "source_evidence_sha256": sha256(evidence_path),
                "source_score_sha256": sha256(score_path),
                "source_boundary_sha256": sha256(boundary_path) if boundary_path.is_file() else None,
                "evaluator_version_sha256": evaluator_version,
            },
        }
        public_trace_dir = output / "raw-traces"
        public_trace_dir.mkdir(exist_ok=True)
        published_trace = public_trace_dir / f"{run_dir.name}.jsonl"
        published_trace.write_bytes(trace_path.read_bytes())
        published_boundary = None
        if boundary_path.is_file():
            published_boundary = public_trace_dir / f"{run_dir.name}.mcp-boundary.jsonl"
            published_boundary.write_bytes(boundary_path.read_bytes())
        relative_trace = os.path.relpath(published_trace, output).replace(os.sep, "/")
        refs = {
            "source_raw_trace": relative_trace,
            "source_raw_trace_sha256": sha256(trace_path),
            "published_copy_sha256": sha256(published_trace),
            "published_copy_byte_identical": trace_path.read_bytes() == published_trace.read_bytes(),
            "event_references": [
                {
                    "index": index,
                    "line": index + 1,
                    "sha256": hashlib.sha256(line).hexdigest(),
                    "event_type": event.get("type"),
                    "name": event.get("name"),
                }
                for index, (line, event) in enumerate(
                    ( (line, json.loads(line)) for line in trace_path.read_bytes().splitlines() if line.strip() )
                )
                if event.get("type") in {"tool_use", "tool_result", "result"}
            ],
            "boundary_file": os.path.relpath(published_boundary, output).replace(os.sep, "/") if published_boundary else None,
            "boundary_sha256": sha256(boundary_path) if boundary_path.is_file() else None,
            "published_boundary_byte_identical": (
                boundary_path.read_bytes() == published_boundary.read_bytes()
                if published_boundary else None
            ),
        }
        target = output / run_dir.name
        target.mkdir(parents=True)
        write_json(target / "evidence.json", derived_evidence)
        write_json(target / "score.json", {
            "evaluator_version_sha256": evaluator_version,
            "original": original_score,
            "reevaluated": {"score": score, "diagnostics": diagnostics, "harness_result": reevaluated},
            "source_evidence": os.path.relpath(evidence_path, output).replace(os.sep, "/"),
            "source_score": os.path.relpath(score_path, output).replace(os.sep, "/"),
        })
        write_json(target / "event-refs.json", refs)
        original_scores[run_dir.name] = original_score
        refs_by_run[run_dir.name] = refs
        batch_runs.append({**evidence, "score": score, "diagnostics": diagnostics,
                           "evidence_path": str(target / "evidence.json"), "score_path": str(target / "score.json"),
                           "evaluator_provenance": {"evaluator": "tutu-search-flights", "version_sha256": evaluator_version}})

    batch = {
        "consumer": manifest["name"],
        "reevaluation": True,
        "execution_mode": "offline_saved_traces",
        "agent_execution_count": 0,
        "evaluator_version_sha256": evaluator_version,
        "original_scores_preserved": True,
        "expected_run_ids": [run["run_id"] for run in batch_runs],
        "executed_run_ids": [run["run_id"] for run in batch_runs],
        "runs": batch_runs,
    }
    write_json(output / "batch_manifest.json", batch)
    write_json(output / "source-manifest.json", {
        "source_directory": str(source),
        "evaluator_version_sha256": evaluator_version,
        "source_runs": {
            run_dir.name: {
                "raw_trace": os.path.relpath(run_dir / "raw_stream.jsonl", output).replace(os.sep, "/"),
                "raw_trace_sha256": sha256(run_dir / "raw_stream.jsonl"),
                "evidence_sha256": sha256(run_dir / "evidence.json"),
                "score_sha256": sha256(run_dir / "score.json"),
            } for run_dir in run_dirs
        },
        "agent_execution_count": 0,
        "historical_raw_traces_modified": False,
    })
    shutil_work = output / "_work"
    for path in shutil_work.glob("*.json"):
        path.unlink()
    shutil_work.rmdir()
    print(json.dumps({"output": str(output), "evaluator_version_sha256": evaluator_version,
                      "agent_execution_count": 0,
                      "runs": [{"run_id": run["run_id"], "score": run["score"], "diagnostics": run["diagnostics"]} for run in batch_runs]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
