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
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _timezone_config(case: dict[str, Any]) -> tuple[ZoneInfo, str]:
    config = case.get("report") if isinstance(case.get("report"), dict) else {}
    name = str(config.get("timezone") or DEFAULT_REPORT_TIMEZONE)
    try:
        zone = ZoneInfo(name)
    except Exception:
        name = DEFAULT_REPORT_TIMEZONE
        zone = ZoneInfo(name)
    label = str(config.get("timezone_label") or name)
    return zone, label


def _duration_seconds(run: dict[str, Any]) -> float | None:
    values = [run.get("elapsed_seconds")]
    metrics = run.get("metrics")
    if isinstance(metrics, dict):
        values.append(metrics.get("duration_seconds"))
    for value in values:
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
    if minutes:
        return f"{minutes} мин {remainder} сек"
    return f"{remainder} сек"


def _run_result(run: dict[str, Any]) -> str:
    if run.get("execution_status") != "COMPLETED":
        return str(run.get("execution_status") or "FAIL")
    values = list((run.get("score") or {}).values())
    if any(value == "ERROR" for value in values):
        return "ERROR"
    if any(value == "FAIL" for value in values):
        return "FAIL"
    if values and all(value == "PASS" for value in values):
        return "PASS"
    if any(value == "PASS" for value in values):
        return "PARTIAL"
    return "UNDEFINED"


def _batch_result(runs: list[dict[str, Any]]) -> str:
    labels = [_run_result(run) for run in runs]
    if labels and all(label == "PASS" for label in labels):
        return "PASS"
    if labels and all(label not in {"PASS", "PARTIAL"} for label in labels):
        return "FAIL"
    return "PARTIAL"


def _floor_minute(value: datetime) -> datetime:
    return value.replace(second=0, microsecond=0)


def _ceil_minute(value: datetime) -> datetime:
    if value.second or value.microsecond:
        value = value + timedelta(minutes=1)
    return value.replace(second=0, microsecond=0)


def _batch_window(runs: list[dict[str, Any]], zone: ZoneInfo) -> tuple[str | None, float | None]:
    starts = [parsed for run in runs if (parsed := _parse_datetime(run.get("started_at"))) is not None]
    ends = [parsed for run in runs if (parsed := _parse_datetime(run.get("ended_at"))) is not None]
    if not starts or not ends:
        return None, None

    start = min(starts)
    end = max(ends)
    start_local = _floor_minute(start.astimezone(zone))
    end_local = _ceil_minute(end.astimezone(zone))
    if start_local.date() == end_local.date():
        period = f"{start_local:%d.%m.%Y}, {start_local:%H:%M}–{end_local:%H:%M}"
    else:
        period = f"{start_local:%d.%m.%Y %H:%M} – {end_local:%d.%m.%Y %H:%M}"
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


def _score(run: dict[str, Any], dimension: str) -> str:
    return str((run.get("score") or {}).get(dimension, "—"))


def _fact(run: dict[str, Any], key: str) -> str:
    facts = run.get("report_facts")
    if isinstance(facts, dict) and key in facts:
        return str(facts[key])
    return "—"


def _note(run: dict[str, Any]) -> str:
    note = run.get("report_note")
    if isinstance(note, str) and note.strip():
        return note.strip().replace("\n", " ")
    error = run.get("error")
    if isinstance(error, str) and error.strip():
        return error.strip().replace("\n", " ")
    return "—"


def _skill_sources(runs: list[dict[str, Any]]) -> list[str]:
    seen: set[tuple[str, str, str]] = set()
    lines: list[str] = []
    for run in runs:
        source = run.get("skill_source")
        if not isinstance(source, dict):
            continue
        version = str(run.get("skill_version", ""))
        requested = str(source.get("requested_ref") or source.get("source") or "unknown")
        resolved = str(source.get("resolved_commit") or "")
        key = (version, requested, resolved)
        if key in seen:
            continue
        seen.add(key)
        short = resolved[:7] if resolved else "unknown"
        lines.append(f"- **{version}:** `{requested} @ {short}`")
    return lines


def render_report(batch: dict[str, Any], case: dict[str, Any]) -> str:
    runs = list(batch.get("runs", []))
    zone, zone_label = _timezone_config(case)
    period, batch_duration = _batch_window(runs, zone)
    successful = sum(_run_result(run) == "PASS" for run in runs)

    lines = [
        "# EVAL REPORT",
        "",
        "## STATUS",
        "",
        f"**Результат:** {_batch_result(runs)}  ",
        f"**Запуски:** {len(runs)}  ",
        f"**Успешно:** {successful}/{len(runs)}  ",
    ]
    if period is not None:
        lines.append(f"**Период:** {period}  ")
    if batch_duration is not None:
        lines.append(f"**Общее время:** {format_batch_duration(batch_duration)}  ")
    lines.append(f"**Часовой пояс:** {zone_label}")
    lines.extend(["", "Кратко:"])
    for (model, _provider), model_runs in _model_groups(runs):
        passed = sum(_run_result(run) == "PASS" for run in model_runs)
        lines.append(f"- {model} — {passed}/{len(model_runs)} PASS")

    lines.extend(["", "## BASELINE", ""])
    lines.append(f"**Consumer:** `{batch.get('consumer', 'unknown')}`")
    modes = sorted({str(run.get("mode")) for run in runs if run.get("mode")})
    if modes:
        lines.append(f"**Mode:** `{', '.join(modes)}`")
    source_lines = _skill_sources(runs)
    if source_lines:
        lines.extend(["", "Skill source:", *source_lines])
    lines.extend([
        "",
        f"**Expected runs:** {len(batch.get('expected_run_ids', []))}  ",
        f"**Executed runs:** {len(batch.get('executed_run_ids', []))}",
    ])

    lines.extend(["", "## RESULTS", ""])
    for (model, provider), model_runs in _model_groups(runs):
        passed = sum(_run_result(run) == "PASS" for run in model_runs)
        lines.extend([
            f"### {model} / {provider} — {passed}/{len(model_runs)} PASS",
            "",
            "| Scenario | Run | Result | Time | Tools | CLI | URL | Примечание |",
            "|---|---:|---|---:|---:|---:|---|---|",
        ])
        for run in sorted(model_runs, key=lambda item: int(item.get("repeat", 0))):
            metrics = run.get("metrics") if isinstance(run.get("metrics"), dict) else {}
            cli = _fact(run, "CLI")
            if cli == "—":
                cli = str(metrics.get("cli_build_calls", "—"))
            row = [
                str(run.get("scenario", "—")),
                str(run.get("repeat", "—")),
                _run_result(run),
                format_run_duration(_duration_seconds(run)),
                str(metrics.get("tool_calls", "—")),
                cli,
                _fact(run, "URL"),
                _note(run).replace("|", "\\|"),
            ]
            lines.append("| " + " | ".join(row) + " |")

        durations = [value for run in model_runs if (value := _duration_seconds(run)) is not None]
        if durations:
            lines.extend([
                "",
                f"**Среднее:** {format_run_duration(statistics.fmean(durations))}  ",
                f"**Медиана:** {format_run_duration(statistics.median(durations))}  ",
                f"**Диапазон:** {format_run_duration(min(durations))}–{format_run_duration(max(durations))}",
            ])
        lines.append("")

    lines.extend([
        "## CONTRACT CHECKS",
        "",
        "| Model | Outcome | Trajectory | Privacy |",
        "|---|---|---|---|",
    ])
    for (model, _provider), model_runs in _model_groups(runs):
        def count_pass(dimension: str) -> str:
            passed = sum(_score(run, dimension) == "PASS" for run in model_runs)
            return f"{passed}/{len(model_runs)}"

        lines.append(
            f"| {model} | {count_pass('outcome')} | "
            f"{count_pass('trajectory')} | {count_pass('privacy')} |"
        )

    url_runs = [
        run
        for run in runs
        if isinstance(run.get("report_facts"), dict)
        and run["report_facts"].get("URL") not in {None, "—"}
    ]
    if url_runs:
        lines.extend(["", "**URL integrity**"])
        for (model, _provider), model_runs in _model_groups(url_runs):
            exact = sum(_fact(run, "URL").lower() == "exact" for run in model_runs)
            lines.append(f"- {model}: {exact}/{len(model_runs)} exact")

    findings = []
    for run in runs:
        if _run_result(run) == "PASS":
            continue
        findings.append(
            f"- `{run.get('run_id', 'unknown')}` — "
            f"{_run_result(run)}; {_note(run)}"
        )
    lines.extend(["", "## FINDINGS", ""])
    if findings:
        lines.extend(findings)
    else:
        lines.append("Существенных отклонений в batch не зафиксировано.")

    lines.extend([
        "",
        "## ARTIFACTS",
        "",
        "Полные machine timestamps, raw traces и детальная evidence сохраняются "
        "в batch/run artifacts. ISO timestamps с микросекундами намеренно не "
        "дублируются в этом человекочитаемом отчёте.",
        "",
        "## GIT",
        "",
        "Точная версия evaluated skill указана в BASELINE. Состояние checkout "
        "и local/remote выводится только если launcher сохранил эти данные как evidence.",
        "",
    ])
    return "\n".join(lines)


def write_report(batch: dict[str, Any], case: dict[str, Any], output_dir: Path) -> Path:
    path = output_dir / "report.md"
    path.write_text(render_report(batch, case), encoding="utf-8")
    return path
