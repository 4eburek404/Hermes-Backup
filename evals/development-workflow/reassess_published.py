#!/usr/bin/env python3
"""Offline re-extraction of the published feature-shout traces."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPT = Path(__file__).resolve()
DEFAULT_REPO = SCRIPT.parents[2]
DEFAULT_BUNDLE = DEFAULT_REPO / "evals/development-workflow/runs/20261006T073402Z/published-bdd-skill"
DEFAULT_OUTPUT = DEFAULT_REPO / "evals/development-workflow/reassessments/pytest-evidence-v1"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def event_pairs(events: list[dict[str, Any]]) -> dict[int, int]:
    pending: dict[str, list[int]] = {}
    paired: dict[int, int] = {}
    for index, event in enumerate(events):
        name = str(event.get("name", ""))
        if event.get("type") == "tool_use":
            pending.setdefault(name, []).append(index)
        elif event.get("type") == "tool_result" and pending.get(name):
            paired[pending[name].pop(0)] = index
    return paired


def rules_for(manifest: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
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


def canonicalize(value: Any, fixture: Path) -> Any:
    root = str(fixture.resolve())
    if isinstance(value, str):
        return value.replace(root, "$FIXTURE")
    if isinstance(value, list):
        return [canonicalize(item, fixture) for item in value]
    if isinstance(value, dict):
        return {key: canonicalize(item, fixture) for key, item in value.items()}
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    bundle = args.bundle.resolve()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"refusing to overwrite non-empty output directory: {output}")

    checksum_file = bundle / "reassessment-96ee449/input-checksums.json"
    pinned = json.loads(checksum_file.read_text(encoding="utf-8"))
    source_hashes: dict[str, str] = {}
    for relative, expected in pinned["inputs"].items():
        actual = sha256(bundle / relative)
        if actual != expected:
            raise SystemExit(f"input checksum mismatch for {relative}: {actual} != {expected}")
        source_hashes[relative] = actual

    manifest_path = bundle / "source/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cfg = manifest["scenarios"]["feature-shout"]
    eval_root = repo / "evals/development-workflow"
    sys.path.insert(0, str(repo))
    sys.path.insert(0, str(eval_root))
    from consumer import DevelopmentWorkflowConsumer

    subject = DevelopmentWorkflowConsumer(eval_root, repo, manifest, ["unused-hermes"])
    rules = rules_for(manifest, cfg)
    output.mkdir(parents=True, exist_ok=True)
    summaries = []
    for run_name in ("r1", "r2", "r3"):
        source = bundle / "runs" / run_name
        trace = source / "raw_stream.jsonl"
        evidence_path = source / "evidence.json"
        score_path = source / "score.json"
        old_evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix=f"published-bdd-{run_name}-") as temporary:
            fixture = Path(temporary) / "fixture"
            fixture.mkdir()
            for relative, content in cfg["fixture_files"].items():
                target = fixture / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            evidence = subject.reextract_workflow_evidence(old_evidence, trace, cfg, fixture)
            evidence = canonicalize(evidence, fixture)

        raw_lines = trace.read_bytes().splitlines()
        events = [json.loads(line) for line in raw_lines if line.strip()]
        pairs = event_pairs(events)
        references = []
        for fact in evidence["workflow_events"]:
            call_index = int(fact.get("index", -1))
            call = events[call_index] if 0 <= call_index < len(events) else None
            result_index = pairs.get(call_index)
            result = events[result_index] if result_index is not None else None
            references.append({
                "fact": fact,
                "call_line": call_index + 1 if call else None,
                "call_tool": call.get("name") if call else None,
                "call_sha256": sha256_bytes(raw_lines[call_index]) if call else None,
                "result_line": result_index + 1 if result_index is not None else None,
                "result_sha256": sha256_bytes(raw_lines[result_index]) if result_index is not None else None,
            })

        scores = {
            dimension: subject.evaluate_dimension_diagnostic(dimension, evidence, rules[dimension])
            for dimension in ("outcome", "trajectory", "privacy")
        }
        source_ref = os.path.relpath(trace, output).replace(os.sep, "/")
        evidence["reassessment"] = {
            "method": "fresh extraction from the frozen raw stream; prior workflow_events were discarded",
            "source_raw_trace": source_ref,
            "source_raw_trace_sha256": sha256(trace),
            "source_original_evidence_sha256": sha256(evidence_path),
            "source_original_score_sha256": sha256(score_path),
            "source_manifest_sha256": sha256(manifest_path),
            "input_checksums_sha256": sha256(checksum_file),
            "evaluator_sha256": sha256(eval_root / "consumer.py"),
            "event_references": "event-refs.json",
            "execution": "offline only; no historical commands, Hermes process, or model call",
        }
        run_output = output / run_name
        run_output.mkdir()
        write_json(run_output / "evidence.json", evidence)
        write_json(run_output / "score.json", {
            "score": {key: value["status"] for key, value in scores.items()},
            "diagnostics": scores,
        })
        write_json(run_output / "event-refs.json", {
            "raw_trace": source_ref,
            "raw_trace_sha256": sha256(trace),
            "references": references,
        })
        summaries.append({
            "run": run_name,
            "score": {key: value["status"] for key, value in scores.items()},
            "reasons": {key: value["reason"] for key, value in scores.items()},
            "workflow_event_count": len(evidence["workflow_events"]),
            "source_raw_trace": source_ref,
        })

    after_hashes = {relative: sha256(bundle / relative) for relative in pinned["inputs"]}
    if after_hashes != source_hashes:
        raise SystemExit("source inputs changed during reassessment")
    write_json(output / "summary.json", {"runs": summaries})
    write_json(output / "source-checksums.json", {
        "pinned_checksum_file_sha256": sha256(checksum_file),
        "before": source_hashes,
        "after": after_hashes,
        "unchanged": source_hashes == after_hashes,
    })
    write_json(output / "reproduction.json", {
        "command": "python3 evals/development-workflow/reassess_published.py",
        "script_sha256": sha256(SCRIPT),
        "evaluator_sha256": sha256(eval_root / "consumer.py"),
        "manifest_sha256": sha256(manifest_path),
        "input_checksum_file": os.path.relpath(checksum_file, output).replace(os.sep, "/"),
        "input_checksum_file_sha256": sha256(checksum_file),
        "historical_commands_executed": False,
        "hermes_or_llm_runs": 0,
    })
    print(json.dumps(summaries, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
