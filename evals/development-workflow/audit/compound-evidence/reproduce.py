#!/usr/bin/env python3
"""Recompute this packaged feature-shout evidence audit using Python stdlib only."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(payload)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def decode_result(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {"output": value}
        if isinstance(decoded, dict):
            if "output" not in decoded and isinstance(decoded.get("content"), str):
                return {**decoded, "output": decoded["content"]}
            return decoded
        return {"output": value}
    return value if isinstance(value, dict) else {}


def simple_chain(command: str) -> tuple[list[list[str]], list[str]] | None:
    """Parse only the evaluator's simple command-list subset; never execute it."""
    if "\n" in command or "\r" in command:
        return None
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return None
    if not tokens or any(token in {"<", ">", ">>", "<>", "<<<", "<<"} for token in tokens):
        return None
    commands: list[list[str]] = []
    operators: list[str] = []
    current: list[str] = []
    for token in tokens:
        if token in {"&&", ";", "||", "|", "&"}:
            if not current or token in {"||", "|", "&"}:
                return None
            commands.append(current)
            operators.append(token)
            current = []
        elif any(char in token for char in ";&|<>"):
            return None
        else:
            current.append(token)
    if not current:
        return None
    commands.append(current)
    return commands, operators


def is_verification(path: str) -> bool:
    parts = [part.lower() for part in Path(path).parts]
    name = parts[-1] if parts else ""
    return (any(p in {"test", "tests", "spec", "specs", "checks", "contracts", "features"} for p in parts)
            or name.startswith("test_") or name.endswith("_test.py") or name.endswith(".feature"))


def events_for(path: Path) -> list[dict[str, Any]]:
    events = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        item = json.loads(line)
        if not isinstance(item, dict) or item.get("index") != len(events):
            raise ValueError(f"{path}:{line_no}: missing or nonsequential event index")
        events.append(item)
    if not events:
        raise ValueError(f"{path}: no events")
    return events


def paired(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pending: dict[str, dict[str, Any]] = {}
    pairs = []
    for event in events:
        kind = event.get("type")
        call_id = str(event.get("call_id", ""))
        if kind == "tool_use":
            if not call_id or call_id in pending:
                raise ValueError(f"invalid/duplicate tool call id at event {event['index']}")
            pending[call_id] = event
        elif kind == "tool_result":
            call = pending.pop(call_id, None)
            if call is None or call.get("name") != event.get("name"):
                raise ValueError(f"unmatched tool result at event {event['index']}")
            pairs.append({"call": call, "result": event})
    if pending:
        raise ValueError(f"unanswered tool calls: {sorted(pending)}")
    return pairs


def invocation(argv: list[str], target_script: str) -> list[str] | None:
    if (len(argv) >= 2 and argv[0] in {"python", "python3"}
            and Path(argv[1]).name == target_script):
        return list(argv[2:])
    return None


def probe_matches(argv: list[str], output: str, exit_code: Any,
                  probe: dict[str, Any], behavior: list[dict[str, Any]]) -> bool:
    signals = [str(x) for x in probe.get("input_signals", [])]
    args = invocation(argv, "app.py")
    if args is None:
        return False
    observed = [Path(argv[1]).name, *args]
    if signals and not all(signal in observed for signal in signals):
        return False
    if not signals and args:
        return False
    expected = []
    for item in behavior:
        command = item.get("command", [])
        if len(command) < 2 or item.get("stdout") != probe.get("stdout") or item.get("exit_code") != probe.get("exit_code"):
            continue
        if (all(signal in command[1:] for signal in signals) if signals else not command[2:]):
            expected.append((Path(str(command[1])).name, list(command[2:])))
    return ((Path(argv[1]).name, args) in expected
            and output == str(probe.get("stdout", ""))
            and exit_code == probe.get("exit_code"))


def workflow(events: list[dict[str, Any]], cfg: dict[str, Any], supplemental: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    applications: list[dict[str, Any]] = []
    noarg_occurrences: list[dict[str, Any]] = []
    noarg_probe = supplemental["probe"]
    unparsed_commands: list[dict[str, Any]] = []
    pending_pairs = paired(events)
    records = []
    for pair in pending_pairs:
        call, result_event = pair["call"], pair["result"]
        name, args = str(call.get("name", "")), call.get("input", {})
        result = decode_result(result_event.get("output"))
        output = str(result.get("output", ""))
        command = str(args.get("command", "")) if isinstance(args, dict) else ""
        record = {"index": call["index"], "tool": name, "output": output, "command": command,
                  "exit_code": result.get("exit_code"), "input": args, "result": result}
        if name == "terminal":
            parsed = simple_chain(command)
            if parsed is None:
                unparsed_commands.append({"event_index": call["index"], "command": command})
            else:
                commands, operators = parsed
                for ordinal, argv in enumerate(commands):
                    tail = invocation(argv, "app.py") if len(argv) > 1 and Path(argv[1]).name == "app.py" else None
                    if tail is None:
                        continue
                    success = (record["exit_code"] == 0 and
                               (len(commands) == 1 or (operators and all(op == "&&" for op in operators))))
                    attributable = len(commands) == 1 and isinstance(record["exit_code"], int)
                    app = {"event_index": call["index"], "command_event_index": call["index"],
                           "ordinal": ordinal, "argv": argv, "arguments_after_script": tail,
                           "command": command, "tool_exit_code": record["exit_code"],
                           "execution": "CONFIRMED_SUCCESS" if success else "UNCONFIRMED",
                           "stdout_attribution": "OWN_RESULT_AVAILABLE" if attributable else "UNCONFIRMED"}
                    applications.append(app)
                    if not tail:
                        noarg_occurrences.append({**app, "result":
                            "CONFIRMED" if attributable and success
                            and record["exit_code"] == noarg_probe["exit_code"]
                            and output == noarg_probe["stdout"] else "UNCONFIRMED"})
                    if attributable:
                        for key, kind in (("current_behavior_probes", "current_behavior_observed"),
                                          ("preserved_behavior_probes", "preserved_behavior_observed")):
                            for probe_index, probe in enumerate(cfg.get(key, [])):
                                if probe_matches(argv, output, record["exit_code"], probe, cfg["behavior_probes"]):
                                    facts.append({"kind": kind, "index": call["index"], "probe_index": probe_index})
            check = test_check(command, output, record["exit_code"])
            if check:
                facts.append({"kind": "target_check_" + check, "index": call["index"], "output": output})
                if check == "failed":
                    facts.append({"kind": "verification_failed", "index": call["index"]})
        if name in {"patch", "write_file", "edit_file"} and isinstance(args, dict):
            if name == "patch":
                paths = result.get("files_modified", [])
                text = str(args.get("patch", "")) + "\n" + output
            else:
                paths = [args.get("path", "")]
                text = str(args.get("content", "")) if name == "write_file" else json.dumps(args, ensure_ascii=False)
            verification_flags = [is_verification(str(path)) for path in paths if path]
            if any(verification_flags):
                if cfg.get("target_check_signals") and all(signal in text for signal in cfg["target_check_signals"]):
                    facts.append({"kind": "target_check_changed", "index": call["index"]})
                facts.append({"kind": "verification_changed", "index": call["index"]})
            if any(not flag for flag in verification_flags):
                facts.append({"kind": "production_changed", "index": call["index"]})
        records.append(record)

    facts.sort(key=lambda item: int(item.get("index", 0)))
    production = [f["index"] for f in facts if f["kind"] == "production_changed"]
    first_prod = min(production) if production else None
    curr_pre = [f for f in facts if f["kind"] == "current_behavior_observed" and (first_prod is None or f["index"] < first_prod)]
    preserved_post = [f for f in facts if f["kind"] == "preserved_behavior_observed" and first_prod is not None and f["index"] > first_prod]
    noarg_pre = any(o["result"] == "CONFIRMED" and (first_prod is None or o["event_index"] < first_prod)
                    for o in noarg_occurrences)
    noarg_post = any(o["result"] == "CONFIRMED" and first_prod is not None and o["event_index"] > first_prod
                     for o in noarg_occurrences)
    return facts, applications, {"pre_change_current": curr_pre, "post_change_preserved": preserved_post,
                                 "pre_change_no_argument": noarg_pre, "post_change_no_argument": noarg_post,
                                 "no_argument_command_present": bool(noarg_occurrences),
                                 "no_argument_occurrences": noarg_occurrences,
                                 "unparsed_terminal_commands": unparsed_commands}


def test_check(command: str, output: str, exit_code: Any) -> str | None:
    parsed = simple_chain(command)
    if not parsed or not isinstance(exit_code, int):
        return None
    commands, operators = parsed
    runners = [argv for argv in commands if (Path(argv[0]).name in {"pytest", "vitest", "jest", "phpunit"}
               or (len(argv) >= 3 and argv[0] in {"python", "python3"} and argv[1:3] in (["-m", "pytest"], ["-m", "unittest"]))) ]
    if len(runners) != 1 or (operators and any(op in {"||", "|", "&"} for op in operators)):
        return None
    failed = bool(re.search(r"(?:\bFAILED\b|\bFAILURES\b|\bAssertionError\b|\bassertion failed\b|\b[1-9][0-9]* failed\b|\bnot ok\b)", output, re.I))
    runner_last = commands.index(runners[0]) == len(commands) - 1
    chained_and = bool(operators) and all(op == "&&" for op in operators)
    if exit_code == 0 and (runner_last or chained_and):
        return "passed"
    if len(commands) == 1 and failed:
        return "failed"
    return None


def trajectory(facts: list[dict[str, Any]], rules: dict[str, Any]) -> tuple[str, str]:
    positions: dict[str, list[int]] = {}
    for fact in facts:
        positions.setdefault(str(fact.get("kind", "")), []).append(int(fact.get("index", 0)))
    reasons = []
    production = positions.get("production_changed", [])
    first_prod = min(production) if production else None
    current_pre = [f for f in facts if f.get("kind") == "current_behavior_observed" and
                   (first_prod is None or int(f["index"]) < first_prod)]
    unique_current = {f.get("probe_index") for f in current_pre}
    if len(unique_current) < int(rules.get("current_probe_count", 1)):
        reasons.append("current observable behavior is UNCONFIRMED")
    if first_prod is None:
        reasons.append("production change is UNCONFIRMED")
    changed = positions.get("target_check_changed", [])
    failed = [f for f in facts if f.get("kind") == "target_check_failed"]
    signal = rules.get("target_failure_signal")
    red = [f for f in failed if str(signal) in str(f.get("output", ""))] if signal else failed
    if not changed:
        reasons.append("executable target check change is UNCONFIRMED")
    if rules.get("requires_red", True):
        if not red:
            reasons.append("target check RED before production change is UNCONFIRMED")
        elif first_prod is not None and not any(c < int(f["index"]) < first_prod for f in red for c in changed):
            reasons.append("target check RED was not observed between check change and production change")
        elif first_prod is not None and min(int(f["index"]) for f in red) >= first_prod:
            reasons.append("target check RED occurred after production change")
    passed_after = [i for i in positions.get("target_check_passed", []) if first_prod is not None and i > first_prod]
    if first_prod is not None and not passed_after:
        reasons.append("executable verification GREEN after production change is UNCONFIRMED")
    preserved = [f for f in facts if f.get("kind") == "preserved_behavior_observed" and first_prod is not None and int(f["index"]) > first_prod]
    if len({f.get("probe_index") for f in preserved}) < int(rules.get("preserved_probe_count", 0)):
        reasons.append("required preserved behavior is UNCONFIRMED after production change")
    return ("FAIL" if reasons else "PASS", "; ".join(reasons) if reasons else "")


def run_counterexample(cfg: dict[str, Any], supplemental: dict[str, Any]) -> dict[str, Any]:
    case_dir = ROOT / "counterexample"
    expected = read_json(case_dir / "expected.json")
    app = case_dir / "app.py"
    actual_processes = []
    for process in expected["expected_processes"]:
        result = subprocess.run(
            ["python3", "-B", str(app), *process["argv"]], cwd=case_dir,
            text=True, capture_output=True, check=False,
        )
        actual = {"argv": process["argv"], "exit_code": result.returncode, "stdout": result.stdout}
        if actual != process:
            raise AssertionError(f"counterexample process differs: expected {process}, got {actual}")
        actual_processes.append(actual)
    command = expected["composite_command"]
    composite = subprocess.run(command, cwd=case_dir, shell=True, text=True, capture_output=True, check=False)
    if composite.returncode != expected["composite_exit_code"] or composite.stdout != expected["composite_stdout"]:
        raise AssertionError("counterexample composite execution differs from expected output/status")
    call_id = "compound-evidence-counterexample"
    events = [
        {"type": "tool_use", "name": "terminal", "call_id": call_id, "index": 0,
         "input": {"command": command}},
        {"type": "tool_result", "name": "terminal", "call_id": call_id, "index": 1,
         "output": json.dumps({"output": composite.stdout, "exit_code": composite.returncode})},
    ]
    facts, invocations, summary = workflow(events, cfg, supplemental)
    if any(f["kind"] in {"current_behavior_observed", "preserved_behavior_observed"} for f in facts):
        raise AssertionError("evaluator attributed a compound output line to an individual run")
    if len(invocations) != 3 or any(x["execution"] != "CONFIRMED_SUCCESS" for x in invocations):
        raise AssertionError("the three successful app executions were not represented")
    if any(x["stdout_attribution"] != "UNCONFIRMED" for x in invocations):
        raise AssertionError("compound stdout was incorrectly marked attributable")
    if not summary["no_argument_command_present"] or not summary["no_argument_occurrences"]:
        raise AssertionError("the example's final no-argument invocation was not detected")
    if summary["no_argument_occurrences"][0]["result"] != "UNCONFIRMED":
        raise AssertionError("the final invocation received an unsupported default-output attribution")
    return {"composite_command": command, "individual_processes": actual_processes,
            "composite_exit_code": composite.returncode, "composite_stdout": composite.stdout,
            "evaluator_workflow_events": facts, "application_invocations": invocations,
            "no_argument_check": {"command_present": True, "execution_confirmed": True,
                                   "result_attributable": False}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="regenerate assessment.json from packaged traces")
    args = parser.parse_args()
    index = read_json(ROOT / "index.json")
    manifest_path = ROOT / "historical-manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    if sha256(manifest_bytes) != index["historical_manifest_sha256"]:
        raise AssertionError("historical manifest byte hash mismatch")
    manifest = json.loads(manifest_bytes)
    scenario = manifest["scenarios"]["feature-shout"]
    policy = read_json(ROOT / "historical-policy.json")
    supplemental = read_json(ROOT / "additional-requirement.json")
    if supplemental.get("report_separately") is not True:
        raise AssertionError("supplemental criterion is not explicitly separated from history")
    if canonical_sha256(scenario) != index["historical_config_sha256"]:
        raise AssertionError("historical scenario config hash mismatch")
    if policy["historical_scenario_config_sha256"] != index["historical_config_sha256"]:
        raise AssertionError("policy and index scenario config hashes differ")
    if policy["evaluator_source_sha256"] != index["evaluator_source_sha256"]:
        raise AssertionError("evaluator source identity differs between policy and index")
    batches = read_json(ROOT / "batch-identities.json")
    expected_runs = []
    batch_for_run = {}
    for batch in batches:
        if batch["expected_run_ids"] != batch["executed_run_ids"]:
            raise AssertionError(f"batch identity mismatch: {batch['batch']}")
        if len(batch["executed_run_ids"]) != 3:
            raise AssertionError(f"unexpected batch run count: {batch['batch']}")
        expected_runs.extend(batch["executed_run_ids"])
        batch_for_run.update({rid: batch for rid in batch["executed_run_ids"]})
    if expected_runs != index["runs"] or len(index["runs"]) != 6:
        raise AssertionError("six run IDs do not match batch metadata")
    if sha256((ROOT / "counterexample/app.py").read_bytes()) != index["counterexample_app_sha256"]:
        raise AssertionError("counterexample fixture hash mismatch")
    if sha256((ROOT / "counterexample/expected.json").read_bytes()) != index["counterexample_expected_sha256"]:
        raise AssertionError("counterexample expectation hash mismatch")
    counterexample = run_counterexample(scenario, supplemental)
    results = []
    for run_id in index["runs"]:
        run_dir = RUNS / run_id
        meta = read_json(run_dir / "metadata.json")
        batch = batch_for_run[run_id]
        if meta["source_batch"] != batch["batch"] or meta["skill_version"] != batch["skill_version"]:
            raise AssertionError(f"run metadata does not match batch identity for {run_id}")
        if meta["source_run_id"] != run_id or meta["scenario"] != "feature-shout":
            raise AssertionError(f"run metadata identity mismatch for {run_id}")
        events_path = run_dir / "events.jsonl"
        score_path = run_dir / "original-score.json"
        events_bytes = events_path.read_bytes()
        score_bytes = score_path.read_bytes()
        if sha256(events_bytes) != meta["published_events_sha256"]:
            raise AssertionError(f"published event copy hash mismatch for {run_id}")
        if sha256(score_bytes) != meta["original_score_sha256"]:
            raise AssertionError(f"published score copy hash mismatch for {run_id}")
        events = events_for(events_path)
        actual_events, applications, summary = workflow(events, scenario, supplemental)
        if summary["unparsed_terminal_commands"]:
            raise AssertionError(f"unparsed terminal commands prevent a complete absence claim for {run_id}")
        status, reason = trajectory(actual_events, policy["trajectory_rules"])
        app_events = []
        # Report each source terminal event once, with every parsed app invocation and attribution state.
        by_index = {}
        for app in applications:
            by_index.setdefault(app["event_index"], []).append(app)
        for index_event, group in sorted(by_index.items()):
            app_events.append({"event_index": index_event, "command": group[0]["command"], "invocations": group})
        assessment = {
            "run_id": run_id,
            "source_batch": meta["source_batch"],
            "original_score": read_json(score_path)["score"],
            "historical_score": {"outcome": read_json(score_path)["score"]["outcome"],
                                 "privacy": read_json(score_path)["score"]["privacy"], "trajectory": status},
            "previous_trajectory_reason": meta["previous_trajectory_reason"],
            "trajectory_reason_before_compound_fix": meta["historical_trajectory_reason_before_compound-fix"],
            "trajectory_reason": reason,
            "historical_probe_evidence": {
                "pre_change_current": summary["pre_change_current"],
                "post_change_preserved": summary["post_change_preserved"],
            },
            "trace_command_coverage": {"unparsed_terminal_commands": summary["unparsed_terminal_commands"],
                                        "absence_claim_supported": not summary["unparsed_terminal_commands"]},
            "workflow_events": actual_events,
            "application_invocations": app_events,
            "supplemental_no_argument": {
                "requirement_is_historical": False,
                "probe": supplemental["probe"],
                "probe_command_present": summary["no_argument_command_present"],
                "execution_confirmed": any(x["execution"] == "CONFIRMED_SUCCESS" for x in summary["no_argument_occurrences"]),
                "result_attributable": any(x["result"] == "CONFIRMED" for x in summary["no_argument_occurrences"]),
                "pre_change_observed": summary["pre_change_no_argument"],
                "post_change_observed": summary["post_change_no_argument"],
                "occurrences": summary["no_argument_occurrences"],
            },
            "source_sha256": {"published_events": meta["published_events_sha256"],
                              "original_raw_session": meta["original_raw_session_sha256"],
                              "original_evidence": meta["original_evidence_sha256"],
                              "original_score": meta["original_score_sha256"]},
        }
        expected_path = run_dir / "assessment.json"
        if args.write:
            expected_path.write_text(json.dumps(assessment, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        else:
            expected = read_json(expected_path)
            if expected != assessment:
                raise AssertionError(f"assessment differs from traces for {run_id}")
        results.append(assessment)
    summary = {"package_version": index["package_version"], "run_count": len(results),
               "counterexample": counterexample,
               "runs": [{"run_id": r["run_id"], "historical_score": r["historical_score"],
                         "trajectory_reason": r["trajectory_reason"],
                         "no_argument": r["supplemental_no_argument"]} for r in results]}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
