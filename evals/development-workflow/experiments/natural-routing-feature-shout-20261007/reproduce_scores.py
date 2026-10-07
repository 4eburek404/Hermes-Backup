#!/usr/bin/env python3
"""Re-extract natural-routing evidence and rescore offline; never launches Hermes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

BUNDLE = Path(__file__).resolve().parent
SOURCE = BUNDLE / "source"
EVAL = SOURCE / "evals" / "development-workflow"
sys.path.insert(0, str(SOURCE))
sys.path.insert(0, str(EVAL))
from consumer import DevelopmentWorkflowConsumer
from run_eval import build_case


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def canonicalize(value: Any, fixture: Path) -> Any:
    root = str(fixture.resolve())
    if isinstance(value, str):
        return value.replace(root, "$FIXTURE")
    if isinstance(value, list):
        return [canonicalize(item, fixture) for item in value]
    if isinstance(value, dict):
        return {key: canonicalize(item, fixture) for key, item in value.items()}
    return value


def event_refs(events: list[dict[str, Any]], facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pending: dict[str, list[int]] = {}
    paired: dict[int, int] = {}
    for i, event in enumerate(events):
        name = str(event.get("name", ""))
        if event.get("type") == "tool_use":
            pending.setdefault(name, []).append(i)
        elif event.get("type") == "tool_result" and pending.get(name):
            paired[pending[name].pop(0)] = i

    def event_hash(event: dict[str, Any]) -> str:
        raw = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()

    result = []
    for fact in facts:
        i = int(fact.get("index", -1))
        call = events[i] if 0 <= i < len(events) else None
        j = paired.get(i)
        reply = events[j] if j is not None else None
        result.append({
            "fact": fact,
            "event_index_zero_based": i if call else None,
            "call_tool": call.get("name") if call else None,
            "call_sha256": event_hash(call) if call else None,
            "result_index_zero_based": j,
            "result_sha256": event_hash(reply) if reply else None,
        })
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"refusing to overwrite non-empty output directory: {output}")
    output.mkdir(parents=True, exist_ok=True)

    manifest_path = EVAL / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cfg = manifest["scenarios"]["feature-shout"]
    consumer = DevelopmentWorkflowConsumer(EVAL, SOURCE, manifest, ["unused-hermes"])
    summaries = []
    input_hashes = {}

    for run_id in ("r1", "r2", "r3"):
        run_dir = BUNDLE / "runs" / run_id
        trace_path = run_dir / "raw_session.json"
        old_evidence_path = run_dir / "evidence.json"
        original_score_path = run_dir / "score.json"
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        old_evidence = json.loads(old_evidence_path.read_text(encoding="utf-8"))
        metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
        input_hashes[run_id] = {
            "raw_session_sha256": sha256(trace_path),
            "evidence_sha256": sha256(old_evidence_path),
            "original_score_sha256": sha256(original_score_path),
        }

        with tempfile.TemporaryDirectory(prefix=f"natural-routing-{run_id}-") as temp:
            fixture = Path(temp) / "fixture"
            fixture.mkdir()
            for relative, content in cfg["fixture_files"].items():
                target = fixture / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            evidence = consumer.reextract_workflow_evidence(old_evidence, trace_path, cfg, fixture)
            evidence = canonicalize(evidence, fixture)

        case = build_case(
            manifest,
            ["feature-shout"],
            ["candidate"],
            [{"model": metadata["model"], "provider": metadata["provider"]}],
            1,
            old_evidence["runtime_version"],
            "natural-routing",
        )
        rules = case["rules"]["feature-shout"]
        diagnostics = {
            dimension: consumer.evaluate_dimension_diagnostic(dimension, evidence, rules.get(dimension, {}))
            for dimension in ("outcome", "trajectory", "privacy")
        }
        scores = {key: value["status"] for key, value in diagnostics.items()}
        live_score = json.loads(original_score_path.read_text(encoding="utf-8"))["score"]
        if scores != live_score:
            raise SystemExit(f"offline score differs from recorded evaluator result for {run_id}: {scores} != {live_score}")

        events = consumer._session_events(trace)
        event_path = os.path.relpath(trace_path, output).replace(os.sep, "/")
        evidence["reassessment"] = {
            "method": "fresh extraction from sanitized captured raw session; previous workflow_events discarded",
            "source_raw_session": event_path,
            "source_raw_session_sha256": sha256(trace_path),
            "source_original_evidence_sha256": sha256(old_evidence_path),
            "source_original_score_sha256": sha256(original_score_path),
            "source_manifest_sha256": sha256(manifest_path),
            "evaluator_sha256": sha256(EVAL / "consumer.py"),
            "run_eval_sha256": sha256(EVAL / "run_eval.py"),
            "event_references": "event-refs.json",
            "execution": "offline only; no Hermes process, historical command, or model call",
        }
        run_output = output / run_id
        run_output.mkdir()
        dump(run_output / "evidence.json", evidence)
        dump(run_output / "score.json", {"score": scores, "diagnostics": diagnostics})
        dump(run_output / "event-refs.json", {
            "raw_session": event_path,
            "raw_session_sha256": sha256(trace_path),
            "references": event_refs(events, evidence.get("workflow_events", [])),
        })
        summaries.append({
            "run": run_id,
            "scores": scores,
            "reasons": {key: value["reason"] for key, value in diagnostics.items()},
            "workflow_event_count": len(evidence.get("workflow_events", [])),
            "source_raw_session": event_path,
        })

    dump(output / "summary.json", {"runs": summaries})
    dump(output / "source-checksums.json", {
        "manifest_sha256": sha256(manifest_path),
        "evaluator_sha256": sha256(EVAL / "consumer.py"),
        "run_eval_sha256": sha256(EVAL / "run_eval.py"),
        "inputs": input_hashes,
    })
    dump(output / "reproduction.json", {
        "script_sha256": sha256(Path(__file__)),
        "source": "bundle/source",
        "historical_commands_executed": False,
        "hermes_or_llm_runs": 0,
    })
    print(json.dumps(summaries, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
