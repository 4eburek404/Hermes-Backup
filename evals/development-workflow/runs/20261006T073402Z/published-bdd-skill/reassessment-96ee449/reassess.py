#!/usr/bin/env python3
"""Re-extract feature-shout workflow evidence from frozen JSONL traces; no Hermes/LLM."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUNDLE = HERE.parent
REPO = BUNDLE.parents[4]
EVAL_ROOT = REPO / "evals" / "development-workflow"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(EVAL_ROOT))
from consumer import DevelopmentWorkflowConsumer


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def event_ref_index(events: list[dict]) -> dict[int, int]:
    pending: dict[str, list[int]] = {}
    call_to_result: dict[int, int] = {}
    for i, event in enumerate(events):
        name = str(event.get("name", ""))
        if event.get("type") == "tool_use":
            pending.setdefault(name, []).append(i)
        elif event.get("type") == "tool_result" and pending.get(name):
            call_to_result[pending[name].pop(0)] = i
    return call_to_result


def rules_for(manifest: dict, cfg: dict) -> dict:
    trajectory = dict(manifest.get("evaluation", {}).get("trajectory", {}))
    trajectory.update({
        "requires_red": True,
        "mechanical": False,
        "preserved_probe_count": len(cfg.get("preserved_behavior_probes", [])),
        "current_probe_count": len(cfg.get("current_behavior_probes", [])),
        "review_only": False,
        "target_failure_signal": (cfg.get("target_check_signals") or [None])[0],
    })
    return {
        "outcome": {"require_repository_change": bool(cfg.get("require_repository_change", False)), "review_only": False},
        "trajectory": trajectory,
        "privacy": {},
    }


def main() -> int:
    manifest_path = BUNDLE / "source" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cfg = manifest["scenarios"]["feature-shout"]
    checksums_path = HERE / "input-checksums.json"
    pinned = json.loads(checksums_path.read_text(encoding="utf-8"))
    for relative, expected in pinned["inputs"].items():
        actual = sha256(BUNDLE / relative)
        if actual != expected:
            raise SystemExit(f"input checksum mismatch for {relative}: {actual} != {expected}")
    subject = DevelopmentWorkflowConsumer(EVAL_ROOT, REPO, manifest, ["unused-hermes"])
    scratch = HERE
    output_root = HERE / "runs"
    output_root.mkdir(parents=True, exist_ok=True)

    for run_name in ("r1", "r2", "r3"):
        source = BUNDLE / "runs" / run_name
        trace = source / "raw_stream.jsonl"
        old_evidence_path = source / "evidence.json"
        old_score_path = source / "score.json"
        old_evidence = json.loads(old_evidence_path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix=f"bdd-replay-{run_name}-", dir=scratch) as temporary:
            fixture = Path(temporary) / "fixture"
            fixture.mkdir()
            for relative, content in cfg["fixture_files"].items():
                target = fixture / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            evidence = subject.reextract_workflow_evidence(old_evidence, trace, cfg, fixture)

        # Re-open the immutable stream only to produce line-addressable references.
        events = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines() if line.strip()]
        pairs = event_ref_index(events)
        references = []
        for fact in evidence["workflow_events"]:
            call_index = int(fact.get("index", -1))
            call = events[call_index] if 0 <= call_index < len(events) else None
            result_index = pairs.get(call_index)
            result = events[result_index] if result_index is not None else None
            references.append({
                "fact": fact,
                "trace_call_line": call_index + 1 if call else None,
                "trace_result_line": result_index + 1 if result_index is not None else None,
                "call_event": call,
                "result_event": result,
            })

        rules = rules_for(manifest, cfg)
        scores = {
            dimension: subject.evaluate_dimension_diagnostic(dimension, evidence, rules[dimension])
            for dimension in ("outcome", "trajectory", "privacy")
        }
        output = output_root / run_name
        output.mkdir(parents=True, exist_ok=True)
        evidence["reassessment"] = {
            "method": "fresh raw_stream.jsonl extraction; original workflow_events/evidence were not reused",
            "source_raw_trace": f"../../../runs/{run_name}/raw_stream.jsonl",
            "source_raw_trace_sha256": sha256(trace),
            "source_original_evidence_sha256": sha256(old_evidence_path),
            "source_original_score_sha256": sha256(old_score_path),
            "source_manifest_sha256": sha256(manifest_path),
            "input_checksums_sha256": sha256(checksums_path),
            "evaluator_sha256": sha256(EVAL_ROOT / "consumer.py"),
            "event_references": f"event-refs.json",
            "execution": "offline only; no historical command, Hermes process, or model call",
        }
        (output / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (output / "score.json").write_text(json.dumps({
            "score": {key: value["status"] for key, value in scores.items()},
            "diagnostics": scores,
        }, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (output / "event-refs.json").write_text(json.dumps({
            "raw_trace": f"../../../runs/{run_name}/raw_stream.jsonl",
            "raw_trace_sha256": sha256(trace),
            "references": references,
        }, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"run": run_name,
                          "score": {key: value["status"] for key, value in scores.items()},
                          "reasons": {key: value["reason"] for key, value in scores.items()},
                          "workflow_event_count": len(evidence["workflow_events"])},
                         ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
