#!/usr/bin/env python3
"""Multi-run evaluation harness for flight-calendar-ics skill.

Uses hermes sessions DB for accurate tool_call_count instead of stdout parsing.
Runs N sessions per (model × version) pair, reports tool_minimality distribution
and per-layer counts.

Usage:
  # Preflight only (native tool-call smoke test):
  python multirun_harness.py --preflight-only --ignore-user-config --n-runs 5

  # Full multi-run eval (skip preflight if already confirmed):
  python multirun_harness.py --n-runs 5 --ignore-user-config --eval-only

  # Specific models:
  python multirun_harness.py --models gemma4_31b gemini_3_flash_preview --n-runs 5

Harness operational pitfalls:

  - **Sessions DB is the authoritative metric source.** Quiet mode suppresses
    tool-invocation detail from stdout. Always query state.db for tool_call_count,
    api_call_count, message_count, model. Session ID from stderr:
    ``session_id: <hex_id>`` — parse with
    ``re.search(r"session_id:\\s*([a-f0-9_]+)", proc.stderr)``.

  - **WAL commit lag.** Use ``sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)``
    with retry (5 attempts × 1s delay). Plain connect() can race with WAL
    checkpoint; the row exists but is not yet visible to readers opened before
    checkpoint completion. If still absent after all retries, classify as
    DB-visibility failure (not model failure).

  - **Python stdout buffering.** subprocess.run(capture_output=True) and
    background processes do not flush print() in real time. Monitor filesystem
    artifacts (run_metrics.json, aggregate.json) for progress, not process poll
    output. Add ``-u`` (PYTHONUNBUFFERED=1) or sys.stdout.flush() after each
    status line if real-time monitoring matters.

  - **gpt-oss:20b exclusion.** Persistent empty-content failure (finish_reason=stop,
    nonzero tokens, empty message.content). Excluded from all multi-run evals by
    default. Re-evaluate only after a successful native tool-call preflight.

  - **Version switching.** This harness toggles top-level no_further_action_needed
    promotion in parser.py via string replacement. Always restore v1.7.8
    (top-level enabled) after eval completes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Configuration ──────────────────────────────────────────────────────────

MODELS = {
    "gemma4_31b": {"model": "gemma4:31b", "provider": "ollama-cloud"},
    "gemini_3_flash_preview": {"model": "gemini-3-flash-preview", "provider": "ollama-cloud"},
    "deepseek_v4_flash": {"model": "deepseek-v4-flash", "provider": "ollama-cloud"},
    # gpt_oss_20b excluded: persistent empty-content failure, 0 native tool calls
}

SKILL_DIR = Path(os.environ.get(
    "SKILL_DIR",
    "/home/konstantin/.hermes/skills/productivity/flight-calendar-ics",
))
PRIVATE_INPUT = Path(os.environ.get(
    "EVAL_PRIVATE_INPUT",
    "/tmp/flight_ics_v177_eval/private/itinerary.json",
))
PARSER_PATH = SKILL_DIR / "scripts" / "flight_calendar" / "parser.py"
EVAL_ROOT = Path(os.environ.get("EVAL_ROOT", "/tmp/flight_ics_multirun_eval"))
SESSIONS_DB = Path.home() / ".hermes" / "state.db"

FLOOR_TOOL_COUNT = 6  # max acceptable tool calls on happy path

# ── Version switching ──────────────────────────────────────────────────────

TOPLEVEL_PROMOTION = '''    # Top-level signal: models check "ok" first — put the stop signal right next to it.
    if handoff_data.get("no_further_action_needed") is True:
        obj["no_further_action_needed"] = True'''

TOPLEVEL_PROMOTION_DISABLED = '''    # Top-level signal: DISABLED for v1.7.7 eval (depth-3 only)
    # if handoff_data.get("no_further_action_needed") is True:
    #     obj["no_further_action_needed"] = True'''


def switch_version(version: str) -> None:
    """Toggle top-level no_further_action_needed in parser.py."""
    content = PARSER_PATH.read_text()
    if version == "v1.7.8":
        if TOPLEVEL_PROMOTION_DISABLED in content:
            content = content.replace(TOPLEVEL_PROMOTION_DISABLED, TOPLEVEL_PROMOTION)
            PARSER_PATH.write_text(content)
            print(f"  [version] Switched to v1.7.8 (top-level NFAA enabled)", flush=True)
        elif TOPLEVEL_PROMOTION in content:
            print(f"  [version] Already v1.7.8", flush=True)
    elif version == "v1.7.7":
        if TOPLEVEL_PROMOTION in content:
            content = content.replace(TOPLEVEL_PROMOTION, TOPLEVEL_PROMOTION_DISABLED)
            PARSER_PATH.write_text(content)
            print(f"  [version] Switched to v1.7.7 (top-level NFAA disabled)", flush=True)
        elif TOPLEVEL_PROMOTION_DISABLED in content:
            print(f"  [version] Already v1.7.7", flush=True)


# ── Session metrics from DB ────────────────────────────────────────────────

def query_session_metrics(session_id: str, retries: int = 5, delay: float = 1.0) -> dict[str, Any]:
    """Query Hermes sessions DB for structured metrics with retry for WAL commit lag.
    Uses ?mode=ro URI to avoid locking conflicts with WAL writer.
    """
    import sqlite3

    if not SESSIONS_DB.exists():
        return {"error": "sessions DB not found"}

    result: dict[str, Any] = {}

    for attempt in range(retries):
        try:
            conn = sqlite3.connect(f"file:{SESSIONS_DB}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT tool_call_count, api_call_count, message_count, "
                    "input_tokens, output_tokens, model, started_at, ended_at "
                    "FROM sessions WHERE id = ?",
                    (session_id,),
                ).fetchone()

                if row:
                    result = dict(row)
                    break
            finally:
                conn.close()
        except Exception:
            pass

        if attempt < retries - 1:
            time.sleep(delay)
    else:
        return {"error": f"session not found after {retries} retries: {session_id}"}

    # Query messages for tool trace
    try:
        conn = sqlite3.connect(f"file:{SESSIONS_DB}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            msg_rows = conn.execute(
                "SELECT role, tool_name, tool_calls, content FROM messages WHERE session_id = ?",
                (session_id,),
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        result["tool_trace"] = []
        result["fallback_activated"] = False
        return result

    # Parse tool trace from messages
    tool_trace: list[str] = []
    tool_names: list[str] = []
    all_content = ""

    for m in msg_rows:
        role = m["role"]
        if role == "assistant" and m["tool_calls"]:
            try:
                calls = json.loads(m["tool_calls"]) if isinstance(m["tool_calls"], str) else m["tool_calls"]
                for tc in calls:
                    fn = tc.get("function", {}).get("name", "") if isinstance(tc, dict) else ""
                    tool_trace.append(fn)
                    tool_names.append(fn)
            except (json.JSONDecodeError, TypeError):
                pass
        elif role == "tool" and m["tool_name"]:
            tool_names.append(m["tool_name"])

        c = m["content"] or ""
        if isinstance(c, str):
            all_content += c + " "

    result["tool_trace"] = tool_trace
    result["tool_names_distinct"] = list(dict.fromkeys(tool_names))
    result["fallback_activated"] = (
        "Fallback activated" in all_content or "fallback activated" in all_content.lower()
    )

    return result


# ── Data structures ────────────────────────────────────────────────────────

@dataclass
class RunResult:
    model_id: str
    version: str
    run_index: int
    tool_calls: int = 0
    wall_time_s: float = 0.0
    artifact_success: bool = False
    envelope_contract_success: bool = False
    tool_minimality_success: bool = False
    final_answer_protocol_success: bool = False
    privacy_success: bool = True
    provider_model_match: bool = True
    fallback_activated: bool = False
    zero_tool_calls: bool = False
    error: str = ""
    session_id: str = ""
    tool_trace: list[str] = field(default_factory=list)
    api_call_count: int = 0
    message_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


# ── Session runner ──────────────────────────────────────────────────────────

def run_eval_session(
    model_id: str,
    version: str,
    run_index: int,
    output_dir: Path,
    *,
    ignore_user_config: bool = False,
) -> RunResult:
    """Run a single eval session via hermes chat -q."""
    model_spec = MODELS[model_id]
    result = RunResult(model_id=model_id, version=version, run_index=run_index)

    run_dir = output_dir / model_id / f"run_{run_index}" / version
    run_dir.mkdir(parents=True, exist_ok=True)

    # Copy private input
    priv_dir = run_dir / "private"
    priv_dir.mkdir(exist_ok=True)
    priv_input = priv_dir / "itinerary.json"
    if not priv_input.exists():
        shutil.copy2(PRIVATE_INPUT, priv_input)
        os.chmod(priv_input, 0o600)

    # Build eval prompt
    eval_prompt = (
        f"Навык: flight-calendar-ics. "
        f"Вход: {priv_input}. "
        f"Output dir: {run_dir}. "
        f"requested_provider={model_spec['provider']}, "
        f"requested_model={model_spec['model']}, "
        f"skill_version_label=runtime-skill-{version.replace('v', '')}. "
        f"Follow SKILL.md runbook exactly. Write result.json."
    )

    # Build command
    cmd = [
        "hermes", "chat",
        "-q", eval_prompt,
        "-m", model_spec["model"],
        "--provider", model_spec["provider"],
        "-t", "terminal,file",
        "-s", "flight-calendar-ics",
        "-Q",
        "--max-turns", "30",
    ]

    if ignore_user_config:
        cmd.append("--ignore-user-config")

    env = os.environ.copy()

    # Run session
    start_time = time.time()
    session_id = ""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
            cwd=str(run_dir),
        )
        result.wall_time_s = time.time() - start_time

        # Extract session ID from stderr
        sid_match = re.search(r"session_id:\s*([a-f0-9_]+)", proc.stderr)
        if sid_match:
            session_id = sid_match.group(1)
            result.session_id = session_id

        # Query session DB for accurate metrics
        if session_id:
            metrics = query_session_metrics(session_id)
            result.tool_calls = metrics.get("tool_call_count", 0)
            result.api_call_count = metrics.get("api_call_count", 0)
            result.message_count = metrics.get("message_count", 0)
            result.input_tokens = metrics.get("input_tokens", 0) or 0
            result.output_tokens = metrics.get("output_tokens", 0) or 0
            result.tool_trace = metrics.get("tool_trace", [])
            result.fallback_activated = metrics.get("fallback_activated", False)

            # Verify model match
            db_model = metrics.get("model", "")
            result.provider_model_match = (db_model == model_spec["model"])

        # Check outputs
        ics_files = list(run_dir.glob("flights.ics")) + list(run_dir.glob("**/flights.ics"))
        result.artifact_success = len(ics_files) > 0

        stdout = proc.stdout
        result.envelope_contract_success = '"ok": true' in stdout or '"ok":true' in stdout

        # Tool minimality
        result.tool_minimality_success = (
            0 < result.tool_calls <= FLOOR_TOOL_COUNT and result.artifact_success
        )

        # Final answer protocol
        result.final_answer_protocol_success = (
            "MEDIA:" in stdout or "safe_summary" in stdout or "result.json" in stdout
        )

        # Zero tool calls
        result.zero_tool_calls = (result.tool_calls == 0)

    except subprocess.TimeoutExpired:
        result.wall_time_s = time.time() - start_time
        result.error = "TIMEOUT: session exceeded 300s"
    except Exception as exc:
        result.wall_time_s = time.time() - start_time
        result.error = f"EXCEPTION: {exc}"

    # Save per-run evidence
    (run_dir / "run_metrics.json").write_text(json.dumps({
        "model_id": result.model_id,
        "version": result.version,
        "run_index": result.run_index,
        "tool_calls": result.tool_calls,
        "tool_trace": result.tool_trace,
        "wall_time_s": round(result.wall_time_s, 2),
        "artifact_success": result.artifact_success,
        "envelope_contract_success": result.envelope_contract_success,
        "tool_minimality_success": result.tool_minimality_success,
        "final_answer_protocol_success": result.final_answer_protocol_success,
        "fallback_activated": result.fallback_activated,
        "zero_tool_calls": result.zero_tool_calls,
        "session_id": result.session_id,
        "error": result.error,
        "api_call_count": result.api_call_count,
        "message_count": result.message_count,
    }, indent=2, default=str))

    return result


# ── Preflight ──────────────────────────────────────────────────────────────

def run_preflight(model_id: str, ignore_user_config: bool) -> dict[str, Any]:
    """Native tool-call smoke test."""
    model_spec = MODELS[model_id]

    cmd = [
        "hermes", "chat",
        "-q", "Read the file /etc/hostname using the read_file tool and tell me the content.",
        "-m", model_spec["model"],
        "--provider", model_spec["provider"],
        "-t", "terminal,file",
        "-Q",
        "--max-turns", "5",
    ]

    if ignore_user_config:
        cmd.append("--ignore-user-config")

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        # Extract session ID
        sid_match = re.search(r"session_id:\s*([a-f0-9_]+)", proc.stderr)
        session_id = sid_match.group(1) if sid_match else ""

        has_tool_call = False
        fallback = False
        zero_tools = True
        actual_model = ""

        if session_id:
            metrics = query_session_metrics(session_id)
            tc_count = metrics.get("tool_call_count", 0)
            has_tool_call = tc_count > 0
            zero_tools = tc_count == 0
            fallback = metrics.get("fallback_activated", False)
            actual_model = metrics.get("model", "")

        return {
            "model_id": model_id,
            "has_tool_call": has_tool_call,
            "fallback_activated": fallback,
            "zero_tool_calls": zero_tools,
            "actual_model": actual_model,
            "session_id": session_id,
            "exit_code": proc.returncode,
        }
    except Exception as exc:
        return {
            "model_id": model_id,
            "error": str(exc),
            "has_tool_call": False,
            "fallback_activated": False,
            "zero_tool_calls": True,
        }


# ── Aggregation ────────────────────────────────────────────────────────────

def aggregate_results(results: list[RunResult], n_runs: int) -> dict[str, Any]:
    """Aggregate multi-run results."""
    by_key: dict[str, list[RunResult]] = defaultdict(list)
    for r in results:
        key = f"{r.model_id}/{r.version}"
        by_key[key].append(r)

    report = {}
    for key in sorted(by_key):
        runs = by_key[key]
        tool_counts = [r.tool_calls for r in runs]
        wall_times = [r.wall_time_s for r in runs]

        layer_counts = {
            "artifact_success": sum(1 for r in runs if r.artifact_success),
            "envelope_contract_success": sum(1 for r in runs if r.envelope_contract_success),
            "tool_minimality_success": sum(1 for r in runs if r.tool_minimality_success),
            "final_answer_protocol_success": sum(1 for r in runs if r.final_answer_protocol_success),
            "privacy_success": sum(1 for r in runs if r.privacy_success),
            "provider_model_match": sum(1 for r in runs if r.provider_model_match),
            "fallback_activated": sum(1 for r in runs if r.fallback_activated),
            "zero_tool_calls": sum(1 for r in runs if r.zero_tool_calls),
        }

        tool_dist = dict(Counter(tool_counts))
        tc_nonzero = [t for t in tool_counts if t > 0]

        entry = {
            "n_runs": len(runs),
            "tool_counts": {
                "values": tool_counts,
                "distribution": {str(k): v for k, v in sorted(tool_dist.items())},
                "median": statistics.median(tc_nonzero) if tc_nonzero else 0,
                "mean": round(statistics.mean(tc_nonzero), 1) if tc_nonzero else 0,
                "min": min(tc_nonzero) if tc_nonzero else 0,
                "max": max(tc_nonzero) if tc_nonzero else 0,
                "stdev": round(statistics.stdev(tc_nonzero), 2) if len(tc_nonzero) > 1 else 0,
            },
            "wall_time": {
                "values": [round(t, 2) for t in wall_times],
                "median": round(statistics.median(wall_times), 1) if wall_times else 0,
                "mean": round(statistics.mean(wall_times), 1) if wall_times else 0,
            },
            "layer_counts": layer_counts,
            "errors": [r.error for r in runs if r.error],
        }
        report[key] = entry

    return report


def format_report(report: dict[str, Any], n_runs: int) -> str:
    """Format report (Telegram-safe, no tables)."""
    lines = []
    lines.append(f"**Multi-run eval: N={n_runs} per (model × version)**")
    lines.append("")

    models = sorted(set(k.split("/")[0] for k in report))

    for model in models:
        v177_key = f"{model}/v1.7.7"
        v178_key = f"{model}/v1.7.8"
        v177 = report.get(v177_key, {})
        v178 = report.get(v178_key, {})

        v177_tc = v177.get("tool_counts", {}) if v177 else {}
        v178_tc = v178.get("tool_counts", {}) if v178 else {}

        v177_med = v177_tc.get("median", "—")
        v178_med = v178_tc.get("median", "—")
        v177_dist = v177_tc.get("distribution", {})
        v178_dist = v178_tc.get("distribution", {})
        v177_std = v177_tc.get("stdev", 0)
        v178_std = v178_tc.get("stdev", 0)

        delta_str = ""
        if isinstance(v177_med, (int, float)) and isinstance(v178_med, (int, float)):
            d = v178_med - v177_med
            delta_str = f"Δ={d:+.0f}"

        lines.append(f"**{model}**")
        lines.append(f"  v1.7.7 depth-3: med={v177_med} σ={v177_std} dist={v177_dist}")
        lines.append(f"  v1.7.8 top-level: med={v178_med} σ={v178_std} dist={v178_dist}")
        if delta_str:
            lines.append(f"  {delta_str}")

        # Per-layer comparison
        v177_l = v177.get("layer_counts", {}) if v177 else {}
        v178_l = v178.get("layer_counts", {}) if v178 else {}
        for layer in ["tool_minimality_success", "zero_tool_calls", "fallback_activated",
                       "artifact_success", "envelope_contract_success"]:
            a = v177_l.get(layer, 0)
            b = v178_l.get(layer, 0)
            if a != b or a > 0 or b > 0:
                lines.append(f"  {layer}: {a}/{n_runs} → {b}/{n_runs}")
        lines.append("")

    # Summary
    lines.append("**Summary: tool_minimality distribution**")
    for key in sorted(report):
        e = report[key]
        tc = e.get("tool_counts", {})
        med = tc.get("median", 0)
        std = tc.get("stdev", 0)
        dist = tc.get("distribution", {})
        minimality = e.get("layer_counts", {}).get("tool_minimality_success", 0)
        n = e.get("n_runs", 0)
        lines.append(f"  {key}: med={med} σ={std} dist={dist} minimality={minimality}/{n}")

    return "\n".join(lines)


# ── Direct CLI baseline ─────────────────────────────────────────────────────

def run_cli_baseline(output_dir: Path, version: str) -> dict[str, Any]:
    """Run direct CLI baseline."""
    cli_dir = output_dir / "direct_cli" / version
    cli_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(SKILL_DIR / "scripts" / "flight_calendar_ics.py"),
        "--json", "build", "auto",
        "--input", str(PRIVATE_INPUT),
        "--output-dir", str(cli_dir),
    ]

    start = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    elapsed = time.time() - start

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        data = {}

    has_top = "no_further_action_needed" in data
    nfaa_loc = "top+handoff" if has_top else "handoff-only"

    result = {
        "version": version,
        "ok": data.get("ok"),
        "elapsed_s": round(elapsed, 2),
        "route": data.get("data", {}).get("agent_handoff", {}).get("safe_summary", {}).get("route"),
        "nfaa_location": nfaa_loc,
    }

    (cli_dir / "direct_metrics.json").write_text(json.dumps(result, indent=2))
    return result


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Multi-run flight-calendar-ics eval harness")
    parser.add_argument("--n-runs", type=int, default=5)
    parser.add_argument("--models", nargs="+", default=None)
    parser.add_argument("--versions", nargs="+", default=["v1.7.7", "v1.7.8"])
    parser.add_argument("--skip-preflight", action="store_true")
    parser.add_argument("--ignore-user-config", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--eval-only", action="store_true")
    args = parser.parse_args()

    model_ids = args.models or list(MODELS.keys())
    versions = args.versions
    n_runs = args.n_runs

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    eval_dir = EVAL_ROOT / f"run_{timestamp}"
    eval_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Multi-run Eval Harness ===", flush=True)
    print(f"  Models: {model_ids}", flush=True)
    print(f"  Versions: {versions}", flush=True)
    print(f"  N runs: {n_runs}", flush=True)
    print(f"  Eval dir: {eval_dir}", flush=True)
    print(f"  Ignore user config: {args.ignore_user_config}", flush=True)
    print(f"  Total sessions: {len(model_ids) * len(versions) * n_runs}", flush=True)
    print(flush=True)

    all_results: list[RunResult] = []

    # ── Preflight ──
    if not args.skip_preflight and not args.eval_only:
        print("=== Preflight: Native tool-call smoke tests ===", flush=True)
        preflight_results = {}
        for model_id in model_ids:
            print(f"  {model_id}...", end=" ", flush=True)
            pf = run_preflight(model_id, args.ignore_user_config)
            preflight_results[model_id] = pf
            status = "✅" if pf.get("has_tool_call") else "❌"
            fb = " [FALLBACK!]" if pf.get("fallback_activated") else ""
            zt = " [0 TOOLS!]" if pf.get("zero_tool_calls") else ""
            am = f" [model={pf.get('actual_model', '')}]" if pf.get("actual_model") else ""
            print(f"{status}{fb}{zt}{am}", flush=True)

            if pf.get("zero_tool_calls") and not pf.get("fallback_activated"):
                print(f"    ⚠️ native-tool-call failure — model returned 0 tool calls without fallback", flush=True)

        (eval_dir / "preflight_results.json").write_text(
            json.dumps(preflight_results, indent=2, default=str)
        )
        print(flush=True)

        if args.preflight_only:
            return

    # ── CLI baselines ──
    print("=== CLI Baselines ===", flush=True)
    for version in versions:
        switch_version(version)
        baseline = run_cli_baseline(eval_dir, version)
        print(f"  {version}: ok={baseline['ok']} route={baseline['route']} nfaa={baseline['nfaa_location']} time={baseline['elapsed_s']}s", flush=True)
    print(flush=True)

    # ── Multi-run evals ──
    total_sessions = len(model_ids) * len(versions) * n_runs
    completed = 0

    for version in versions:
        switch_version(version)

        for model_id in model_ids:
            for run_idx in range(1, n_runs + 1):
                completed += 1
                print(f"  [{completed}/{total_sessions}] {model_id}/{version}/run_{run_idx}...", end=" ", flush=True)

                result = run_eval_session(
                    model_id=model_id,
                    version=version,
                    run_index=run_idx,
                    output_dir=eval_dir,
                    ignore_user_config=args.ignore_user_config,
                )
                all_results.append(result)

                status = "✅" if result.artifact_success and not result.error else "❌"
                fb = " [FALLBACK]" if result.fallback_activated else ""
                zt = " [0-TOOLS]" if result.zero_tool_calls else ""
                print(f"{status} tools={result.tool_calls} time={result.wall_time_s:.1f}s{fb}{zt}", flush=True)

    print(flush=True)

    # Restore v1.7.8
    switch_version("v1.7.8")

    # ── Aggregation ──
    report = aggregate_results(all_results, n_runs)

    # Save JSON
    report_serializable = {}
    for k, v in report.items():
        entry = {}
        for fk, fv in v.items():
            if isinstance(fv, dict):
                entry[fk] = {str(sk): sv for sk, sv in fv.items()}
            else:
                entry[fk] = fv
        report_serializable[k] = entry

    (eval_dir / "aggregate.json").write_text(json.dumps(report_serializable, indent=2, default=str))

    # Save all runs metrics
    results_data = [{
        "model_id": r.model_id, "version": r.version, "run_index": r.run_index,
        "tool_calls": r.tool_calls, "wall_time_s": round(r.wall_time_s, 2),
        "artifact_success": r.artifact_success,
        "envelope_contract_success": r.envelope_contract_success,
        "tool_minimality_success": r.tool_minimality_success,
        "final_answer_protocol_success": r.final_answer_protocol_success,
        "fallback_activated": r.fallback_activated,
        "zero_tool_calls": r.zero_tool_calls,
        "error": r.error, "session_id": r.session_id,
        "tool_trace": r.tool_trace,
    } for r in all_results]
    (eval_dir / "all_runs_metrics.json").write_text(json.dumps(results_data, indent=2))

    # Format summary
    summary = format_report(report, n_runs)
    (eval_dir / "summary.md").write_text(summary)

    # Metadata
    metadata = {
        "timestamp": timestamp, "n_runs": n_runs, "models": model_ids,
        "versions": versions, "ignore_user_config": args.ignore_user_config,
        "total_sessions": total_sessions, "completed": completed,
        "eval_dir": str(eval_dir),
    }
    (eval_dir / "run_metadata.json").write_text(json.dumps(metadata, indent=2))

    print(summary, flush=True)
    print(f"\nFull results: {eval_dir}/", flush=True)


if __name__ == "__main__":
    main()