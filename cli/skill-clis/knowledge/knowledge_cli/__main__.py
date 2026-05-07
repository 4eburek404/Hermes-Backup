#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from knowledge_cli import __version__


DEFAULT_DOCS_ROOT = Path.home() / "docs"
DEFAULT_HERMES_HOME = Path.home() / ".hermes"
DEFAULT_WORKER_SCRIPT = (
    DEFAULT_HERMES_HOME
    / "skills"
    / "note-taking"
    / "knowledge-architecture"
    / "scripts"
    / "distillation_worker.py"
)
DEFAULT_COMPANION_SKILL = Path.home() / ".codex" / "skills" / "knowledge-cli" / "SKILL.md"

ACTIVE_STATUSES = ("planned", "in_progress", "blocked")
CLOSED_STATUSES = ("done", "completed", "cancelled", "canceled", "superseded")


class CliError(Exception):
    def __init__(
        self,
        kind: str,
        message: str,
        *,
        details: Any = None,
        exit_code: int = 1,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.details = details
        self.exit_code = exit_code


def json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise CliError("read_error", f"Cannot read {path}", details=str(exc))


def iso_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")


def rel_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_markdown_file(path: Path, root: Path) -> dict[str, Any]:
    text = read_text(path)
    lines = text.splitlines()
    headings: list[dict[str, Any]] = []
    title = None
    current_status = None
    current_status_line = None

    for idx, line in enumerate(lines, start=1):
        heading = re.match(r"^(#{1,3})\s+(.+?)\s*$", line)
        if heading:
            level = len(heading.group(1))
            value = heading.group(2).strip()
            headings.append({"level": level, "line": idx, "text": value})
            if title is None and level == 1:
                title = value
        if current_status is None and line.startswith("Current status:"):
            current_status = line.split(":", 1)[1].strip()
            current_status_line = idx

    stat = path.stat()
    return {
        "path": str(path),
        "rel_path": rel_path(path, root),
        "bytes": stat.st_size,
        "mtime": iso_mtime(path),
        "lines": len(lines),
        "title": title,
        "headings": headings,
        "current_status": current_status,
        "current_status_line": current_status_line,
    }


def markdown_files(root: Path, max_depth: int | None = None) -> list[Path]:
    if not root.exists():
        return []
    paths = []
    for path in root.rglob("*.md"):
        if not path.is_file():
            continue
        if max_depth is not None:
            depth = len(path.relative_to(root).parts)
            if depth > max_depth:
                continue
        paths.append(path)
    return sorted(paths)


def normalize_status(status: str | None) -> str:
    if not status:
        return "missing"
    lowered = status.strip().lower()
    first = re.split(r"[\s(:;,.-]+", lowered, maxsplit=1)[0]
    if first in ACTIVE_STATUSES:
        return "active"
    if first in CLOSED_STATUSES:
        return "closed"
    return "unknown"


def finding(
    finding_class: str,
    severity: str,
    path: str,
    message: str,
    *,
    line: int | None = None,
    action: str | None = None,
    evidence: Any = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "class": finding_class,
        "severity": severity,
        "path": path,
        "message": message,
    }
    if line is not None:
        out["line"] = line
    if action is not None:
        out["action"] = action
    if evidence is not None:
        out["evidence"] = evidence
    return out


def docs_inventory_data(docs_root: Path, max_depth: int | None = None) -> dict[str, Any]:
    files = [parse_markdown_file(path, docs_root) for path in markdown_files(docs_root, max_depth)]
    total_bytes = sum(item["bytes"] for item in files)
    total_lines = sum(item["lines"] for item in files)
    return {
        "docs_root": str(docs_root),
        "exists": docs_root.exists(),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "total_lines": total_lines,
        "files": files,
    }


def plans_inventory_data(docs_root: Path) -> dict[str, Any]:
    plans_root = docs_root / "plans"
    archive_root = plans_root / "archive"
    root_plans = []
    archive_plans = []

    if plans_root.exists():
        for path in sorted(plans_root.glob("*.md")):
            if path.name == "README.md":
                continue
            info = parse_markdown_file(path, docs_root)
            info["status_kind"] = normalize_status(info["current_status"])
            root_plans.append(info)

    if archive_root.exists():
        for path in sorted(archive_root.rglob("*.md")):
            if path.name == "README.md":
                continue
            info = parse_markdown_file(path, docs_root)
            info["status_kind"] = normalize_status(info["current_status"])
            archive_plans.append(info)

    return {
        "plans_root": str(plans_root),
        "archive_root": str(archive_root),
        "plans_root_exists": plans_root.exists(),
        "archive_root_exists": archive_root.exists(),
        "root_count": len(root_plans),
        "archive_count": len(archive_plans),
        "root_plans": root_plans,
        "archive_plans": archive_plans,
    }


def plans_audit_data(docs_root: Path) -> dict[str, Any]:
    inventory = plans_inventory_data(docs_root)
    findings: list[dict[str, Any]] = []

    if not inventory["plans_root_exists"]:
        findings.append(
            finding(
                "missing_index",
                "error",
                str(docs_root / "plans"),
                "Plans root does not exist.",
                action="create_or_point_to_canonical_plans_root",
            )
        )
        return {"inventory": inventory, "findings": findings, "finding_count": len(findings)}

    for item in inventory["root_plans"]:
        status_kind = item["status_kind"]
        if status_kind == "missing":
            findings.append(
                finding(
                    "plan_status_drift",
                    "warn",
                    item["path"],
                    "Root plan has no machine-readable 'Current status:' line.",
                    action="add_current_status",
                )
            )
        elif status_kind == "closed":
            findings.append(
                finding(
                    "plan_status_drift",
                    "warn",
                    item["path"],
                    "Closed plan is still in plans root.",
                    line=item["current_status_line"],
                    action="archive_plan",
                    evidence={"current_status": item["current_status"]},
                )
            )
        elif status_kind == "unknown":
            findings.append(
                finding(
                    "plan_status_drift",
                    "info",
                    item["path"],
                    "Plan status is present but not one of the expected lifecycle statuses.",
                    line=item["current_status_line"],
                    action="normalize_current_status",
                    evidence={"current_status": item["current_status"]},
                )
            )

    for item in inventory["archive_plans"]:
        if item["status_kind"] == "active":
            findings.append(
                finding(
                    "plan_status_drift",
                    "warn",
                    item["path"],
                    "Active plan appears under archive.",
                    line=item["current_status_line"],
                    action="review_archive_location",
                    evidence={"current_status": item["current_status"]},
                )
            )
        elif item["status_kind"] == "missing":
            findings.append(
                finding(
                    "plan_status_drift",
                    "info",
                    item["path"],
                    "Archived plan has no machine-readable 'Current status:' line.",
                    action="add_or_confirm_archived_status",
                )
            )

    return {"inventory": inventory, "findings": findings, "finding_count": len(findings)}


SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private_key_marker", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "assignment_secret",
        re.compile(
            r"(?i)\b(api[_-]?key|token|secret|password|passwd|bearer|cookie)\b"
            r"\s*[:=]\s*['\"]?[^'\"\s`]{8,}"
        ),
    ),
    ("url_token_param", re.compile(r"(?i)[?&](access_token|refresh_token|api_key|token|key)=")),
    (
        "credential_path",
        re.compile(
            r"(?i)/(?:home|etc|var|opt)/[^\s`'\"]*"
            r"(credential|secret|token|private[_-]?key|service[_-]?account)[^\s`'\"]*"
        ),
    ),
]


def scan_secrets_data(path: Path) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    files_scanned = 0

    if path.is_file():
        paths = [path]
    elif path.exists():
        paths = sorted(p for p in path.rglob("*") if p.is_file())
    else:
        paths = []

    for file_path in paths:
        if file_path.stat().st_size > 5_000_000:
            continue
        files_scanned += 1
        try:
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line_no, line in enumerate(lines, start=1):
            for name, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(
                        {
                            "class": "secret_risk",
                            "severity": "warn",
                            "path": str(file_path),
                            "line": line_no,
                            "pattern": name,
                            "message": "Potential secret or sensitive credential metadata detected; value intentionally omitted.",
                        }
                    )

    return {
        "path": str(path),
        "exists": path.exists(),
        "files_scanned": files_scanned,
        "finding_count": len(findings),
        "findings": findings,
    }


def docs_audit_data(docs_root: Path) -> dict[str, Any]:
    inventory = docs_inventory_data(docs_root)
    findings: list[dict[str, Any]] = []

    readme = docs_root / "README.md"
    if not readme.exists():
        findings.append(
            finding(
                "missing_index",
                "warn",
                str(readme),
                "Docs README.md is missing.",
                action="create_docs_index",
            )
        )

    for item in inventory["files"]:
        if item["bytes"] > 20_000:
            findings.append(
                finding(
                    "dead_log",
                    "info",
                    item["path"],
                    "Large markdown file; review for raw logs, stale plan history, or content that belongs in a skill.",
                    action="review_large_file",
                    evidence={"bytes": item["bytes"], "lines": item["lines"]},
                )
            )
        if not item["title"]:
            findings.append(
                finding(
                    "missing_index",
                    "info",
                    item["path"],
                    "Markdown file has no level-1 title.",
                    action="add_title",
                )
            )

    secret_scan = scan_secrets_data(docs_root)
    findings.extend(secret_scan["findings"])
    plan_audit = plans_audit_data(docs_root)
    findings.extend(plan_audit["findings"])

    return {
        "inventory": inventory,
        "secret_scan": {
            "files_scanned": secret_scan["files_scanned"],
            "finding_count": secret_scan["finding_count"],
        },
        "plan_finding_count": plan_audit["finding_count"],
        "findings": findings,
        "finding_count": len(findings),
    }


def sqlite_scalar(cur: sqlite3.Cursor, sql: str) -> Any:
    row = cur.execute(sql).fetchone()
    return row[0] if row else None


def numeric_stats(values: list[float | int]) -> dict[str, Any] | None:
    if not values:
        return None
    return {
        "min": min(values),
        "max": max(values),
        "avg": round(sum(values) / len(values), 3),
        "median": statistics.median(values),
    }


def memory_file_pressure(hermes_home: Path) -> list[dict[str, Any]]:
    result = []
    memories = hermes_home / "memories"
    for name in ("USER.md", "MEMORY.md", "SOUL.md"):
        path = memories / name
        exists = path.exists()
        text = read_text(path) if exists else ""
        result.append(
            {
                "name": name,
                "path": str(path),
                "exists": exists,
                "bytes": path.stat().st_size if exists else 0,
                "chars": len(text),
                "lines": len(text.splitlines()) if text else 0,
            }
        )
    return result


def memory_metrics_data(hermes_home: Path, db_path: Path | None = None) -> dict[str, Any]:
    path = db_path or (hermes_home / "memory_store.db")
    result: dict[str, Any] = {
        "hermes_home": str(hermes_home),
        "db_path": str(path),
        "db_exists": path.exists(),
        "db_size_bytes": path.stat().st_size if path.exists() else 0,
        "memory_files": memory_file_pressure(hermes_home),
    }
    if not path.exists():
        result["tables"] = []
        result["counts"] = {}
        result["facts"] = None
        return result

    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        cur = con.cursor()
        tables = [
            row[0]
            for row in cur.execute(
                "select name from sqlite_master where type='table' order by name"
            ).fetchall()
        ]
        indexes = [
            row[0]
            for row in cur.execute(
                "select name from sqlite_master where type='index' order by name"
            ).fetchall()
        ]
        counts: dict[str, Any] = {}
        for table in ("facts", "facts_fts", "entities", "fact_entities", "memory_banks"):
            if table in tables:
                counts[table] = sqlite_scalar(cur, f"select count(*) from {table}")
            else:
                counts[table] = None

        result["tables"] = tables
        result["indexes"] = indexes
        result["counts"] = counts
        result["fts_consistent"] = (
            counts.get("facts") is not None
            and counts.get("facts_fts") is not None
            and counts.get("facts") == counts.get("facts_fts")
        )

        if "facts" in tables:
            rows = [
                dict(row)
                for row in cur.execute(
                    """
                    select fact_id, category, tags, trust_score, retrieval_count,
                           helpful_count, created_at, updated_at, length(content) as content_len
                    from facts
                    """
                ).fetchall()
            ]
            categories: dict[str, int] = {}
            created_by_day: dict[str, int] = {}
            for row in rows:
                category = row.get("category") or "general"
                categories[category] = categories.get(category, 0) + 1
                day = (row.get("created_at") or "")[:10]
                if day:
                    created_by_day[day] = created_by_day.get(day, 0) + 1
            result["facts"] = {
                "count": len(rows),
                "categories": categories,
                "created_by_day": created_by_day,
                "tagged_count": sum(1 for row in rows if row.get("tags")),
                "trust": numeric_stats([row["trust_score"] for row in rows if row["trust_score"] is not None]),
                "helpful": numeric_stats([row["helpful_count"] for row in rows if row["helpful_count"] is not None]),
                "retrieval": numeric_stats([row["retrieval_count"] for row in rows if row["retrieval_count"] is not None]),
                "content_len": numeric_stats([row["content_len"] for row in rows if row["content_len"] is not None]),
                "top_helpful": sorted(
                    [
                        {
                            "fact_id": row["fact_id"],
                            "helpful_count": row["helpful_count"],
                            "trust_score": row["trust_score"],
                            "category": row["category"],
                            "content_len": row["content_len"],
                        }
                        for row in rows
                    ],
                    key=lambda row: (-(row["helpful_count"] or 0), -(row["trust_score"] or 0)),
                )[:10],
                "low_trust": sorted(
                    [
                        {
                            "fact_id": row["fact_id"],
                            "trust_score": row["trust_score"],
                            "category": row["category"],
                            "content_len": row["content_len"],
                        }
                        for row in rows
                    ],
                    key=lambda row: row["trust_score"] if row["trust_score"] is not None else 999,
                )[:10],
            }
        else:
            result["facts"] = None
    finally:
        con.close()
    return result


def command_doctor(args: argparse.Namespace) -> dict[str, Any]:
    docs_root = Path(args.docs_root).expanduser()
    hermes_home = Path(args.hermes_home).expanduser()
    memory_db = hermes_home / "memory_store.db"
    checks: dict[str, Any] = {
        "version": __version__,
        "python": sys.version.split()[0],
        "docs_root": str(docs_root),
        "docs_root_exists": docs_root.exists(),
        "plans_root_exists": (docs_root / "plans").exists(),
        "hermes_home": str(hermes_home),
        "hermes_home_exists": hermes_home.exists(),
        "memory_db": str(memory_db),
        "memory_db_exists": memory_db.exists(),
        "memory_db_size_bytes": memory_db.stat().st_size if memory_db.exists() else 0,
        "commands": {
            "hermes": shutil.which("hermes"),
            "sqlite3": shutil.which("sqlite3"),
            "python3": shutil.which("python3"),
        },
        "external_checks": {"ran": False},
    }
    if args.check_hermes:
        started = time.monotonic()
        try:
            proc = subprocess.run(
                ["hermes", "memory", "status"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=args.timeout,
                check=False,
            )
            checks["external_checks"] = {
                "ran": True,
                "command": "hermes memory status",
                "exit_code": proc.returncode,
                "elapsed_seconds": round(time.monotonic() - started, 2),
                "stdout": proc.stdout[-2000:],
                "stderr": proc.stderr[-2000:],
            }
        except FileNotFoundError:
            raise CliError("missing_command", "hermes command is not installed on PATH")
        except subprocess.TimeoutExpired:
            raise CliError("timeout", "hermes memory status timed out")
    return checks


def classify_candidate(line: str) -> dict[str, str]:
    lowered = line.lower()
    evidence = "session_summary"
    durability = "medium"
    destination = "skip"
    action = "skip"
    reason = "Candidate kept for curator review."

    if re.search(r"\b(user|пользователь)\b.*\b(corrected|исправ|уточн|сказал)", lowered):
        evidence = "repeated_correction"
        durability = "high"
        action = "update"
        destination = "user-context.md"
        reason = "Direct correction can prevent repeated agent mistakes."
    elif re.search(r"\b(remember|запомни|важно|не трогай|do not|don't|never)\b", lowered):
        evidence = "direct_user_instruction"
        durability = "high"
        action = "add"
        destination = "user-context.md"
        reason = "Direct instruction may be durable user preference or safety rule."
    elif re.search(r"\b(verified|проверено|created|installed|configured|path|cron|service|docker|systemd)\b", lowered):
        evidence = "verified_tool_result"
        durability = "high"
        action = "add"
        destination = "infrastructure.md"
        reason = "Operational fact may belong in infrastructure if still current."
    elif re.search(r"\b(runbook|procedure|checklist|workflow|как делать|процедур)", lowered):
        evidence = "agent_mistake_lesson"
        durability = "medium"
        action = "add"
        destination = "runbooks.md"
        reason = "Repeatable procedure may belong in runbooks or a skill."
    elif re.search(r"\b(memory|fact_store|holographic|memories|memory\.md)\b", lowered):
        evidence = "session_summary"
        durability = "medium"
        action = "update"
        destination = "memory"
        reason = "Memory architecture fact needs curator routing."

    if re.search(r"\b(raw log|full transcript|temporary|one-off|debug dump)\b", lowered):
        durability = "low"
        action = "skip"
        destination = "skip"
        reason = "Looks transient or raw; keep in session history unless curator disagrees."

    return {
        "evidence_type": evidence,
        "durability": durability,
        "destination": destination,
        "action": action,
        "reason": reason,
    }


def split_candidate_lines(text: str, limit: int) -> list[str]:
    chunks = []
    for raw in text.splitlines():
        line = normalize_ws(raw.strip("-* \t"))
        if not line or len(line) < 20:
            continue
        chunks.append(line)
    if len(chunks) < 3:
        chunks = [
            normalize_ws(part)
            for part in re.split(r"(?<=[.!?])\s+", text)
            if len(normalize_ws(part)) >= 30
        ]
    return chunks[:limit]


def offline_distill_candidates(text: str, limit: int) -> dict[str, Any]:
    candidates = []
    seen: set[str] = set()
    for line in split_candidate_lines(text, limit * 2):
        key = re.sub(r"[^a-zа-я0-9]+", " ", line.lower()).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        attrs = classify_candidate(line)
        if attrs["action"] == "skip" and attrs["durability"] == "medium":
            continue
        candidates.append(
            {
                "claim": line[:600],
                **attrs,
                "confidence": "low",
                "votes": 1,
                "workers": ["offline_heuristic"],
            }
        )
        if len(candidates) >= limit:
            break
    return {
        "mode": "offline_heuristic",
        "candidates": candidates,
        "stats": {
            "input_chars": len(text),
            "candidate_count": len(candidates),
            "limit": limit,
            "live_model_calls": False,
        },
    }


def run_live_distillation(text: str, worker_script: Path) -> dict[str, Any]:
    if not worker_script.exists():
        raise CliError("missing_worker", f"Distillation worker not found: {worker_script}")
    spec = importlib.util.spec_from_file_location("knowledge_distillation_worker", worker_script)
    if spec is None or spec.loader is None:
        raise CliError("worker_import_error", f"Cannot import worker script: {worker_script}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise CliError("worker_import_error", "Failed to import distillation worker", details=str(exc))
    try:
        result = module.run_distillation(text)
    except Exception as exc:
        raise CliError("worker_runtime_error", "Live distillation worker failed", details=str(exc))
    if not isinstance(result, dict):
        raise CliError("worker_runtime_error", "Live distillation worker returned non-dict result")
    result.setdefault("mode", "live_models")
    return result


def read_input_text(input_path: str | None) -> str:
    if input_path in (None, "-"):
        return sys.stdin.read()
    path = Path(input_path).expanduser()
    return read_text(path)


def command_distill_candidates(args: argparse.Namespace) -> dict[str, Any]:
    text = read_input_text(args.input)
    if not text.strip():
        raise CliError("empty_input", "No input text provided for distillation candidates")
    if args.live_models:
        return run_live_distillation(text, Path(args.worker_script).expanduser())
    return offline_distill_candidates(text, args.limit)


def command_report(args: argparse.Namespace) -> dict[str, Any]:
    docs_root = Path(args.docs_root).expanduser()
    hermes_home = Path(args.hermes_home).expanduser()
    doctor = command_doctor(args)
    docs = docs_inventory_data(docs_root, max_depth=args.max_depth)
    plans = plans_audit_data(docs_root)
    memory = memory_metrics_data(hermes_home)
    secrets = scan_secrets_data(docs_root)
    data = {
        "doctor": doctor,
        "docs": {
            "file_count": docs["file_count"],
            "total_bytes": docs["total_bytes"],
            "total_lines": docs["total_lines"],
        },
        "plans": {
            "root_count": plans["inventory"]["root_count"],
            "archive_count": plans["inventory"]["archive_count"],
            "finding_count": plans["finding_count"],
            "findings": plans["findings"],
        },
        "memory": {
            "db_exists": memory["db_exists"],
            "db_size_bytes": memory["db_size_bytes"],
            "counts": memory.get("counts", {}),
            "fts_consistent": memory.get("fts_consistent"),
            "memory_files": memory["memory_files"],
        },
        "secrets": {
            "files_scanned": secrets["files_scanned"],
            "finding_count": secrets["finding_count"],
            "findings": secrets["findings"],
        },
    }
    if args.format == "md":
        data["markdown"] = render_report_markdown(data)
    return data


def render_report_markdown(data: dict[str, Any]) -> str:
    lines = [
        "# Knowledge Audit Report",
        "",
        "## Doctor",
        f"- docs_root_exists: {data['doctor']['docs_root_exists']}",
        f"- hermes_home_exists: {data['doctor']['hermes_home_exists']}",
        f"- memory_db_exists: {data['doctor']['memory_db_exists']}",
        "",
        "## Docs",
        f"- markdown files: {data['docs']['file_count']}",
        f"- total lines: {data['docs']['total_lines']}",
        f"- total bytes: {data['docs']['total_bytes']}",
        "",
        "## Plans",
        f"- root plans: {data['plans']['root_count']}",
        f"- archived plans: {data['plans']['archive_count']}",
        f"- findings: {data['plans']['finding_count']}",
    ]
    for item in data["plans"]["findings"][:20]:
        line = item.get("line")
        location = f"{item['path']}:{line}" if line else item["path"]
        lines.append(f"- {item['severity']} {item['class']}: {location} - {item['message']}")
    lines.extend(
        [
            "",
            "## Memory",
            f"- db_exists: {data['memory']['db_exists']}",
            f"- counts: {json.dumps(data['memory']['counts'], ensure_ascii=False)}",
            f"- fts_consistent: {data['memory']['fts_consistent']}",
            "",
            "## Secret Scan",
            f"- files scanned: {data['secrets']['files_scanned']}",
            f"- findings: {data['secrets']['finding_count']}",
        ]
    )
    for item in data["secrets"]["findings"][:20]:
        lines.append(f"- {item['severity']} {item['pattern']}: {item['path']}:{item['line']}")
    return "\n".join(lines) + "\n"


def parse_skill_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    marker = "\n---\n"
    end = text.find(marker, 4)
    if end == -1:
        return {}
    frontmatter = text[4:end]
    values: dict[str, str] = {}
    for line in frontmatter.splitlines():
        if ":" not in line or line.startswith(" "):
            continue
        key, value = line.split(":", 1)
        cleaned = value.strip().strip('"\'')
        values[key.strip()] = cleaned
    return values


def command_skill_companion(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.path).expanduser()
    exists = path.exists()
    text = read_text(path) if exists else ""
    frontmatter = parse_skill_frontmatter(text)
    lowered = text.lower()
    contract = {
        "mentions_self_check": "knowledge --json skill companion" in lowered,
        "mentions_report_all": "knowledge --json report --all" in lowered,
        "mentions_mutation_boundary": bool(re.search(r"\b(edit|editing|mutation|mutat|правк|измен|docs|memory|skills|config|cron)\b", lowered))
        and bool(re.search(r"\b(ask|permission|explicit|before|разреш|явн|не является разрешением)\b", lowered)),
        "mentions_read_only": "read-only" in lowered or "read only" in lowered,
        "mentions_live_model_boundary": "--live-models" in lowered,
    }
    issues = []
    if not exists:
        issues.append("companion_skill_missing")
    if exists and frontmatter.get("name") != "knowledge-cli":
        issues.append("unexpected_skill_name")
    for key, ok in contract.items():
        if not ok:
            issues.append(f"contract_gap:{key}")

    recommended_sequence = [
        "knowledge --json skill companion",
        "knowledge --json report --all",
        "knowledge --json docs audit",
        "knowledge --json plans audit",
        "knowledge --json memory metrics",
        "knowledge --json scan secrets --path /home/konstantin/docs",
    ]
    return {
        "path": str(path),
        "exists": exists,
        "bytes": path.stat().st_size if exists else 0,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest() if exists else None,
        "name": frontmatter.get("name"),
        "description": frontmatter.get("description"),
        "contract": contract,
        "issues": issues,
        "issue_count": len(issues),
        "recommended_sequence": recommended_sequence,
        "mutation_boundary": "CLI output is evidence only; it is not permission to edit docs, memory, skills, config, cron, credentials, or external systems.",
    }


def render_skill_companion_markdown(data: dict[str, Any]) -> str:
    lines = [
        "# knowledge-cli Companion Contract",
        "",
        f"- path: `{data['path']}`",
        f"- exists: {data['exists']}",
        f"- name: {data.get('name')}",
        f"- issue_count: {data['issue_count']}",
        "",
        "## Required Agent Sequence",
    ]
    for command in data["recommended_sequence"]:
        lines.append(f"- `{command}`")
    lines.extend([
        "",
        "## Contract Checks",
    ])
    for key, ok in data["contract"].items():
        lines.append(f"- {key}: {ok}")
    lines.extend([
        "",
        "## Mutation boundary",
        data["mutation_boundary"],
        "",
    ])
    if data["issues"]:
        lines.append("## Issues")
        for issue in data["issues"]:
            lines.append(f"- {issue}")
        lines.append("")
    return "\n".join(lines)


def emit(args: argparse.Namespace, command: str, data: dict[str, Any]) -> None:
    if args.json:
        print(json.dumps({"ok": True, "command": command, "data": data}, ensure_ascii=False, indent=2, default=json_default))
        return
    if args.command == "report" and data.get("markdown") and args.format == "md":
        print(data["markdown"], end="")
        return
    if args.command == "distill" and getattr(args, "format", None) == "md":
        print(render_candidates_markdown(data), end="")
        return
    if args.command == "skill" and getattr(args, "format", None) == "md":
        print(render_skill_companion_markdown(data), end="")
        return
    print(json.dumps(data, ensure_ascii=False, indent=2, default=json_default))


def render_candidates_markdown(data: dict[str, Any]) -> str:
    lines = [
        "# Knowledge Distillation Candidates",
        "",
        f"Mode: {data.get('mode')}",
        f"Stats: {json.dumps(data.get('stats', {}), ensure_ascii=False)}",
        "",
    ]
    for idx, item in enumerate(data.get("candidates", []), start=1):
        lines.extend(
            [
                f"## {idx}. {item.get('destination')} / {item.get('action')}",
                "",
                item.get("claim", ""),
                "",
                f"- evidence_type: {item.get('evidence_type')}",
                f"- durability: {item.get('durability')}",
                f"- confidence: {item.get('confidence')}",
                f"- reason: {item.get('reason')}",
                "",
            ]
        )
    return "\n".join(lines)


def fail(args: argparse.Namespace | None, error: CliError) -> int:
    if args is not None and getattr(args, "json", False):
        payload = {
            "ok": False,
            "error": {
                "type": error.kind,
                "message": error.message,
                "details": error.details,
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default), file=sys.stderr)
    else:
        print(f"knowledge: {error.message}", file=sys.stderr)
        if error.details is not None:
            print(str(error.details), file=sys.stderr)
    return error.exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="knowledge",
        description="Read-only knowledge architecture audit and candidate CLI for local Hermes.",
    )
    parser.add_argument("--json", action="store_true", help="Emit stable JSON envelope.")
    parser.add_argument("--docs-root", default=str(DEFAULT_DOCS_ROOT), help="Docs root path.")
    parser.add_argument("--hermes-home", default=str(DEFAULT_HERMES_HOME), help="Hermes home path.")

    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="Check local paths and optional Hermes memory status.")
    doctor.add_argument("--check-hermes", action="store_true", help="Run 'hermes memory status'.")
    doctor.add_argument("--timeout", type=float, default=10.0)
    doctor.set_defaults(func=command_doctor, command_name="doctor")

    docs = sub.add_parser("docs", help="Inspect / audit markdown docs.")
    docs_sub = docs.add_subparsers(dest="docs_command", required=True)
    docs_inv = docs_sub.add_parser("inventory", help="List docs files, headings, sizes, statuses.")
    docs_inv.add_argument("--max-depth", type=int, default=None)
    docs_inv.set_defaults(
        func=lambda args: docs_inventory_data(Path(args.docs_root).expanduser(), args.max_depth),
        command_name="docs inventory",
    )
    docs_audit = docs_sub.add_parser("audit", help="Read-only docs audit.")
    docs_audit.set_defaults(
        func=lambda args: docs_audit_data(Path(args.docs_root).expanduser()),
        command_name="docs audit",
    )

    plans = sub.add_parser("plans", help="Inspect / audit docs plans.")
    plans_sub = plans.add_subparsers(dest="plans_command", required=True)
    plans_inv = plans_sub.add_parser("inventory", help="List root and archived plans.")
    plans_inv.set_defaults(
        func=lambda args: plans_inventory_data(Path(args.docs_root).expanduser()),
        command_name="plans inventory",
    )
    plans_audit = plans_sub.add_parser("audit", help="Find plan status and archive drift.")
    plans_audit.set_defaults(
        func=lambda args: plans_audit_data(Path(args.docs_root).expanduser()),
        command_name="plans audit",
    )

    memory = sub.add_parser("memory", help="Inspect Hermes holographic memory metadata.")
    memory_sub = memory.add_subparsers(dest="memory_command", required=True)
    metrics = memory_sub.add_parser("metrics", help="SQLite counts, stats, FTS consistency, memory file pressure.")
    metrics.add_argument("--db", default=None, help="Override memory_store.db path.")
    metrics.set_defaults(
        func=lambda args: memory_metrics_data(
            Path(args.hermes_home).expanduser(),
            Path(args.db).expanduser() if args.db else None,
        ),
        command_name="memory metrics",
    )

    scan = sub.add_parser("scan", help="Local scanners.")
    scan_sub = scan.add_subparsers(dest="scan_command", required=True)
    secrets = scan_sub.add_parser("secrets", help="Scan for token-like secrets without printing values.")
    secrets.add_argument("--path", default=str(DEFAULT_DOCS_ROOT), help="File or directory to scan.")
    secrets.set_defaults(
        func=lambda args: scan_secrets_data(Path(args.path).expanduser()),
        command_name="scan secrets",
    )

    distill = sub.add_parser("distill", help="Knowledge distillation helpers.")
    distill_sub = distill.add_subparsers(dest="distill_command", required=True)
    candidates = distill_sub.add_parser("candidates", help="Extract curator candidates from snippets.")
    candidates.add_argument("--input", "-i", default="-", help="Input text file, or '-' for stdin.")
    candidates.add_argument("--limit", type=int, default=20)
    candidates.add_argument("--format", choices=("json", "md"), default="json")
    candidates.add_argument("--live-models", action="store_true", help="Explicitly call the local distillation worker and Ollama Cloud endpoint.")
    candidates.add_argument("--worker-script", default=str(DEFAULT_WORKER_SCRIPT))
    candidates.set_defaults(func=command_distill_candidates, command_name="distill candidates")

    report = sub.add_parser("report", help="Aggregate read-only knowledge audit.")
    report.add_argument("--all", action="store_true", help="Run all safe local checks.")
    report.add_argument("--format", choices=("json", "md"), default="json")
    report.add_argument("--max-depth", type=int, default=None)
    report.add_argument("--check-hermes", action="store_true", help="Include 'hermes memory status'.")
    report.add_argument("--timeout", type=float, default=10.0)
    report.set_defaults(func=command_report, command_name="report")

    skill = sub.add_parser("skill", help="Inspect the companion skill contract for this CLI.")
    skill_sub = skill.add_subparsers(dest="skill_command", required=True)
    companion = skill_sub.add_parser("companion", help="Read-only companion skill contract check.")
    companion.add_argument("--path", default=str(DEFAULT_COMPANION_SKILL), help="Path to knowledge-cli SKILL.md.")
    companion.add_argument("--format", choices=("json", "md"), default="json")
    companion.set_defaults(func=command_skill_companion, command_name="skill companion")

    return parser


def preprocess_argv(argv: list[str]) -> tuple[list[str], bool]:
    json_flag = False
    cleaned = []
    for item in argv:
        if item == "--json":
            json_flag = True
        else:
            cleaned.append(item)
    return cleaned, json_flag


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    cleaned_argv, json_flag = preprocess_argv(raw_argv)
    parser = build_parser()
    args: argparse.Namespace | None = None
    try:
        args = parser.parse_args(cleaned_argv)
        args.json = bool(args.json or json_flag)
        data = args.func(args)
        emit(args, args.command_name, data)
        return 0
    except CliError as exc:
        return fail(args, exc)
    except KeyboardInterrupt:
        return fail(args, CliError("interrupted", "Interrupted", exit_code=130))


if __name__ == "__main__":
    raise SystemExit(main())
