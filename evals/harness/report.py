from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


DEFAULT_REPORT_TIMEZONE = "UTC"


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _timezone_config(case: dict[str, Any]) -> tuple[ZoneInfo, str]:
    config = case.get("report") if isinstance(case.get("report"), dict) else {}
    name = str(config.get("timezone") or DEFAULT_REPORT_TIMEZONE)
    try:
        zone = ZoneInfo(name)
    except Exception:
        name, zone = DEFAULT_REPORT_TIMEZONE, ZoneInfo(DEFAULT_REPORT_TIMEZONE)
    return zone, str(config.get("timezone_label") or name)


def _duration_seconds(run: dict[str, Any]) -> float | None:
    for value in (run.get("elapsed_seconds"), (run.get("metrics") or {}).get("duration_seconds")):
        if isinstance(value, (int, float)) and value >= 0:
            return float(value)
    return None


def format_run_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    if seconds < 60:
        return f"{seconds:.1f} сек"
    rounded = int(round(seconds))
    minutes, remainder = divmod(rounded, 60)
    return f"{minutes} мин {remainder} сек"


def format_batch_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    rounded = int(round(seconds))
    minutes, remainder = divmod(rounded, 60)
    return f"{minutes} мин {remainder} сек" if minutes else f"{remainder} сек"


def _floor_minute(value: datetime) -> datetime:
    return value.replace(second=0, microsecond=0)


def _ceil_minute(value: datetime) -> datetime:
    if value.second or value.microsecond:
        value += timedelta(minutes=1)
    return value.replace(second=0, microsecond=0)


def _batch_window(runs: list[dict[str, Any]], zone: ZoneInfo) -> tuple[str | None, float | None]:
    starts = [parsed for run in runs if (parsed := _parse_datetime(run.get("started_at"))) is not None]
    ends = [parsed for run in runs if (parsed := _parse_datetime(run.get("ended_at"))) is not None]
    if not starts or not ends:
        return None, None
    start, end = min(starts), max(ends)
    local_start, local_end = _floor_minute(start.astimezone(zone)), _ceil_minute(end.astimezone(zone))
    if local_start.date() == local_end.date():
        period = f"{local_start:%d.%m.%Y}, {local_start:%H:%M}–{local_end:%H:%M}"
    else:
        period = f"{local_start:%d.%m.%Y %H:%M} – {local_end:%d.%m.%Y %H:%M}"
    return period, max(0.0, (end - start).total_seconds())


def _model_groups(runs: list[dict[str, Any]]) -> list[tuple[tuple[str, str], list[dict[str, Any]]]]:
    order: list[tuple[str, str]] = []
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for run in runs:
        key = (str(run.get("model", "")), str(run.get("provider", "")))
        if key not in groups:
            order.append(key)
            groups[key] = []
        groups[key].append(run)
    return [(key, groups[key]) for key in order]


def _run_result(run: dict[str, Any]) -> str:
    if run.get("execution_status") == "RUNTIME_FAILURE":
        return "RUNTIME_FAILURE"
    values = list((run.get("score") or {}).values())
    if any(value == "ERROR" for value in values):
        return "ERROR"
    if any(value == "FAIL" for value in values):
        return "FAIL"
    if values and all(value == "PASS" for value in values):
        return "PASS"
    if any(value == "PASS" for value in values):
        return "PARTIAL"
    if run.get("execution_status") == "AGENT_FAILURE":
        return "FAIL"
    return "UNDEFINED"


def _batch_result(runs: list[dict[str, Any]]) -> str:
    labels = [_run_result(run) for run in runs]
    if labels and all(label == "PASS" for label in labels):
        return "PASS"
    if any(label == "PASS" for label in labels):
        return "PARTIAL"
    return "FAIL"


def _scenario_label(name: str) -> str:
    return {
        "ural-url-success": "Ural",
        "pdf-success": "PDF",
        "url-success": "URL",
    }.get(name, name)


def _diagnostic_lines(run: dict[str, Any]) -> list[str]:
    diagnostics = run.get("diagnostics") if isinstance(run.get("diagnostics"), dict) else {}
    lines: list[str] = []
    for dimension in ("outcome", "trajectory", "privacy"):
        detail = diagnostics.get(dimension)
        if not isinstance(detail, dict):
            continue
        status, reason = detail.get("status"), detail.get("reason")
        if status not in {"PASS", None} and reason:
            lines.append(f"- {dimension.title()}: {status} — {reason}")
    if run.get("execution_status") == "RUNTIME_FAILURE":
        error = run.get("error") or "runtime/harness failure"
        lines.insert(0, f"- Runtime: FAIL — {error}")
    return lines


def _facts(run: dict[str, Any]) -> str | None:
    facts = run.get("report_facts") if isinstance(run.get("report_facts"), dict) else {}
    values: list[str] = []
    for key in ("Source", "AnyDoc", "CLI", "CLI success", "URL"):
        if key in facts and facts[key] not in {None, "—"}:
            label = {"AnyDoc": "AnyDoc calls", "CLI": "CLI calls", "CLI success": "CLI success"}.get(key, key)
            values.append(f"{label}: {facts[key]}")
    return "; ".join(values) if values else None


def _skill_sources(runs: list[dict[str, Any]]) -> list[str]:
    seen: set[tuple[str, str, str]] = set()
    lines: list[str] = []
    for run in runs:
        source = run.get("skill_source")
        if not isinstance(source, dict):
            continue
        key = (
            str(run.get("skill_version", "")),
            str(source.get("requested_ref") or source.get("source") or "unknown"),
            str(source.get("resolved_commit") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"- **{key[0]}:** `{key[1]} @ {key[2][:7] or 'unknown'}`")
    return lines


def render_report(batch: dict[str, Any], case: dict[str, Any]) -> str:
    runs = list(batch.get("runs", []))
    zone, zone_label = _timezone_config(case)
    period, batch_duration = _batch_window(runs, zone)
    scenarios: list[str] = []
    for run in runs:
        scenario = str(run.get("scenario", ""))
        if scenario not in scenarios:
            scenarios.append(scenario)
    model_groups = _model_groups(runs)
    successful = sum(_run_result(run) == "PASS" for run in runs)

    lines = [
        "# EVAL REPORT",
        "",
        "## STATUS",
        "",
        f"Result: {_batch_result(runs)}",
        f"Runs: {successful}/{len(runs)} PASS",
    ]
    if period:
        lines.append(f"Period: {period}")
    if batch_duration is not None:
        lines.append(f"Duration: {format_batch_duration(batch_duration)}")
    lines.extend([f"Timezone: {zone_label}", "", "## BASELINE", ""])
    lines.append(f"Consumer: `{batch.get('consumer', 'unknown')}`")
    modes = sorted({str(run.get("mode")) for run in runs if run.get("mode")})
    if modes:
        lines.append(f"Mode: `{', '.join(modes)}`")
    source_lines = _skill_sources(runs)
    if source_lines:
        lines.extend(["", "Skill source:", *source_lines])
    lines.extend([
        "",
        f"Expected runs: {len(batch.get('expected_run_ids', []))}",
        f"Executed runs: {len(batch.get('executed_run_ids', []))}",
        "",
        "## RESULTS",
        "",
    ])

    header = ["Model", *(_scenario_label(scenario) for scenario in scenarios)]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))
    for (model, _provider), group in model_groups:
        cells = [model]
        for scenario in scenarios:
            matching = [run for run in group if run.get("scenario") == scenario]
            if not matching:
                cells.append("—")
                continue
            run = matching[0]
            cells.append(f"{_run_result(run)} · {format_run_duration(_duration_seconds(run))}")
        lines.append("| " + " | ".join(cells) + " |")

    lines.extend(["", "## FACTS", ""])
    fact_lines = []
    for run in runs:
        fact = _facts(run)
        if fact:
            fact_lines.append(f"- {run.get('model')} / {_scenario_label(str(run.get('scenario')))}: {fact}")
    lines.extend(fact_lines or ["No additional domain facts."])

    lines.extend(["", "## CONTRACT CHECKS", "", "| Model | Outcome | Trajectory | Privacy |", "|---|---|---|---|"])
    for (model, _provider), group in model_groups:
        counts = []
        for dimension in ("outcome", "trajectory", "privacy"):
            counts.append(f"{sum((run.get('score') or {}).get(dimension) == 'PASS' for run in group)}/{len(group)}")
        lines.append(f"| {model} | {' | '.join(counts)} |")

    url_runs = [run for run in runs if (_facts(run) or "").find("URL:") >= 0]
    if url_runs:
        lines.extend(["", "URL integrity"])
        for (model, _provider), group in _model_groups(url_runs):
            exact = sum((run.get("report_facts") or {}).get("URL") == "exact" for run in group)
            lines.append(f"- {model}: {exact}/{len(group)} exact")

    lines.extend(["", "## FINDINGS", ""])
    findings = []
    for run in runs:
        if _run_result(run) == "PASS":
            continue
        diagnostics = _diagnostic_lines(run)
        if diagnostics:
            findings.append(f"### {run.get('model')} / {_scenario_label(str(run.get('scenario')))}")
            findings.extend(diagnostics)
    lines.extend(findings or ["No failures recorded."])
    lines.extend([
        "",
        "## ARTIFACTS",
        "",
        "Raw traces and detailed evidence remain in the batch/run artifacts. Human report timestamps are intentionally minute-readable.",
        "",
        "## GIT",
        "",
        "Git state is recorded by the launcher when available.",
        "",
    ])
    return "\n".join(lines)


def write_report(batch: dict[str, Any], case: dict[str, Any], output_dir: Path) -> Path:
    path = output_dir / "report.md"
    path.write_text(render_report(batch, case), encoding="utf-8")
    return path
