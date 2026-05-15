#!/usr/bin/env python3
"""Deterministic, read-only Hermes skill audit helper.

The helper audits in-repo Hermes skills and emits a stable JSON report suitable
for local automation and future CI gates. By default it does not mutate audited
skills, execute skill-owned CLIs, install packages, or run service commands.
Opt-in --deep-cli executable checks are advisory only and remain non-blocking.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SCHEMA_VERSION = "1.0.0"
TOOL_VERSION = "0.2.0"
MAX_DESCRIPTION_LENGTH = 1024
MAX_SKILL_CONTENT_CHARS = 100_000
MAX_NAME_LENGTH = 64

TEXT_SUFFIXES = {".md", ".py", ".toml", ".yaml", ".yml", ".txt", ".json", ".sh"}
SUPPORT_DIRS = ("references", "templates", "scripts", "assets", "cli", "schemas", "baselines", "tests")
GENERATED_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist", "build"}
GENERATED_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp"}

STALE_PATH_PATTERNS = [
    "/home/konstantin/code/clis",
    "local/skill-clis",
    "cli/skill-clis",
    "cli/hermes-agent",
    "hermes/skills",
]
INTENTIONAL_STALE_CONTEXT_RE = re.compile(
    r"(?i)(stale|obsolete|removed|do not|don't|should not|not recreate|avoid|old|runtime state|not source|guard|stale-path|stale path|example of|false-positive)"
)
SECRET_LINE_RE = re.compile(
    r"(?i)(api[_-]?key|secret|password|passwd|token|authorization|cookie|private[_-]?key|access[_-]?key|database_url|dsn|connection_string)\s*[:=]\s*['\"]?([^'\"\s`]+)"
)
SENSITIVE_ASSIGNMENT_LINE_RE = re.compile(
    r"(?im)(api[_-]?key|secret|password|passwd|token|authorization|cookie|private[_-]?key|access[_-]?key|database_url|dsn|connection_string)\s*[:=]\s*[^\r\n]*"
)
BEARER_TOKEN_RE = re.compile(r"(?i)bearer\s+[^\r\n,'\"`]+")
CLI_SECRET_FLAG_VALUE_RE = re.compile(
    r"(?i)(-{1,2}(?:api[-_]?key|secret|password|passwd|token|authorization|cookie|private[-_]?key|access[-_]?key|database[-_]?url|dsn|connection[-_]?string)(?:\s+|=))([^\s`'\"]+)"
)
SECRET_KEYWORD_RE = re.compile(
    r"(?i)(api[_-]?key|secret|password|passwd|token|authorization|cookie|private[_-]?key|access[_-]?key|database_url|dsn|connection_string)"
)
INTENTIONAL_UNSAFE_SCAN_CONTEXT_RE = re.compile(
    r"(?i)(do not|don't|avoid|not recommend|instead|this skill wins|fails on|detect|fixture|example of unsafe|should flag)"
)


def redact_sensitive_text(value: str) -> str:
    redacted = SENSITIVE_ASSIGNMENT_LINE_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)
    redacted = CLI_SECRET_FLAG_VALUE_RE.sub(lambda match: f"{match.group(1)}[REDACTED]", redacted)
    return BEARER_TOKEN_RE.sub("Bearer [REDACTED]", redacted)


def sanitize_for_report(value: Any) -> Any:
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, list):
        return [sanitize_for_report(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_for_report(item) for key, item in value.items()}
    return value


WHEN_NOT_TO_USE_RE = re.compile(r"(?i)(do\s+(?:\*\*)?not(?:\*\*)?\s+use|don't\s+use|when\s+not\s+to\s+use|do\s+not\s+use\s+this)")
MARKDOWN_LINK_RE = re.compile(r"(?<!\\)!?\[[^\]]+\]\(([^)]+)\)")

REQUIRED_SECTIONS = [
    "## Overview",
    "## When to Use",
    "## Common Pitfalls",
    "## Verification Checklist",
]


class AuditInputError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def relpath(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def safe_read_lines(path: Path) -> List[str]:
    try:
        return read_text(path).splitlines()
    except (UnicodeDecodeError, OSError):
        return []


def parse_frontmatter(text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Return (frontmatter, error). Fallback parser is used when PyYAML is absent."""
    if not text.startswith("---"):
        return None, "frontmatter must start at byte 0"
    match = re.search(r"\n---\s*\n", text[3:])
    if not match:
        return None, "frontmatter closing marker not found"
    fm_text = text[3 : match.start() + 3]
    try:
        import yaml  # type: ignore
    except ImportError:
        yaml = None  # type: ignore[assignment]

    if yaml is not None:
        try:
            data = yaml.safe_load(fm_text)
        except Exception as exc:  # pragma: no cover - exact PyYAML messages vary
            return None, f"frontmatter YAML parse error: {redact_sensitive_text(str(exc))}"
        if not isinstance(data, dict):
            return None, "frontmatter is not a YAML mapping"
        return data, None

    data: Dict[str, Any] = {}
    for line in fm_text.splitlines():
        simple = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not simple:
            continue
        key, value = simple.groups()
        value = value.strip().strip('"').strip("'")
        if value.startswith("[") and value.endswith("]"):
            data[key] = [part.strip().strip('"').strip("'") for part in value[1:-1].split(",") if part.strip()]
        else:
            data[key] = value
    if not data:
        return None, "frontmatter parse failed and fallback found no keys"
    return data, None


def body_after_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return ""
    match = re.search(r"\n---\s*\n", text[3:])
    if not match:
        return ""
    return text[match.end() + 3 :]


def related_skills_from_frontmatter(fm: Dict[str, Any]) -> List[str]:
    metadata = fm.get("metadata") if isinstance(fm, dict) else None
    hermes = metadata.get("hermes") if isinstance(metadata, dict) else None
    related = hermes.get("related_skills") if isinstance(hermes, dict) else None
    if isinstance(related, list):
        return [str(item) for item in related]
    if isinstance(related, str):
        return [item.strip() for item in related.strip("[]").split(",") if item.strip()]
    return []


def git_stdout(repo: Path, args: Sequence[str]) -> Tuple[int, str, str]:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def git_lines(repo: Path, args: Sequence[str]) -> List[str]:
    code, stdout, _ = git_stdout(repo, args)
    if code not in (0, 1):
        return []
    return [line.strip() for line in stdout.splitlines() if line.strip()]


def resolve_repo(repo_arg: str) -> Tuple[Optional[Path], Optional[AuditInputError]]:
    repo = Path(repo_arg).expanduser().resolve()
    if not repo.exists():
        return None, AuditInputError("INVALID_REPO", f"repo path does not exist: {repo}")
    completed = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        return None, AuditInputError("INVALID_REPO", f"not a git repo: {repo}")
    root = Path(completed.stdout.strip()).resolve()
    if not (root / "skills").is_dir():
        return None, AuditInputError("INVALID_REPO", f"git repo has no skills/ directory: {root}")
    return root, None


def changed_names(repo: Path) -> Dict[str, List[str]]:
    unstaged = git_lines(repo, ["diff", "--name-only"])
    staged = git_lines(repo, ["diff", "--cached", "--name-only"])
    untracked = git_lines(repo, ["ls-files", "--others", "--exclude-standard"])
    return {
        "changed_files": sorted(set(unstaged + staged + untracked)),
        "unstaged_files": sorted(set(unstaged)),
        "staged_files": sorted(set(staged)),
        "untracked_files": sorted(set(untracked)),
    }


def repo_manifest(repo: Path) -> Dict[str, Any]:
    branch = git_lines(repo, ["branch", "--show-current"])
    commit_code, commit_stdout, _ = git_stdout(repo, ["rev-parse", "--short=12", "HEAD"])
    status = git_lines(repo, ["status", "--short", "--branch", "--untracked-files=all"])
    changed = changed_names(repo)
    return {
        "root": str(repo.resolve()),
        "branch": branch[0] if branch else None,
        "commit": commit_stdout.strip() if commit_code == 0 else None,
        "dirty": bool(status[1:] if status and status[0].startswith("##") else status),
        "status_short": status,
        **changed,
    }


def find_skill_files(repo: Path) -> List[Path]:
    skills_root = repo / "skills"
    if not skills_root.exists():
        return []
    return sorted(path for path in skills_root.glob("**/SKILL.md") if ".archive" not in path.parts)


def collect_skill_map(repo: Path) -> Dict[str, List[Path]]:
    result: Dict[str, List[Path]] = {}
    for path in find_skill_files(repo):
        try:
            text = read_text(path)
            fm, _ = parse_frontmatter(text)
            name = fm.get("name") if fm else None
            if isinstance(name, str) and name:
                result.setdefault(name, []).append(path)
        except Exception:
            continue
    return result


def resolve_path_target(repo: Path, path_arg: str) -> Path:
    raw = Path(path_arg).expanduser()
    candidate = raw.resolve() if raw.is_absolute() else (repo / raw).resolve()
    skills_root = (repo / "skills").resolve()
    if not is_relative_to(candidate, skills_root):
        raise AuditInputError("TARGET_OUTSIDE_SKILLS", "target path must resolve inside repo skills/")
    skill_path = candidate / "SKILL.md" if candidate.is_dir() else candidate
    if skill_path.name != "SKILL.md":
        raise AuditInputError("TARGET_NOT_SKILL", "target path must be a skill directory or SKILL.md")
    if not skill_path.exists():
        raise AuditInputError("SKILL_NOT_FOUND", f"SKILL.md not found for path: {path_arg}")
    return skill_path.resolve()


def resolve_skill_target(repo: Path, skill_arg: str, skill_map: Dict[str, List[Path]]) -> Path:
    matches = skill_map.get(skill_arg, [])
    if len(matches) == 1:
        return matches[0].resolve()
    if len(matches) > 1:
        raise AuditInputError("AMBIGUOUS_SKILL", f"skill name is ambiguous: {skill_arg}")
    if any(sep in skill_arg for sep in ("/", "\\")) or skill_arg.endswith("SKILL.md"):
        return resolve_path_target(repo, skill_arg)
    raise AuditInputError("SKILL_NOT_FOUND", f"skill not found: {skill_arg}")


def normalize_evidence(evidence: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not evidence:
        return {}
    normalized: Dict[str, Any] = {}
    for key, value in evidence.items():
        if key == "value" and evidence.get("redacted"):
            normalized[key] = "[REDACTED]"
        else:
            normalized[key] = sanitize_for_report(value)
    return normalized


def finding_fingerprint(rule_id: str, path: Optional[str], line: Optional[int], evidence: Optional[Dict[str, Any]]) -> str:
    payload = {
        "rule_id": rule_id,
        "path": path or "",
        "line": line,
        "evidence": normalize_evidence(evidence),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def make_finding(
    rule_id: str,
    severity: str,
    category: str,
    message: str,
    path: Optional[Path | str] = None,
    line: Optional[int] = None,
    column: Optional[int] = None,
    evidence: Optional[Dict[str, Any]] = None,
    suggested_fix: Optional[str] = None,
    root: Optional[Path] = None,
) -> Dict[str, Any]:
    path_str: Optional[str]
    if isinstance(path, Path):
        path_str = relpath(path, root) if root is not None else str(path)
    else:
        path_str = path
    location: Dict[str, Any] = {"path": path_str, "line": line, "column": column}
    finding = {
        "rule_id": rule_id,
        "code": rule_id.lower(),
        "severity": severity,
        "category": category,
        "message": redact_sensitive_text(message),
        "location": location,
        "evidence": normalize_evidence(evidence),
        "suggested_fix": suggested_fix,
        "fingerprint": finding_fingerprint(rule_id, path_str, line, evidence),
    }
    return finding


def make_check(rule_id: str, status: str, category: str, message: Optional[str] = None) -> Dict[str, Any]:
    item: Dict[str, Any] = {"rule_id": rule_id, "status": status, "category": category}
    if message:
        item["message"] = redact_sensitive_text(message)
    return item


def summary_from_findings(findings: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    return {
        "blockers": sum(1 for item in findings if item.get("severity") == "blocker"),
        "warnings": sum(1 for item in findings if item.get("severity") == "warning"),
        "recommendations": sum(1 for item in findings if item.get("severity") == "recommendation"),
        "info": sum(1 for item in findings if item.get("severity") == "info"),
    }


def finding_sort_key(finding: Dict[str, Any]) -> Tuple[int, str, int, str, str]:
    severity_order = {"blocker": 0, "warning": 1, "recommendation": 2, "info": 3}
    location = finding.get("location") or {}
    line = location.get("line") if isinstance(location.get("line"), int) else 0
    return (
        severity_order.get(str(finding.get("severity")), 9),
        str(location.get("path") or ""),
        line,
        str(finding.get("rule_id") or ""),
        str(finding.get("fingerprint") or ""),
    )


def dedupe_findings(findings: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    unique: List[Dict[str, Any]] = []
    for finding in sorted(findings, key=finding_sort_key):
        fingerprint = str(finding.get("fingerprint") or "")
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        unique.append(finding)
    return unique


def legacy_issue(finding: Dict[str, Any]) -> Dict[str, Any]:
    location = finding.get("location") or {}
    legacy = {
        "severity": "error" if finding.get("severity") == "blocker" else finding.get("severity"),
        "code": finding.get("code"),
        "message": finding.get("message"),
    }
    if location.get("path") is not None:
        legacy["path"] = location.get("path")
    if location.get("line") is not None:
        legacy["line"] = location.get("line")
    return legacy


def evidence_manifest_for(skill_dir: Path, root: Path, include_generated: bool = True) -> List[Dict[str, Any]]:
    manifest: List[Dict[str, Any]] = []
    skill_file = skill_dir / "SKILL.md"
    if skill_file.exists():
        manifest.append({"path": relpath(skill_file, root), "kind": "primary", "exists": True})
    for dirname in sorted(SUPPORT_DIRS):
        support_root = skill_dir / dirname
        if not support_root.exists():
            continue
        for path in sorted(support_root.rglob("*")):
            if path.is_file():
                generated = is_generated_artifact(path)
                if generated and not include_generated:
                    continue
                manifest.append({"path": relpath(path, root), "kind": dirname, "exists": True, "generated": generated})
    return manifest


def is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES


def is_generated_artifact(path: Path) -> bool:
    parts = set(path.parts)
    if parts & GENERATED_DIR_NAMES:
        return True
    if path.name in {".DS_Store"}:
        return True
    if path.suffix.lower() in GENERATED_SUFFIXES:
        return True
    return False


def is_test_fixture_path(path: Path, root: Path) -> bool:
    rel = relpath(path, root)
    return rel.startswith("tests/fixtures/")


def support_files(skill_dir: Path, include_generated: bool = False) -> List[Path]:
    paths: List[Path] = []
    for dirname in SUPPORT_DIRS:
        root = skill_dir / dirname
        if root.exists():
            for path in sorted(root.rglob("*")):
                if path.is_file() and (include_generated or not is_generated_artifact(path)):
                    paths.append(path)
    return paths


def scan_generated_artifacts(skill_dir: Path, root: Path) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for path in sorted(skill_dir.rglob("*")):
        if is_generated_artifact(path):
            findings.append(
                make_finding(
                    "GENERATED_ARTIFACT",
                    "blocker",
                    "source_runtime_correctness",
                    "generated/runtime artifact found under skill directory",
                    path,
                    evidence={"kind": "artifact", "name": path.name},
                    suggested_fix="Remove generated artifacts from the skill tree and run tests with bytecode/cache disabled.",
                    root=root,
                )
            )
    return findings


def scan_stale_paths(paths: Iterable[Path], root: Path) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for path in paths:
        if path.is_dir() or not path.exists() or not is_text_file(path):
            continue
        in_code_fence = False
        for index, line in enumerate(safe_read_lines(path), start=1):
            stripped = line.strip()
            if stripped.startswith("```"):
                in_code_fence = not in_code_fence
            for pattern in STALE_PATH_PATTERNS:
                normalized_literal = stripped.rstrip(",").strip('"').strip("'")
                if normalized_literal == pattern:
                    continue
                if pattern in line and not INTENTIONAL_STALE_CONTEXT_RE.search(line):
                    severity = "blocker" if in_code_fence else "warning"
                    findings.append(
                        make_finding(
                            "STALE_PATH",
                            severity,
                            "source_runtime_correctness",
                            "stale source/runtime path reference",
                            path,
                            index,
                            evidence={"kind": "path", "value": pattern, "redacted": False},
                            suggested_fix="Update the path to the current source/runtime location or mark it as an intentional stale-path guard.",
                            root=root,
                        )
                    )
    return findings


def is_placeholder_secret(value: str, line: str) -> bool:
    lower = value.lower()
    if "[redacted]" in line.lower() or "os.getenv" in line:
        return True
    if lower in {"redacted", "placeholder", "changeme", "example", "dummy"}:
        return True
    if lower.startswith(("your_", "example_", "placeholder_")):
        return True
    if value.startswith("$") or (value.startswith("${") and value.endswith("}")):
        return True
    if re.fullmatch(r"[A-Z0-9_]*(TOKEN|SECRET|PASSWORD|PASS|KEY|DSN|URL)[A-Z0-9_]*", value):
        return True
    return False


def scan_secret_lines(paths: Iterable[Path], root: Path, severity: str = "blocker") -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for path in paths:
        if path.is_dir() or not path.exists() or not is_text_file(path):
            continue
        for index, line in enumerate(safe_read_lines(path), start=1):
            match = SECRET_LINE_RE.search(line)
            if not match:
                continue
            value = match.group(2)
            if is_placeholder_secret(value, line):
                continue
            findings.append(
                make_finding(
                    "SECRET_LIKE_VALUE",
                    severity,
                    "safety",
                    "credential-shaped assignment found; value redacted",
                    path,
                    index,
                    evidence={"kind": "secret_detector", "detector": match.group(1).lower(), "value": "[REDACTED]", "redacted": True},
                    suggested_fix="Replace real values with [REDACTED] or documented environment variable placeholders.",
                    root=root,
                )
            )
    return findings


def scan_unsafe_secret_scan_commands(paths: Iterable[Path], root: Path, severity: str = "blocker") -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for path in paths:
        if path.is_dir() or not path.exists() or not is_text_file(path):
            continue
        previous_nonempty = ""
        for index, line in enumerate(safe_read_lines(path), start=1):
            stripped = line.strip()
            lower = stripped.lower()
            previous_lower = previous_nonempty.lower()
            grep_sensitive_match = "grep" in lower and SECRET_KEYWORD_RE.search(stripped)
            same_line_diff = "git diff" in lower or "git show" in lower or '"^+"' in lower or "'^+'" in lower
            previous_line_diff = "git diff" in previous_lower or "git show" in previous_lower or previous_lower.endswith("|")
            is_diff_grep_pipeline = bool(grep_sensitive_match and (same_line_diff or previous_line_diff))
            combined_context = f"{previous_nonempty} {stripped}".strip()
            if is_diff_grep_pipeline and not INTENTIONAL_UNSAFE_SCAN_CONTEXT_RE.search(combined_context):
                findings.append(
                    make_finding(
                        "UNSAFE_SECRET_SCAN",
                        severity,
                        "safety",
                        "grep-based sensitive-value scan can print matched values; use metadata-only redacting scan",
                        path,
                        index,
                        evidence={"kind": "unsafe_command", "value": "[REDACTED]", "redacted": True},
                        suggested_fix="Use audit_skill.py --changed --json or another metadata-only redacting scanner.",
                        root=root,
                    )
                )
            if stripped:
                previous_nonempty = stripped
    return findings


def scan_markdown_links(paths: Iterable[Path], root: Path) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for path in paths:
        if path.suffix.lower() != ".md" or not path.exists():
            continue
        for index, line in enumerate(safe_read_lines(path), start=1):
            for match in MARKDOWN_LINK_RE.finditer(line):
                raw_target = match.group(1).strip()
                target = raw_target.split()[0].strip('"').strip("'")
                if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                target_no_fragment = target.split("#", 1)[0]
                if not target_no_fragment:
                    continue
                candidate = (path.parent / target_no_fragment).resolve()
                if not candidate.exists():
                    findings.append(
                        make_finding(
                            "BROKEN_MARKDOWN_LINK",
                            "warning",
                            "documentation_health",
                            "relative markdown link target does not exist",
                            path,
                            index,
                            evidence={"kind": "path", "value": target_no_fragment, "redacted": False},
                            suggested_fix="Update the link target or add the referenced support file.",
                            root=root,
                        )
                    )
    return findings


def scan_python_syntax(paths: Iterable[Path], root: Path) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for path in paths:
        if path.suffix.lower() != ".py" or is_generated_artifact(path):
            continue
        try:
            ast.parse(read_text(path), filename=str(path))
        except SyntaxError as exc:
            findings.append(
                make_finding(
                    "SCRIPT_SYNTAX_ERROR",
                    "blocker",
                    "executability",
                    "Python file has invalid syntax",
                    path,
                    exc.lineno,
                    exc.offset,
                    evidence={"kind": "syntax_error", "value": exc.msg, "redacted": False},
                    suggested_fix="Fix the Python syntax error; use ast.parse or py_compile with bytecode disabled.",
                    root=root,
                )
            )
    return findings


def scan_empty_support_files(paths: Iterable[Path], root: Path) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for path in paths:
        if path.is_file() and not is_generated_artifact(path):
            try:
                if path.stat().st_size == 0:
                    findings.append(
                        make_finding(
                            "EMPTY_SUPPORT_FILE",
                            "warning",
                            "support_file_integrity",
                            "support file is empty",
                            path,
                            evidence={"kind": "file", "value": path.name, "redacted": False},
                            suggested_fix="Remove the file or add the intended content.",
                            root=root,
                        )
                    )
            except OSError:
                continue
    return findings


def scan_read_only_contract(paths: Iterable[Path], root: Path) -> List[Dict[str, Any]]:
    patterns = [
        (re.compile(r"\bgit\s+(add|commit|checkout|reset)\b"), "git mutation command"),
        (re.compile(r"\bchmod\s+-R\b"), "recursive permission change"),
        (re.compile(r"\brm\s+-rf\b"), "recursive deletion command"),
        (re.compile(r"\bsystemctl\s+(restart|stop|start)\b"), "service mutation command"),
        (re.compile(r"\bcurl\b.*\|\s*(sh|bash)\b"), "pipe-to-shell command"),
    ]
    intentional = re.compile(r"(?i)(do not|don't|must not|rollback|example|detect|reject|forbidden|block)")
    findings: List[Dict[str, Any]] = []
    for path in paths:
        if not path.exists() or not is_text_file(path):
            continue
        for index, line in enumerate(safe_read_lines(path), start=1):
            for regex, description in patterns:
                if regex.search(line) and not intentional.search(line):
                    findings.append(
                        make_finding(
                            "READ_ONLY_CONTRACT_RISK",
                            "warning",
                            "safety",
                            "command may violate read-only audit contract",
                            path,
                            index,
                            evidence={"kind": "command_pattern", "value": description, "redacted": False},
                            suggested_fix="Keep audit helpers read-only or move mutating actions behind explicit human-approved workflows.",
                            root=root,
                        )
                    )
    return findings


def count_support_files(skill_dir: Path, dirname: str) -> int:
    root_dir = skill_dir / dirname
    if not root_dir.exists():
        return 0
    return sum(1 for path in root_dir.rglob("*") if path.is_file() and not is_generated_artifact(path))




CLI_STATIC_SKIP_REASON = "Step 1 implements static inventory only; doctor/help/tests/schema runtime validation not executed."
JSON_CLAIM_RE = re.compile(r"(?i)(--json|json output|\bJSON\b|\bschema\b|\bcontract\b|\bdoctor\b|\bok\b|\bissues\b|error\.code)")
MUTATION_CANDIDATE_RE = re.compile(
    r"(?i)(--apply|--yes|--force|--delete|--write|\bdeploy\b|\binstall\b|\bremove\b|\bunlink\b|rmtree|write_text|open\([^\n]*['\"]w['\"]|requests\.(post|put|delete)|systemctl|git\s+push)"
)
WRAPPER_CANDIDATE_RE = re.compile(r"(?i)(\balias\b|\bcron\b|python\s+-m\s+[\w.:-]+|\b[A-Z][A-Z0-9_]+\s*=|fallback|legacy|old command|wrapper)")
PYTHON_MODULE_SNIPPET_RE = re.compile(r"python\s+-m\s+([A-Za-z_][\w.]*)")
LIKELY_WRAPPER_RE = re.compile(r"(?m)(?:^|[\s`])([a-zA-Z][\w-]*(?:-cli|ctl|doctor|audit|check|lint))(?:\s|$)")


def import_toml_loader():
    try:
        import tomllib  # type: ignore
    except ImportError:  # pragma: no cover - Python <3.11 fallback
        try:
            import tomli as tomllib  # type: ignore
        except ImportError:
            return None
    return tomllib


def read_pyproject(pyproject: Path) -> Dict[str, Any]:
    loader = import_toml_loader()
    if loader is None or not pyproject.exists():
        return {}
    try:
        with pyproject.open("rb") as handle:
            data = loader.load(handle)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def unique_dicts(items: Iterable[Dict[str, Any]], keys: Sequence[str]) -> List[Dict[str, Any]]:
    seen: set[Tuple[Any, ...]] = set()
    result: List[Dict[str, Any]] = []
    for item in items:
        marker = tuple(item.get(key) for key in keys)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result


def truncate_error(value: str, limit: int = 240) -> str:
    value = redact_sensitive_text(value).replace("\n", " ").strip()
    return value if len(value) <= limit else value[: limit - 3] + "..."


def detect_schema_dialect(schema_keyword: Optional[str]) -> Optional[str]:
    if not schema_keyword:
        return None
    value = schema_keyword.strip().lower().rstrip("#")
    if value == "https://json-schema.org/draft/2020-12/schema" or "draft/2020-12" in value or "draft2020-12" in value:
        return "draft2020-12"
    if value == "https://json-schema.org/draft/2019-09/schema" or "draft/2019-09" in value or "draft2019-09" in value:
        return "draft2019-09"
    if "draft-07" in value or "draft/07" in value:
        return "draft-07"
    return "unknown"


def infer_version_hint(filename: str, schema_id: Optional[str], title: Optional[str] = None) -> Optional[str]:
    for value in (filename, schema_id or "", title or ""):
        match = re.search(r"(?i)(?:^|[._/-])(v\d+)(?:[._/-]|$)", value)
        if match:
            return match.group(1).lower()
    return None


def schema_type_name(value: Any) -> str:
    if isinstance(value, list):
        return "mixed"
    if isinstance(value, str):
        if value in {"object", "array", "string", "number", "integer", "boolean", "null"}:
            return "number" if value == "integer" else value
        return "unknown"
    return "unknown"


def schema_defs_count(data: Dict[str, Any]) -> int:
    total = 0
    for key in ("$defs", "definitions"):
        value = data.get(key)
        if isinstance(value, dict):
            total += len(value)
    return total


def object_policy(value: Dict[str, Any]) -> Optional[str]:
    value_type = value.get("type")
    object_like = value_type == "object" or isinstance(value.get("properties"), dict) or isinstance(value.get("required"), list)
    if not object_like:
        return None
    if "additionalProperties" not in value:
        return "unspecified"
    additional = value.get("additionalProperties")
    if additional is False:
        return "closed"
    if additional is True:
        return "open"
    return "mixed"


def iter_object_schemas(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        if object_policy(value) is not None:
            yield value
        for child in value.values():
            yield from iter_object_schemas(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_object_schemas(child)


def additional_properties_policy(data: Optional[Dict[str, Any]]) -> str:
    if not isinstance(data, dict):
        return "unknown"
    root_policy = object_policy(data)
    if root_policy is None:
        return "unknown"
    policies = [policy for schema in iter_object_schemas(data) for policy in [object_policy(schema)] if policy is not None]
    if len(set(policies)) > 1:
        return "mixed"
    return root_policy


def schema_like(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    return any(key in data for key in ("$schema", "$id", "id", "type", "properties", "required", "$defs", "definitions", "additionalProperties"))


def meta_validate_schema(data: Any, json_valid: bool) -> Dict[str, Any]:
    if not json_valid:
        return {"performed": False, "status": "skipped", "validator": "none", "error": "JSON parse failed; schema meta-validation skipped"}
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return {"performed": False, "status": "skipped", "validator": "none", "skipped_reason": "jsonschema library unavailable", "error": None}
    try:
        validator = jsonschema.validators.validator_for(data)
        validator.check_schema(data)
    except Exception as exc:
        return {"performed": True, "status": "warn", "validator": "jsonschema", "error": truncate_error(str(exc))}
    return {"performed": True, "status": "pass", "validator": "jsonschema", "error": None}


def schema_reference_paths(skill_dir: Path) -> Tuple[List[Path], List[Path]]:
    doc_paths: List[Path] = []
    test_paths: List[Path] = []
    for candidate in [skill_dir / "SKILL.md", *skill_dir.glob("README*")]:
        if candidate.exists() and candidate.is_file():
            doc_paths.append(candidate)
    for dirname in ("references", "templates", "scripts", "cli"):
        root = skill_dir / dirname
        if root.exists():
            for path in root.rglob("*"):
                if not path.is_file() or is_generated_artifact(path):
                    continue
                if "tests" in path.parts:
                    test_paths.append(path)
                else:
                    doc_paths.append(path)
    root_tests = skill_dir / "tests"
    if root_tests.exists():
        test_paths.extend(path for path in root_tests.rglob("*") if path.is_file() and not is_generated_artifact(path))
    return unique_paths(doc_paths), unique_paths(test_paths)


def path_text_contains_reference(paths: Iterable[Path], schema_path: str, filename: str) -> bool:
    basename = filename
    for suffix in (".schema.json", ".json"):
        if basename.endswith(suffix):
            basename = basename[: -len(suffix)]
            break
    needles = {schema_path, filename, basename}
    for path in paths:
        if not path.exists() or not is_text_file(path):
            continue
        text = read_text(path)
        if any(needle and needle in text for needle in needles):
            return True
    return False


def schema_inventory_item(path: Path, skill_dir: Path, scope: str, doc_paths: Sequence[Path], test_paths: Sequence[Path]) -> Dict[str, Any]:
    filename = path.name
    rel = relpath(path, skill_dir)
    raw = b""
    data: Any = None
    json_valid = False
    json_parse_error: Optional[str] = None
    try:
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8"))
        json_valid = True
    except Exception as exc:
        json_parse_error = truncate_error(str(exc))
    schema_keyword: Optional[str] = None
    id_keyword: Optional[str] = None
    title: Optional[str] = None
    type_name = "unknown"
    required_count = 0
    properties_count = 0
    defs_count = 0
    has_schema = False
    has_id = False
    if isinstance(data, dict):
        schema_value = data.get("$schema")
        schema_keyword = str(schema_value) if isinstance(schema_value, str) else None
        id_value = data.get("$id", data.get("id"))
        id_keyword = str(id_value) if isinstance(id_value, str) else None
        has_schema = "$schema" in data
        has_id = "$id" in data or "id" in data
        title_value = data.get("title")
        title = str(title_value) if isinstance(title_value, str) else None
        if "type" in data:
            type_name = schema_type_name(data.get("type"))
        elif isinstance(data.get("properties"), dict):
            type_name = "object"
        required_count = len(data.get("required")) if isinstance(data.get("required"), list) else 0
        properties_count = len(data.get("properties")) if isinstance(data.get("properties"), dict) else 0
        defs_count = schema_defs_count(data)
    meta_validation = meta_validate_schema(data, json_valid)
    return {
        "path": rel,
        "scope": scope,
        "filename": filename,
        "size_bytes": len(raw) if raw else (path.stat().st_size if path.exists() else 0),
        "sha256": hashlib.sha256(raw).hexdigest() if raw else None,
        "json_valid": json_valid,
        "json_parse_error": json_parse_error,
        "schema_like": schema_like(data),
        "dialect": detect_schema_dialect(schema_keyword),
        "dialect_hint": detect_schema_dialect(schema_keyword),
        "schema_keyword": schema_keyword,
        "id_keyword": id_keyword,
        "has_schema_keyword": has_schema,
        "has_id_keyword": has_id,
        "title": title,
        "type": type_name,
        "required_count": required_count,
        "properties_count": properties_count,
        "defs_count": defs_count,
        "additional_properties_policy": additional_properties_policy(data if isinstance(data, dict) else None),
        "version_hint": infer_version_hint(filename, id_keyword, title),
        "referenced_by_docs": path_text_contains_reference([p for p in doc_paths if p.resolve() != path.resolve()], rel, filename),
        "referenced_by_tests": path_text_contains_reference([p for p in test_paths if p.resolve() != path.resolve()], rel, filename),
        "meta_validation": meta_validation,
    }


SCHEMA_OUTPUT_SCAN_IGNORED_DIRS = GENERATED_DIR_NAMES | {".git", "node_modules", "vendor", ".venv", "venv", "dist", "build"}
SCHEMA_OUTPUT_MAX_FILE_BYTES = 512_000
SCHEMA_OUTPUT_SNIPPET_LIMIT = 200
SCHEMA_OUTPUT_WINDOW_LINES = 8
SCHEMA_OUTPUT_DOC_SUFFIXES = {".md", ".txt", ".rst"}
SCHEMA_OUTPUT_COMMAND_RE = re.compile(r"`([^`]*(?:python3?|[A-Za-z0-9_.-]+)[^`]*(?:--json|--agent-brief|doctor)[^`]*)`")
SCHEMA_OUTPUT_FIELD_RE = re.compile(r"\bdata\.[A-Za-z_][A-Za-z0-9_.]*")
SCHEMA_OUTPUT_TERMS_RE = re.compile(
    r"(?i)(--json|--agent-brief|\bemits?\b|\boutput\b|\bpayload\b|structured\s+(?:output|payload)|validated\s+against|\bcontract\b)"
)
SCHEMA_OUTPUT_CODE_EXPLICIT_RE = re.compile(
    r"(?i)(_SCHEMA_RESOURCE\s*=|_SCHEMA_VERSION\b|load_[A-Za-z0-9_]*_schema|validate_[A-Za-z0-9_]*_contract|build_[A-Za-z0-9_]*_contract|importlib\.resources\.files|\.joinpath\()"
)
SCHEMA_OUTPUT_TEST_EXPLICIT_RE = re.compile(
    r"(?i)(load|schema_resource|validate_[A-Za-z0-9_]*|build_[A-Za-z0-9_]*|schema_version|\$id|payload|assert)"
)
SCHEMA_OUTPUT_REPORT_HINT_RE = re.compile(r"(?i)(audit\s+report|--json|validate_audit_report|validate_cli_doctor_envelope|doctor\s+envelope)")
SCHEMA_OUTPUT_GENERIC_TOKENS = {"json", "schema", "contract", "doctor", "report", "output"}


def schema_output_schema_path(item: Dict[str, Any]) -> Optional[str]:
    value = item.get("path") or item.get("schema_path")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.replace("\\", "/").lstrip("/")


def schema_output_basename(filename: str) -> str:
    base = filename
    for suffix in (".schema.json", ".json"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    base = re.sub(r"(?i)(?:[._-]v\d+)$", "", base)
    return base.replace("-", "_")


def schema_output_schema_version(filename: str) -> str:
    version = filename
    for suffix in (".schema.json", ".json"):
        if version.endswith(suffix):
            version = version[: -len(suffix)]
            break
    return version


def schema_output_tokens(schema_path: str, filename: str) -> List[str]:
    version = schema_output_schema_version(filename)
    tokens = {schema_path, filename}
    if version.lower() not in SCHEMA_OUTPUT_GENERIC_TOKENS:
        tokens.add(version)
    return [token for token in tokens if token]


def contains_exact_schema_token(text: str, token: str) -> bool:
    if not token:
        return False
    pattern = rf"(?<![A-Za-z0-9_-]){re.escape(token)}(?![A-Za-z0-9_-])"
    return re.search(pattern, text) is not None


def has_exact_schema_identity(text: str, filename: str, schema_version: str) -> bool:
    if contains_exact_schema_token(text, filename):
        return True
    if schema_version.lower() in SCHEMA_OUTPUT_GENERIC_TOKENS:
        return False
    return contains_exact_schema_token(text, schema_version)


def bounded_schema_output_snippet(line: str) -> str:
    snippet = redact_sensitive_text(line.strip())
    if len(snippet) > SCHEMA_OUTPUT_SNIPPET_LIMIT:
        snippet = snippet[: SCHEMA_OUTPUT_SNIPPET_LIMIT - 3] + "..."
    return snippet


def schema_output_evidence(path: Path, skill_dir: Path, line_no: int, line: str) -> Dict[str, Any]:
    return {"path": relpath(path, skill_dir), "line": line_no, "snippet": bounded_schema_output_snippet(line)}


def iter_schema_output_text_files(skill_dir: Path) -> List[Path]:
    root = skill_dir.resolve()
    paths: List[Path] = []
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file():
            continue
        if set(path.parts) & SCHEMA_OUTPUT_SCAN_IGNORED_DIRS:
            continue
        try:
            resolved = path.resolve()
            resolved.relative_to(root)
            if path.stat().st_size > SCHEMA_OUTPUT_MAX_FILE_BYTES:
                continue
        except (OSError, ValueError):
            continue
        if is_text_file(path):
            paths.append(path)
    return paths


def schema_output_file_role(path: Path) -> str:
    if "tests" in path.parts or path.name.startswith("test_"):
        return "tests"
    if path.suffix.lower() == ".py":
        return "code"
    if path.suffix.lower() in SCHEMA_OUTPUT_DOC_SUFFIXES or path.name.lower().startswith("readme") or path.name == "SKILL.md":
        return "docs"
    return "other"


def window_for_line(lines: Sequence[str], index: int, radius: int = SCHEMA_OUTPUT_WINDOW_LINES) -> Tuple[int, int, str]:
    start = max(0, index - radius)
    end = min(len(lines), index + radius + 1)
    return start, end, "\n".join(lines[start:end])


def references_any_schema_token(text: str, tokens: Sequence[str]) -> bool:
    return any(contains_exact_schema_token(text, token) for token in tokens)


def extract_schema_output_name(text: str, filename: str) -> str:
    field_match = SCHEMA_OUTPUT_FIELD_RE.search(text)
    if field_match:
        return field_match.group(0)
    base = schema_output_basename(filename)
    return f"data.{base}" if base else "unknown"


def infer_schema_output_scope(text: str, filename: str) -> str:
    lower = f"{text}\n{filename}".lower()
    if "audit-report" in lower or "audit report" in lower or "cli-doctor-envelope" in lower or "doctor envelope" in lower:
        return "report_contract"
    if "final answer" in lower or "user answer" in lower or "user_answer" in lower or "answer_contract" in lower:
        return "final_answer_contract"
    if "--json" in lower or "--agent-brief" in lower or "cli" in lower or "emits" in lower or "output" in lower:
        return "cli_output"
    return "unknown"


def extract_schema_output_command_hint(text: str) -> Optional[str]:
    match = SCHEMA_OUTPUT_COMMAND_RE.search(text)
    if not match:
        return None
    command = redact_sensitive_text(match.group(1)).strip()
    return command[: SCHEMA_OUTPUT_SNIPPET_LIMIT - 3] + "..." if len(command) > SCHEMA_OUTPUT_SNIPPET_LIMIT else command


def schema_output_has_builder_or_validator(text: str, base: str) -> bool:
    normalized = base.replace("-", "_").replace(".", "_")
    if not normalized or normalized.lower() in SCHEMA_OUTPUT_GENERIC_TOKENS:
        return False
    candidates = {normalized}
    pieces = [piece for piece in re.split(r"[_\-.]+", normalized) if piece and not re.fullmatch(r"v\d+", piece, re.I)]
    if len(pieces) >= 2:
        candidates.add("_".join(pieces[-2:]))
    for candidate in candidates:
        pattern = rf"(?i)\b(?:build|validate|load)_[A-Za-z0-9_]*{re.escape(candidate)}[A-Za-z0-9_]*(?:_contract|_schema)?\b"
        if re.search(pattern, text):
            return True
    return False


def make_schema_output_mapping(
    schema_path: str,
    output_name: str,
    command_hint: Optional[str],
    mapping_kind: str,
    confidence: str,
    scope: str,
    evidence: Sequence[Dict[str, Any]],
    notes: str,
) -> Dict[str, Any]:
    unique_evidence = unique_dicts(list(evidence), ["path", "line", "snippet"])
    return {
        "schema_path": schema_path,
        "output_name": output_name,
        "command_hint": command_hint,
        "mapping_kind": mapping_kind,
        "confidence": confidence,
        "scope": scope,
        "evidence": unique_evidence[:5],
        "notes": notes[:240],
    }


def schema_output_mapping_priority(mapping: Dict[str, Any]) -> Tuple[int, int]:
    kind = mapping.get("mapping_kind")
    scope = mapping.get("scope")
    confidence = mapping.get("confidence")
    has_command = bool(mapping.get("command_hint"))
    if kind == "docs_explicit" and scope == "cli_output" and has_command:
        return (0, 0)
    if kind == "report_contract":
        return (1, 0)
    if kind == "code_explicit" and confidence == "high":
        return (2, 0)
    if kind == "tests_explicit" and confidence == "high":
        return (3, 0)
    if kind == "naming_inference":
        return (4, 0)
    if kind == "docs_explicit":
        return (5, 0)
    return (9, 0)


def detect_schema_output_mappings(skill_dir: Path, schema_items: list[dict]) -> list[dict]:
    """Statically detect likely schema-to-output mappings under ``skill_dir``.

    The detector is read-only and bounded: it never executes commands, skips large
    or generated files, only inspects text files inside ``skill_dir``, and stores
    short redacted evidence snippets.
    """
    if not schema_items:
        return []
    root = skill_dir.resolve()
    if not skill_dir.exists() or not skill_dir.is_dir():
        return []
    files = iter_schema_output_text_files(skill_dir)
    file_lines: Dict[Path, List[str]] = {path: safe_read_lines(path) for path in files}
    mappings: List[Dict[str, Any]] = []

    for item in schema_items:
        schema_path = schema_output_schema_path(item)
        if not schema_path:
            continue
        schema_abs = (skill_dir / schema_path).resolve()
        try:
            schema_abs.relative_to(root)
        except ValueError:
            continue
        filename = str(item.get("filename") or Path(schema_path).name)
        schema_version = schema_output_schema_version(filename)
        tokens = schema_output_tokens(schema_path, filename)
        base = schema_output_basename(filename)
        report_evidence: List[Dict[str, Any]] = []
        docs_evidence: List[Dict[str, Any]] = []
        code_evidence: List[Dict[str, Any]] = []
        tests_evidence: List[Dict[str, Any]] = []
        naming_evidence: List[Dict[str, Any]] = []
        docs_context = ""
        code_context = ""
        tests_context = ""

        is_report_schema = schema_path in {"schemas/audit-report.schema.json", "schemas/cli-doctor-envelope.v1.schema.json"}

        for path, lines in file_lines.items():
            if path.resolve() == schema_abs:
                continue
            role = schema_output_file_role(path)
            full_text = "\n".join(lines)
            has_exact_identity = has_exact_schema_identity(full_text, filename, schema_version) or schema_path in full_text
            has_schema_ref = references_any_schema_token(full_text, tokens)
            if not has_schema_ref and role in {"code", "tests"} and base and schema_output_has_builder_or_validator(full_text, base):
                for line_no, line in enumerate(lines, start=1):
                    if schema_output_has_builder_or_validator(line, base):
                        naming_evidence.append(schema_output_evidence(path, skill_dir, line_no, line))
                        break

            for idx, line in enumerate(lines):
                line_has_schema_ref = references_any_schema_token(line, tokens)
                if role in {"code", "tests"}:
                    line_has_schema_ref = has_exact_schema_identity(line, filename, schema_version) or schema_path in line
                if not line_has_schema_ref:
                    continue
                start, end, window = window_for_line(lines, idx)
                line_no = idx + 1
                evidence = schema_output_evidence(path, skill_dir, line_no, line)
                if is_report_schema and (SCHEMA_OUTPUT_REPORT_HINT_RE.search(window) or path.name in {"validate_audit_report.py", "audit_skill.py"}):
                    report_evidence.append(evidence)
                    report_hint_lines = [schema_output_evidence(path, skill_dir, i + 1, lines[i]) for i in range(start, end) if SCHEMA_OUTPUT_REPORT_HINT_RE.search(lines[i])]
                    report_evidence.extend(report_hint_lines[:2])
                elif role == "docs" and SCHEMA_OUTPUT_TERMS_RE.search(window):
                    docs_evidence.append(evidence)
                    docs_context += "\n" + window
                elif (
                    role == "code"
                    and has_exact_identity
                    and SCHEMA_OUTPUT_CODE_EXPLICIT_RE.search(window)
                    and schema_output_has_builder_or_validator(full_text, base)
                ):
                    code_evidence.append(evidence)
                    for i in range(start, end):
                        if SCHEMA_OUTPUT_CODE_EXPLICIT_RE.search(lines[i]) or schema_output_has_builder_or_validator(lines[i], base):
                            code_evidence.append(schema_output_evidence(path, skill_dir, i + 1, lines[i]))
                    code_context += "\n" + full_text
                elif role == "tests" and has_exact_identity and SCHEMA_OUTPUT_TEST_EXPLICIT_RE.search(window):
                    tests_evidence.append(evidence)
                    for i in range(start, end):
                        if SCHEMA_OUTPUT_TEST_EXPLICIT_RE.search(lines[i]):
                            tests_evidence.append(schema_output_evidence(path, skill_dir, i + 1, lines[i]))
                    tests_context += "\n" + window

        candidates: List[Dict[str, Any]] = []
        if report_evidence:
            candidates.append(
                make_schema_output_mapping(
                    schema_path,
                    "audit_report" if schema_path.endswith("audit-report.schema.json") else "cli_doctor_envelope",
                    None,
                    "report_contract",
                    "high",
                    "report_contract",
                    report_evidence,
                    "Central auditor report/envelope schema is explicitly referenced by validator or audit script.",
                )
            )
        if docs_evidence:
            candidates.append(
                make_schema_output_mapping(
                    schema_path,
                    extract_schema_output_name(docs_context, filename),
                    extract_schema_output_command_hint(docs_context),
                    "docs_explicit",
                    "high",
                    infer_schema_output_scope(docs_context, filename),
                    docs_evidence,
                    "Documentation references the exact schema identity near output or command terms.",
                )
            )
        if code_evidence:
            candidates.append(
                make_schema_output_mapping(
                    schema_path,
                    extract_schema_output_name(code_context, filename),
                    None,
                    "code_explicit",
                    "high",
                    infer_schema_output_scope(code_context, filename),
                    code_evidence,
                    "Code references the exact schema resource/version in the same file as matching builder/validator helpers.",
                )
            )
        if tests_evidence:
            candidates.append(
                make_schema_output_mapping(
                    schema_path,
                    extract_schema_output_name(tests_context, filename),
                    None,
                    "tests_explicit",
                    "high",
                    infer_schema_output_scope(tests_context, filename),
                    tests_evidence,
                    "Tests reference the exact schema identity and validate/build/assert a structured payload.",
                )
            )
        if naming_evidence:
            context = "\n".join(ev["snippet"] for ev in naming_evidence)
            candidates.append(
                make_schema_output_mapping(
                    schema_path,
                    extract_schema_output_name(context, filename),
                    None,
                    "naming_inference",
                    "medium",
                    infer_schema_output_scope(context, filename),
                    naming_evidence,
                    "Schema filename strongly matches builder/validator names, but no direct schema path reference was found.",
                )
            )
        if candidates:
            mappings.append(sorted(candidates, key=schema_output_mapping_priority)[0])
    return mappings

def schema_output_mappings_summary(mappings: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    by_scope = {
        "cli_output": 0,
        "report_contract": 0,
        "final_answer_contract": 0,
        "unknown": 0,
    }
    summary: Dict[str, Any] = {
        "total": len(mappings),
        "high": 0,
        "medium": 0,
        "low": 0,
        "by_scope": by_scope,
    }
    for mapping in mappings:
        confidence = mapping.get("confidence")
        if confidence in {"high", "medium", "low"}:
            summary[str(confidence)] += 1
        scope = mapping.get("scope")
        if scope in by_scope:
            by_scope[str(scope)] += 1
        else:
            by_scope["unknown"] += 1
    return summary


def collect_schema_inventory(skill_dir: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    doc_paths, test_paths = schema_reference_paths(skill_dir)
    top_level: List[Dict[str, Any]] = []
    top_root = skill_dir / "schemas"
    if top_root.exists():
        for path in sorted({*top_root.rglob("*.schema.json"), *top_root.rglob("*.json")}):
            if path.is_file() and not is_generated_artifact(path):
                top_level.append(schema_inventory_item(path, skill_dir, "top_level", doc_paths, test_paths))
    cli_contract: List[Dict[str, Any]] = []
    cli_root = skill_dir / "cli"
    if cli_root.exists():
        candidates: set[Path] = set()
        candidates.update(path for path in cli_root.rglob("*.schema.json") if path.is_file())
        for dirname in ("contracts", "schemas"):
            for directory in cli_root.rglob(dirname):
                if directory.is_dir():
                    candidates.update(path for path in directory.rglob("*.json") if path.is_file())
        for path in sorted(candidates):
            if not is_generated_artifact(path):
                cli_contract.append(schema_inventory_item(path, skill_dir, "cli_contract", doc_paths, test_paths))
    return top_level, cli_contract


def classify_json_claim(line: str) -> str:
    lower = line.lower()
    if "--json" in lower:
        return "json_flag"
    if "doctor" in lower:
        return "doctor_command"
    if "schema" in lower or "contract" in lower:
        return "schema_reference"
    if "ok" in lower or "issues" in lower or "error.code" in lower:
        return "json_envelope"
    return "generic"


def collect_line_matches(paths: Iterable[Path], skill_dir: Path, regex: re.Pattern[str], claim: bool = False) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    for path in sorted(paths):
        if not path.exists() or path.is_dir() or not is_text_file(path):
            continue
        for line_no, line in enumerate(safe_read_lines(path), start=1):
            if not regex.search(line):
                continue
            snippet = line.strip()
            if len(snippet) > 180:
                snippet = snippet[:177] + "..."
            item = {"path": relpath(path, skill_dir), "line": line_no, "snippet": snippet}
            if claim:
                item["claim_type"] = classify_json_claim(line)
            matches.append(item)
    return matches


def docs_and_cli_scan_paths(skill_dir: Path) -> List[Path]:
    paths: List[Path] = []
    for candidate in [skill_dir / "SKILL.md", skill_dir / "README.md", skill_dir / "README"]:
        if candidate.exists():
            paths.append(candidate)
    for dirname in ("references", "docs", "templates", "scripts", "cli", "tests"):
        root = skill_dir / dirname
        if root.exists():
            paths.extend(path for path in root.rglob("*") if path.is_file() and not is_generated_artifact(path))
    paths.extend(path for path in skill_dir.glob("README*") if path.is_file())
    return unique_paths(paths)


def wrapper_scan_paths(skill_dir: Path) -> List[Path]:
    paths: List[Path] = []
    for candidate in [skill_dir / "SKILL.md", *skill_dir.glob("README*")]:
        if candidate.exists() and candidate.is_file():
            paths.append(candidate)
    for dirname in ("scripts", "bin", "cli", "references"):
        root = skill_dir / dirname
        if root.exists():
            paths.extend(path for path in root.rglob("*") if path.is_file())
    return unique_paths(paths)


def unique_paths(paths: Iterable[Path]) -> List[Path]:
    seen: set[Path] = set()
    result: List[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append(path)
    return result


def entrypoint(kind: str, name: Optional[str], module: Optional[str], path: Optional[str], confidence: str, source: str) -> Dict[str, Any]:
    return {"kind": kind, "name": name, "module": module, "path": path, "confidence": confidence, "source": source}


def collect_cli_entrypoints(skill_dir: Path) -> List[Dict[str, Any]]:
    cli_dir = skill_dir / "cli"
    items: List[Dict[str, Any]] = []
    pyproject = cli_dir / "pyproject.toml"
    data = read_pyproject(pyproject)
    project = data.get("project") if isinstance(data.get("project"), dict) else {}
    scripts = project.get("scripts") if isinstance(project.get("scripts"), dict) else {}
    for name, target in sorted(scripts.items()):
        target_str = str(target)
        module = target_str.split(":", 1)[0]
        items.append(entrypoint("project_script", str(name), module, relpath(pyproject, skill_dir), "high", "pyproject"))
    packages = project.get("packages") if isinstance(project.get("packages"), list) else []
    if packages:
        for package in packages:
            items.append(entrypoint("python_module", None, str(package), relpath(pyproject, skill_dir), "medium", "pyproject"))
    for table_name in ("tool",):
        if table_name in data:
            # Pyproject contains package/build hints, but no standardized script. Keep a low-noise module hint.
            build_system = data.get("build-system") if isinstance(data.get("build-system"), dict) else None
            if build_system:
                items.append(entrypoint("unknown", None, None, relpath(pyproject, skill_dir), "low", "pyproject"))
                break
    main_path = cli_dir / "__main__.py"
    if main_path.exists():
        items.append(entrypoint("python_file", "__main__", None, relpath(main_path, skill_dir), "high", "filesystem"))
    for path in sorted(cli_dir.rglob("*_cli.py")):
        if path.is_file() and not is_generated_artifact(path):
            module = relpath(path.with_suffix(""), cli_dir).replace("/", ".")
            items.append(entrypoint("python_file", path.name, module, relpath(path, skill_dir), "medium", "filesystem"))
    for path in docs_and_cli_scan_paths(skill_dir):
        if not path.exists() or not is_text_file(path):
            continue
        for line in safe_read_lines(path):
            for match in PYTHON_MODULE_SNIPPET_RE.finditer(line):
                items.append(entrypoint("python_module", None, match.group(1), relpath(path, skill_dir), "medium", "docs"))
            for match in LIKELY_WRAPPER_RE.finditer(line):
                name = match.group(1)
                if name in {"json", "schema", "contract", "doctor"}:
                    continue
                items.append(entrypoint("docs_mention", name, None, relpath(path, skill_dir), "low", "docs"))
    return unique_dicts(items, ["kind", "name", "module", "path", "source"])


def collect_cli_inventory(skill_dir: Path, top_level_schemas: List[Dict[str, Any]], cli_contract_schemas: List[Dict[str, Any]]) -> Dict[str, Any]:
    cli_dir = skill_dir / "cli"
    exists = cli_dir.exists()
    pyproject = cli_dir / "pyproject.toml"
    inventory: Dict[str, Any] = {
        "exists": exists,
        "path": "cli/" if exists else None,
        "pyproject": "cli/pyproject.toml" if pyproject.exists() else None,
        "entrypoints": [],
        "python_files": [],
        "test_dirs": [],
        "contract_schemas": cli_contract_schemas,
        "json_files": [],
        "docs_mentions": [],
        "json_output_claims": [],
        "mutating_command_candidates": [],
        "wrapper_candidates": [],
    }
    if not exists:
        return inventory
    inventory["python_files"] = sorted(relpath(path, skill_dir) for path in cli_dir.rglob("*.py") if path.is_file() and not is_generated_artifact(path))
    inventory["test_dirs"] = sorted(relpath(path, skill_dir) for path in cli_dir.rglob("tests") if path.is_dir())
    inventory["json_files"] = sorted(relpath(path, skill_dir) for path in cli_dir.rglob("*.json") if path.is_file() and not is_generated_artifact(path))
    inventory["entrypoints"] = collect_cli_entrypoints(skill_dir)
    docs_paths = docs_and_cli_scan_paths(skill_dir)
    inventory["json_output_claims"] = collect_line_matches(docs_paths, skill_dir, JSON_CLAIM_RE, claim=True)
    inventory["docs_mentions"] = [item for item in inventory["json_output_claims"] if item.get("path", "").endswith((".md", "README"))]
    inventory["mutating_command_candidates"] = collect_line_matches(docs_paths, skill_dir, MUTATION_CANDIDATE_RE, claim=False)
    wrapper_items = collect_line_matches(wrapper_scan_paths(skill_dir), skill_dir, WRAPPER_CANDIDATE_RE, claim=False)
    for path in wrapper_scan_paths(skill_dir):
        if path.suffix.lower() == ".sh" or os.access(path, os.X_OK):
            wrapper_items.append({"path": relpath(path, skill_dir), "line": None, "snippet": "executable_or_shell_file"})
    inventory["wrapper_candidates"] = unique_dicts(wrapper_items, ["path", "line", "snippet"])
    return inventory


def cli_contract_check(cli_inventory: Dict[str, Any]) -> Dict[str, Any]:
    exists = bool(cli_inventory.get("exists"))
    inventory_status = "pass" if exists else "not_applicable"
    return {
        "status": "pass" if exists else "not_applicable",
        "mode": "static",
        "enforced": False,
        "execution_performed": False,
        "skipped_executable_checks_reason": CLI_STATIC_SKIP_REASON,
        "inventory_status": inventory_status,
    }


MUTATING_ARG_VALUES = {"--apply", "--yes", "--force", "--delete", "--write", "--install", "--deploy", "--send", "--commit", "--push"}
MUTATING_VERB_VALUES = {"apply", "force", "delete", "write", "install", "deploy", "send", "commit", "push", "remove", "unlink"}
MUTATING_EXECUTABLES = {"rm", "mv", "systemctl"}
CLI_DEEP_NO_EXEC_REASON = "--no-exec provided; executable checks disabled even though --deep-cli was requested."
CLI_TESTS_NOT_REQUESTED_REASON = "--run-cli-tests not provided"


def command_blocked_reason(argv: Sequence[str]) -> Optional[str]:
    lowered_joined = " ".join(argv).lower()
    if re.search(r"\bgit\s+push\b", lowered_joined):
        return "mutation_or_side_effect_risk"
    for token in argv:
        lowered = token.lower()
        executable = Path(lowered).name
        flag_name = lowered.split("=", 1)[0]
        if flag_name in MUTATING_ARG_VALUES:
            return "mutation_or_side_effect_risk"
        if executable in MUTATING_EXECUTABLES or executable in MUTATING_VERB_VALUES:
            return "mutation_or_side_effect_risk"
        if executable == "cp":
            non_options = [item for item in argv[1:] if not item.startswith("-")]
            destination = non_options[-1] if non_options else ""
            if not destination.startswith(("/tmp/", str(Path(tempfile.gettempdir()).resolve()) + "/")):
                return "mutation_or_side_effect_risk"
    return None


def minimal_sanitized_env(home: str, cli_dir: Path) -> Dict[str, str]:
    env: Dict[str, str] = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "HOME": home,
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONUNBUFFERED": "1",
    }
    for key in ("LANG", "LC_ALL", "LC_CTYPE"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    if os.environ.get("PYTHONPATH"):
        env["PYTHONPATH"] = os.environ["PYTHONPATH"]
    return env


def json_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    return type(value).__name__


def json_top_level_keys(value: Any) -> List[str]:
    if isinstance(value, dict):
        return sorted(str(key) for key in value.keys())
    return []


def json_fingerprint(value: Any) -> str:
    if isinstance(value, dict):
        keys = json_top_level_keys(value)
        return "keys:" + ",".join(keys) if keys else "keys:"
    return f"root:{json_type_name(value)}"


def validate_cli_doctor_envelope(value: Any) -> Dict[str, Any]:
    required_fields = ["ok", "command", "data", "issues"]
    root_type = json_type_name(value)
    result: Dict[str, Any] = {
        "performed": True,
        "status": "pass",
        "schema_name": "cli-doctor-envelope.v1",
        "json_root_type": root_type,
        "required_fields": required_fields,
        "required_fields_present": [],
        "missing_required_fields": [],
        "field_type_errors": [],
        "ok_value": None,
        "command_value": None,
        "data_type": None,
        "issues_count": None,
        "issue_severity_counts": {},
        "error_code": None,
        "warnings": [],
    }
    warnings: List[str] = result["warnings"]
    field_errors: List[Dict[str, str]] = result["field_type_errors"]
    if not isinstance(value, dict):
        result["status"] = "warn"
        warnings.append("JSON root must be object")
        return result

    present = [field for field in required_fields if field in value]
    missing = [field for field in required_fields if field not in value]
    result["required_fields_present"] = present
    result["missing_required_fields"] = missing
    if missing:
        result["status"] = "warn"
        warnings.append("missing required fields: " + ", ".join(missing))

    if "ok" in value:
        if isinstance(value.get("ok"), bool):
            result["ok_value"] = value.get("ok")
            if value.get("ok") is False:
                warnings.append("doctor reported ok=false")
        else:
            field_errors.append({"field": "ok", "expected": "boolean", "actual": json_type_name(value.get("ok"))})
    if "command" in value:
        if isinstance(value.get("command"), str):
            result["command_value"] = value.get("command")
        else:
            field_errors.append({"field": "command", "expected": "string", "actual": json_type_name(value.get("command"))})
    if "data" in value:
        result["data_type"] = json_type_name(value.get("data"))
        if not isinstance(value.get("data"), dict):
            warnings.append("data is not object; accepted advisory-only in Step 2B")
    if "issues" in value:
        issues = value.get("issues")
        if isinstance(issues, list):
            result["issues_count"] = len(issues)
            severity_counts: Dict[str, int] = {}
            for issue in issues:
                if isinstance(issue, dict) and isinstance(issue.get("severity"), str):
                    severity = issue["severity"]
                    severity_counts[severity] = severity_counts.get(severity, 0) + 1
            result["issue_severity_counts"] = severity_counts
        else:
            field_errors.append({"field": "issues", "expected": "array", "actual": json_type_name(issues)})
    if "error" in value:
        error = value.get("error")
        if error is not None and not isinstance(error, dict):
            field_errors.append({"field": "error", "expected": "object|null", "actual": json_type_name(error)})
        elif isinstance(error, dict):
            if "code" in error:
                if isinstance(error.get("code"), str):
                    result["error_code"] = error.get("code")
                else:
                    field_errors.append({"field": "error.code", "expected": "string", "actual": json_type_name(error.get("code"))})
            if "message" in error and not isinstance(error.get("message"), str):
                field_errors.append({"field": "error.message", "expected": "string", "actual": json_type_name(error.get("message"))})
    if field_errors:
        result["status"] = "warn"
        warnings.append("field type errors present")
    return result


def envelope_validation_skipped(reason: str) -> Dict[str, Any]:
    return {
        "performed": False,
        "status": "skipped",
        "schema_name": "cli-doctor-envelope.v1",
        "skipped_reason": reason,
    }


def bounded_preview(value: str, max_bytes: int) -> Tuple[str, bool]:
    raw = value.encode("utf-8", errors="replace")
    if len(raw) <= max_bytes:
        return value, False
    return raw[:max_bytes].decode("utf-8", errors="replace"), True


def command_evidence_id(check: str, index: int) -> str:
    suffix = {"cli_help": "help", "cli_doctor": "doctor", "cli_tests": "tests"}.get(check, check)
    return f"ev_cli_{suffix}_{index:03d}"


def doctor_json_metadata(stdout: str, status: str, exit_code: Optional[int]) -> Dict[str, Any]:
    looks_json = stdout.lstrip().startswith(("{", "["))
    if status not in {"pass", "fail"} or not (exit_code == 0 or looks_json):
        return {"envelope_validation": envelope_validation_skipped("doctor command did not produce executable JSON candidate")}
    try:
        parsed = json.loads(stdout)
    except Exception as exc:
        return {
            "parsed_json": False,
            "json_parse_error": redact_sensitive_text(str(exc)),
            "envelope_validation": envelope_validation_skipped("stdout did not parse as JSON"),
        }
    metadata: Dict[str, Any] = {
        "parsed_json": True,
        "json_parse_error": None,
        "json_root_type": json_type_name(parsed),
        "json_top_level_keys": json_top_level_keys(parsed),
        "json_fingerprint": json_fingerprint(parsed),
        "envelope_validation": validate_cli_doctor_envelope(parsed),
    }
    if isinstance(parsed, dict):
        if "ok" in parsed:
            metadata["doctor_json_ok_field"] = parsed.get("ok")
        if "command" in parsed:
            metadata["doctor_json_command_field"] = parsed.get("command")
    return metadata


def redact_argv(argv: Sequence[str]) -> List[str]:
    redacted: List[str] = []
    previous_secret_flag = False
    for token in argv:
        token_text = str(token)
        lowered_flag = token_text.lower().split("=", 1)[0].lstrip("-").replace("-", "_")
        if previous_secret_flag:
            if token_text.startswith("-"):
                previous_secret_flag = False
            else:
                redacted.append("[REDACTED]")
                continue
        redacted.append(redact_sensitive_text(token_text))
        previous_secret_flag = bool(SECRET_KEYWORD_RE.search(lowered_flag) and "=" not in token_text)
    return redacted


def make_command_evidence(
    *,
    evidence_id: str,
    check: str,
    status: str,
    argv: Sequence[str],
    cwd: str,
    timeout_sec: int,
    max_output_bytes: int,
    stdout: str = "",
    stderr: str = "",
    exit_code: Optional[int] = None,
    duration_ms: Optional[int] = None,
    execution_performed: bool = False,
    parsed_json: bool = False,
    json_parse_error: Optional[str] = None,
    skipped_reason: Optional[str] = None,
    blocked_reason: Optional[str] = None,
    timeout: bool = False,
    doctor_json_ok_field: Optional[Any] = None,
    doctor_json_command_field: Optional[Any] = None,
    json_root_type: Optional[str] = None,
    json_top_level_keys: Optional[List[str]] = None,
    json_fingerprint: Optional[str] = None,
    envelope_validation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    stdout_preview, stdout_truncated = bounded_preview(stdout, max_output_bytes)
    stderr_preview, stderr_truncated = bounded_preview(stderr, max_output_bytes)
    stdout_preview_redacted = redact_sensitive_text(stdout_preview)
    stderr_preview_redacted = redact_sensitive_text(stderr_preview)
    output_redaction_applied = stdout_preview_redacted != stdout_preview or stderr_preview_redacted != stderr_preview
    item: Dict[str, Any] = {
        "id": evidence_id,
        "kind": "command",
        "evidence_schema_version": "command-evidence.v1",
        "command_id": evidence_id.removeprefix("ev_"),
        "check": check,
        "status": status,
        "argv": redact_argv(argv),
        "argv_redacted": True,
        "cwd": cwd,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "timeout_sec": timeout_sec,
        "stdout_sha256": hashlib.sha256(stdout.encode("utf-8", errors="replace")).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr.encode("utf-8", errors="replace")).hexdigest(),
        "stdout_preview": stdout_preview_redacted,
        "stderr_preview": stderr_preview_redacted,
        "stdout_preview_redacted": stdout_preview_redacted,
        "stderr_preview_redacted": stderr_preview_redacted,
        "output_redaction_applied": output_redaction_applied,
        "stdout_bytes": len(stdout.encode("utf-8", errors="replace")),
        "stderr_bytes": len(stderr.encode("utf-8", errors="replace")),
        "stdout_preview_bytes": len(stdout_preview_redacted.encode("utf-8", errors="replace")),
        "stderr_preview_bytes": len(stderr_preview_redacted.encode("utf-8", errors="replace")),
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "parsed_json": parsed_json,
        "json_parse_error": redact_sensitive_text(json_parse_error) if json_parse_error else None,
        "env_policy": "sanitized_minimal",
        "mutation_policy": "deny",
        "network_policy": "not_allowed_or_unknown",
        "execution_performed": execution_performed,
    }
    if skipped_reason:
        item["skipped_reason"] = skipped_reason
    if blocked_reason:
        item["blocked_reason"] = blocked_reason
    if timeout:
        item["timeout"] = True
    if doctor_json_ok_field is not None:
        item["doctor_json_ok_field"] = doctor_json_ok_field
    if doctor_json_command_field is not None:
        item["doctor_json_command_field"] = doctor_json_command_field
    if json_root_type is not None:
        item["json_root_type"] = json_root_type
    if json_top_level_keys is not None:
        item["json_top_level_keys"] = json_top_level_keys
    if json_fingerprint is not None:
        item["json_fingerprint"] = json_fingerprint
    if envelope_validation is not None:
        item["envelope_validation"] = sanitize_for_report(envelope_validation)
    elif check == "cli_doctor":
        item["envelope_validation"] = envelope_validation_skipped("stdout did not parse as JSON" if json_parse_error else "doctor JSON envelope validation not performed")
    return item


def run_safe_command(argv: Sequence[str], cli_dir: Path, check: str, evidence_id: str, timeout_sec: int, max_output_bytes: int) -> Dict[str, Any]:
    blocked_reason = command_blocked_reason(argv)
    if blocked_reason:
        return make_command_evidence(
            evidence_id=evidence_id,
            check=check,
            status="blocked",
            argv=argv,
            cwd="cli",
            timeout_sec=timeout_sec,
            max_output_bytes=max_output_bytes,
            blocked_reason=blocked_reason,
            execution_performed=False,
        )
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="audit-skill-home-") as home:
        try:
            completed = subprocess.run(
                list(argv),
                cwd=str(cli_dir),
                env=minimal_sanitized_env(home, cli_dir),
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", errors="replace")
            stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", errors="replace")
            return make_command_evidence(
                evidence_id=evidence_id,
                check=check,
                status="timeout",
                argv=argv,
                cwd="cli",
                exit_code=None,
                duration_ms=duration_ms,
                timeout_sec=timeout_sec,
                max_output_bytes=max_output_bytes,
                stdout=stdout,
                stderr=stderr,
                timeout=True,
                execution_performed=True,
            )
        except OSError as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            return make_command_evidence(
                evidence_id=evidence_id,
                check=check,
                status="fail",
                argv=argv,
                cwd="cli",
                exit_code=None,
                duration_ms=duration_ms,
                timeout_sec=timeout_sec,
                max_output_bytes=max_output_bytes,
                stderr=str(exc),
                execution_performed=True,
            )
    duration_ms = int((time.monotonic() - started) * 1000)
    status = "pass" if completed.returncode == 0 else "fail"
    doctor_metadata = doctor_json_metadata(completed.stdout, status, completed.returncode) if check == "cli_doctor" else {}
    return make_command_evidence(
        evidence_id=evidence_id,
        check=check,
        status=status,
        argv=argv,
        cwd="cli",
        exit_code=completed.returncode,
        duration_ms=duration_ms,
        timeout_sec=timeout_sec,
        max_output_bytes=max_output_bytes,
        stdout=completed.stdout,
        stderr=completed.stderr,
        execution_performed=True,
        **doctor_metadata,
    )


def high_confidence_entrypoints(cli_inventory: Dict[str, Any]) -> List[Dict[str, Any]]:
    confidence_order = {"high": 0, "medium": 1, "low": 2}
    kind_order = {"project_script": 0, "python_module": 1, "python_file": 2, "docs_mention": 3, "unknown": 4}
    items = [item for item in cli_inventory.get("entrypoints", []) if item.get("confidence") == "high"]
    return sorted(items, key=lambda item: (confidence_order.get(str(item.get("confidence")), 9), kind_order.get(str(item.get("kind")), 9), str(item.get("module") or item.get("path") or item.get("name") or "")))


def module_resolves_inside_cli(module: str, skill_dir: Path) -> bool:
    cli_dir = (skill_dir / "cli").resolve()
    parts = [part for part in module.split(".") if part]
    if not parts:
        return False
    package_path = (cli_dir / Path(*parts)).resolve()
    top_level = (cli_dir / parts[0]).resolve()
    candidates = [
        package_path.with_suffix(".py"),
        package_path / "__main__.py",
        package_path / "__init__.py",
        top_level.with_suffix(".py"),
        top_level / "__main__.py",
        top_level / "__init__.py",
    ]
    return any(is_relative_to(path, cli_dir) and path.exists() for path in candidates)


def help_argv_for_entrypoint(entry: Dict[str, Any], skill_dir: Path) -> Optional[List[str]]:
    kind = entry.get("kind")
    module = entry.get("module")
    path_value = entry.get("path")
    if kind in {"python_module", "project_script"} and module:
        module_text = str(module)
        if module_resolves_inside_cli(module_text, skill_dir):
            return ["python3", "-m", module_text, "--help"]
        return None
    if kind == "python_file" and path_value:
        path = (skill_dir / str(path_value)).resolve()
        cli_dir = (skill_dir / "cli").resolve()
        if is_relative_to(path, cli_dir):
            return ["python3", relpath(path, cli_dir), "--help"]
    return None


def module_entrypoint(cli_inventory: Dict[str, Any], skill_dir: Path) -> Optional[str]:
    for entry in high_confidence_entrypoints(cli_inventory):
        if entry.get("kind") in {"project_script", "python_module"} and entry.get("module"):
            module = str(entry["module"])
            if module_resolves_inside_cli(module, skill_dir):
                return module
    return None


def extract_candidate_argv(snippet: str) -> List[str]:
    candidates = re.findall(r"`([^`]+)`", snippet)
    raw = candidates[0] if candidates else snippet
    try:
        parts = shlex.split(raw)
    except ValueError:
        parts = [raw]
    return parts or [snippet]


def doctor_pattern_from_claims(cli_inventory: Dict[str, Any]) -> Optional[str]:
    snippets = [str(item.get("snippet") or "") for item in cli_inventory.get("json_output_claims", [])]
    combined = "\n".join(snippets).lower()
    if "--json doctor" in combined:
        return "json_first"
    if "doctor" in combined and "--json" in combined:
        if "doctor --json" in combined:
            return "doctor_first"
        return "json_first"
    return None


def should_try_doctor(cli_inventory: Dict[str, Any]) -> bool:
    claims = cli_inventory.get("json_output_claims", [])
    has_doctor = any("doctor" in str(item.get("snippet") or "").lower() or item.get("claim_type") == "doctor_command" for item in claims)
    has_json = any("--json" in str(item.get("snippet") or "").lower() or item.get("claim_type") == "json_flag" for item in claims)
    return bool(has_doctor and has_json)


def parse_doctor_json_evidence(evidence: Dict[str, Any]) -> None:
    if evidence.get("parsed_json") or evidence.get("json_parse_error"):
        return
    stdout = str(evidence.get("stdout_preview") or "")
    looks_json = stdout.lstrip().startswith(("{", "["))
    if evidence.get("status") not in {"pass", "fail"}:
        return
    if evidence.get("exit_code") == 0 or looks_json:
        try:
            parsed = json.loads(stdout)
        except Exception as exc:
            evidence["parsed_json"] = False
            evidence["json_parse_error"] = redact_sensitive_text(str(exc))
        else:
            evidence["parsed_json"] = True
            evidence["json_parse_error"] = None
            if isinstance(parsed, dict):
                if "ok" in parsed:
                    evidence["doctor_json_ok_field"] = parsed.get("ok")
                if "command" in parsed:
                    evidence["doctor_json_command_field"] = parsed.get("command")


def advisory_cli_findings(skill_dir: Path, root: Path, evidence: Sequence[Dict[str, Any]], cli_contract: Dict[str, Any]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    if cli_contract.get("execution_performed"):
        findings.append(make_finding("CLI_DEEP_AUDIT_EXECUTED", "info", "cli_contract", "advisory --deep-cli executable checks were performed", skill_dir / "cli", root=root))
    for item in evidence:
        check = item.get("check")
        status = item.get("status")
        if status == "blocked":
            findings.append(make_finding("CLI_EXECUTION_BLOCKED_UNSAFE", "warning", "cli_contract", "candidate CLI command blocked by advisory mutation policy", skill_dir / "cli", evidence={"kind": "command", "value": " ".join(item.get("argv", [])), "redacted": True}, root=root))
        if status == "timeout":
            findings.append(make_finding("CLI_EXECUTION_TIMEOUT", "warning", "cli_contract", "advisory CLI command timed out", skill_dir / "cli", evidence={"kind": "command", "value": " ".join(item.get("argv", [])), "redacted": True}, root=root))
        if item.get("stdout_truncated") or item.get("stderr_truncated"):
            findings.append(make_finding("CLI_EXECUTION_OUTPUT_TRUNCATED", "info", "cli_contract", "advisory CLI command output preview was truncated", skill_dir / "cli", root=root))
        if check == "cli_help" and status == "fail":
            findings.append(make_finding("CLI_HELP_CHECK_FAILED", "warning", "cli_contract", "advisory CLI help check failed", skill_dir / "cli", evidence={"kind": "command", "value": " ".join(item.get("argv", [])), "redacted": True}, root=root))
        if check == "cli_doctor" and status in {"fail", "timeout"}:
            findings.append(make_finding("CLI_DOCTOR_CHECK_FAILED", "warning", "cli_contract", "advisory CLI doctor check failed", skill_dir / "cli", evidence={"kind": "command", "value": " ".join(item.get("argv", [])), "redacted": True}, root=root))
        if check == "cli_doctor" and item.get("json_parse_error"):
            findings.append(make_finding("CLI_DOCTOR_JSON_PARSE_FAILED", "warning", "cli_contract", "advisory CLI doctor output did not parse as JSON", skill_dir / "cli", evidence={"kind": "json_parse_error", "value": item.get("json_parse_error"), "redacted": True}, root=root))
        if check == "cli_doctor":
            validation = item.get("envelope_validation") if isinstance(item.get("envelope_validation"), dict) else {}
            if validation.get("performed"):
                validation_status = validation.get("status")
                if validation_status == "pass":
                    findings.append(make_finding("CLI_DOCTOR_ENVELOPE_VALID", "info", "cli_contract", "advisory CLI doctor JSON envelope shape is valid", skill_dir / "cli", evidence={"kind": "schema", "value": validation.get("schema_name"), "redacted": False}, root=root))
                elif validation_status == "warn":
                    findings.append(make_finding("CLI_DOCTOR_ENVELOPE_INVALID", "warning", "cli_contract", "advisory CLI doctor JSON envelope shape is invalid", skill_dir / "cli", evidence={"kind": "schema", "value": validation.get("schema_name"), "redacted": False}, root=root))
                missing = validation.get("missing_required_fields") or []
                if missing:
                    findings.append(make_finding("CLI_DOCTOR_ENVELOPE_MISSING_REQUIRED_FIELD", "warning", "cli_contract", "doctor JSON envelope is missing required fields", skill_dir / "cli", evidence={"kind": "fields", "value": ",".join(missing), "redacted": False}, root=root))
                type_errors = validation.get("field_type_errors") or []
                if type_errors:
                    findings.append(make_finding("CLI_DOCTOR_ENVELOPE_FIELD_TYPE_INVALID", "warning", "cli_contract", "doctor JSON envelope field types are invalid", skill_dir / "cli", evidence={"kind": "fields", "value": ",".join(str(error.get("field")) for error in type_errors if isinstance(error, dict)), "redacted": False}, root=root))
                if validation.get("json_root_type") and validation.get("json_root_type") != "object":
                    findings.append(make_finding("CLI_DOCTOR_JSON_ROOT_NOT_OBJECT", "warning", "cli_contract", "doctor JSON envelope root is not an object", skill_dir / "cli", evidence={"kind": "json_root_type", "value": validation.get("json_root_type"), "redacted": False}, root=root))
                if validation.get("data_type") and validation.get("data_type") != "object":
                    findings.append(make_finding("CLI_DOCTOR_DATA_NOT_OBJECT", "info", "cli_contract", "doctor JSON envelope data field is not an object; accepted advisory-only in Step 2B", skill_dir / "cli", evidence={"kind": "json_type", "value": validation.get("data_type"), "redacted": False}, root=root))
                if validation.get("ok_value") is False:
                    severity = "warning" if (validation.get("issues_count") or validation.get("error_code")) else "info"
                    findings.append(make_finding("CLI_DOCTOR_REPORTED_NOT_OK", severity, "cli_contract", "doctor JSON envelope reported ok=false", skill_dir / "cli", evidence={"kind": "doctor_ok", "value": "false", "redacted": False}, root=root))
        if check == "cli_tests" and status in {"fail", "timeout"}:
            findings.append(make_finding("CLI_TESTS_FAILED" if status == "fail" else "CLI_EXECUTION_TIMEOUT", "warning", "cli_contract", "advisory CLI tests did not pass", skill_dir / "cli", root=root))
    if cli_contract.get("tests_check", {}).get("status") == "skipped" and cli_contract.get("tests_check", {}).get("reason") == CLI_TESTS_NOT_REQUESTED_REASON:
        findings.append(make_finding("CLI_TESTS_SKIPPED", "info", "cli_contract", "CLI tests skipped because --run-cli-tests was not provided", skill_dir / "cli", root=root))
    if cli_contract.get("status") == "skipped" and not cli_contract.get("execution_performed") and not str(cli_contract.get("skipped_executable_checks_reason", "")).startswith("--no-exec"):
        findings.append(make_finding("CLI_DEEP_AUDIT_NO_SAFE_COMMANDS", "warning", "cli_contract", "--deep-cli found no safe executable CLI command to run", skill_dir / "cli", root=root))
    return findings


def executable_summary(evidence: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    return {
        "attempted": sum(1 for item in evidence if item.get("execution_performed")),
        "passed": sum(1 for item in evidence if item.get("status") == "pass"),
        "failed": sum(1 for item in evidence if item.get("status") == "fail"),
        "blocked": sum(1 for item in evidence if item.get("status") == "blocked"),
        "skipped": sum(1 for item in evidence if item.get("status") == "skipped"),
        "timeouts": sum(1 for item in evidence if item.get("status") == "timeout"),
    }


def advisory_cli_contract_check(
    cli_inventory: Dict[str, Any],
    skill_dir: Path,
    timeout_sec: int,
    max_output_bytes: int,
    run_cli_tests: bool,
    no_exec: bool,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    exists = bool(cli_inventory.get("exists"))
    base: Dict[str, Any] = {
        "status": "not_applicable" if not exists else "skipped",
        "mode": "advisory",
        "enforced": False,
        "execution_performed": False,
        "inventory_status": "pass" if exists else "not_applicable",
        "help_check": {"status": "not_applicable" if not exists else "skipped", "commands_attempted": 0, "commands_passed": 0},
        "doctor_check": {"status": "not_applicable" if not exists else "skipped", "commands_attempted": 0, "json_parsed": False},
        "tests_check": {"status": "not_applicable" if not exists else "skipped", "reason": CLI_TESTS_NOT_REQUESTED_REASON},
        "executable_checks_summary": {"attempted": 0, "passed": 0, "failed": 0, "blocked": 0, "skipped": 0, "timeouts": 0},
        "warning": "Executable CLI checks in --deep-cli mode are advisory in this phase. A passing advisory run does not yet imply enforced CLI contract compliance.",
    }
    if not exists:
        base["skipped_executable_checks_reason"] = "no cli/ directory"
        return base, []
    if no_exec:
        base["skipped_executable_checks_reason"] = CLI_DEEP_NO_EXEC_REASON
        base["help_check"]["reason"] = CLI_DEEP_NO_EXEC_REASON
        base["doctor_check"]["reason"] = CLI_DEEP_NO_EXEC_REASON
        base["tests_check"] = {"status": "skipped", "reason": CLI_DEEP_NO_EXEC_REASON}
        return base, []

    cli_dir = skill_dir / "cli"
    evidence: List[Dict[str, Any]] = []
    sequence = 1

    for entry in high_confidence_entrypoints(cli_inventory)[:3]:
        argv = help_argv_for_entrypoint(entry, skill_dir)
        if not argv:
            continue
        evidence.append(run_safe_command(argv, cli_dir, "cli_help", command_evidence_id("cli_help", sequence), timeout_sec, max_output_bytes))
        sequence += 1

    for candidate in cli_inventory.get("mutating_command_candidates", []):
        argv = extract_candidate_argv(str(candidate.get("snippet") or ""))
        if command_blocked_reason(argv):
            evidence.append(make_command_evidence(
                evidence_id=command_evidence_id("cli_help", sequence),
                check="cli_help",
                status="blocked",
                argv=argv,
                cwd="cli",
                timeout_sec=timeout_sec,
                max_output_bytes=max_output_bytes,
                blocked_reason="mutation_or_side_effect_risk",
                execution_performed=False,
            ))
            sequence += 1

    help_entries = [item for item in evidence if item.get("check") == "cli_help" and item.get("status") != "blocked"]
    if help_entries:
        base["help_check"] = {
            "status": "pass" if all(item.get("status") == "pass" for item in help_entries) else "warn",
            "commands_attempted": sum(1 for item in help_entries if item.get("execution_performed")),
            "commands_passed": sum(1 for item in help_entries if item.get("status") == "pass"),
        }
    else:
        base["help_check"]["reason"] = "no high-confidence safe help command identified"

    if should_try_doctor(cli_inventory):
        module = module_entrypoint(cli_inventory, skill_dir)
        if module:
            pattern = doctor_pattern_from_claims(cli_inventory) or "json_first"
            argv = ["python3", "-m", module, "doctor", "--json"] if pattern == "doctor_first" else ["python3", "-m", module, "--json", "doctor"]
            doctor_ev = run_safe_command(argv, cli_dir, "cli_doctor", command_evidence_id("cli_doctor", 1), timeout_sec, max_output_bytes)
            parse_doctor_json_evidence(doctor_ev)
            evidence.append(doctor_ev)
            json_parsed = bool(doctor_ev.get("parsed_json"))
            envelope_validation = doctor_ev.get("envelope_validation") if isinstance(doctor_ev.get("envelope_validation"), dict) else envelope_validation_skipped("stdout did not parse as JSON")
            doctor_status = "warn"
            if doctor_ev.get("status") == "pass" and json_parsed and envelope_validation.get("status") == "pass" and envelope_validation.get("ok_value") is not False:
                doctor_status = "pass"
            base["doctor_check"] = {
                "status": doctor_status,
                "commands_attempted": 1,
                "json_parsed": json_parsed,
                "envelope_validation": envelope_validation,
            }
        else:
            base["doctor_check"] = {"status": "skipped", "commands_attempted": 0, "json_parsed": False, "reason": "no high-confidence module entrypoint for doctor"}
    else:
        base["doctor_check"] = {"status": "skipped", "commands_attempted": 0, "json_parsed": False, "reason": "no likely doctor JSON surface in static inventory"}

    tests_dir = cli_dir / "tests"
    if not run_cli_tests:
        base["tests_check"] = {"status": "skipped", "reason": CLI_TESTS_NOT_REQUESTED_REASON}
    elif not tests_dir.is_dir():
        base["tests_check"] = {"status": "skipped", "reason": "cli/tests not found"}
    elif any("import pytest" in read_text(path) for path in tests_dir.rglob("*.py") if path.is_file()):
        base["tests_check"] = {"status": "skipped", "reason": "pytest runner not implemented in Step 2A"}
    else:
        test_ev = run_safe_command(["python3", "-m", "unittest", "discover", "-s", "tests", "-v"], cli_dir, "cli_tests", command_evidence_id("cli_tests", 1), timeout_sec, max_output_bytes)
        evidence.append(test_ev)
        base["tests_check"] = {"status": "pass" if test_ev.get("status") == "pass" else "warn", "commands_attempted": 1}

    summary = executable_summary(evidence)
    base["executable_checks_summary"] = summary
    base["execution_performed"] = summary["attempted"] > 0
    advisory_failures = summary["failed"] + summary["timeouts"]
    if advisory_failures or base.get("doctor_check", {}).get("status") == "warn" or base.get("tests_check", {}).get("status") == "warn" or base.get("help_check", {}).get("status") == "warn":
        base["status"] = "warn"
    elif base["execution_performed"]:
        base["status"] = "pass"
    else:
        base["status"] = "skipped"
        base["skipped_executable_checks_reason"] = "all executable checks were skipped or blocked by policy"
    return base, evidence


MACHINE_CONSUMER_RE = re.compile(r"(?i)(machine consumer|consumed by another tool|another tool|downstream|agent report|machine-readable contract|structured output consumed|stable json envelope|stable json|json envelope promised)")
CI_BASELINE_RE = re.compile(r"(?i)(\bci\b|baseline|contract test|schema validation|validate_audit_report)")
GOLDEN_RE = re.compile(r"(?i)(golden(?: json)?|golden baseline)")
REDACTION_SENSITIVE_RE = re.compile(r"(?i)(redaction|redact|secret|token|password|credential|authorization|security)")
WRAPPER_PARSES_JSON_RE = re.compile(r"(?i)(json\.loads|parse[s]? json|parsed_json|json fields|wrapper.*json|report.*json)")
REPEATED_EXECUTABLE_RE = re.compile(r"(?i)(workflow|repeat|repeated|automation|cli|doctor|unittest|command)")


def text_for_schema_decision(skill_dir: Path) -> str:
    chunks: List[str] = []
    for path in docs_and_cli_scan_paths(skill_dir):
        if path.exists() and is_text_file(path):
            chunks.append(read_text(path))
    return "\n".join(chunks)


def decide_schema_contract_need(context: Dict[str, Any]) -> Dict[str, Any]:
    cli_inventory = context.get("cli_inventory") if isinstance(context.get("cli_inventory"), dict) else {}
    top_level_schemas = context.get("top_level_schemas") if isinstance(context.get("top_level_schemas"), list) else []
    cli_contract_schemas = context.get("cli_contract_schemas") if isinstance(context.get("cli_contract_schemas"), list) else []
    command_evidence = context.get("command_evidence") if isinstance(context.get("command_evidence"), list) else []
    text = str(context.get("text") or "")
    reason_codes: set[str] = set()

    if cli_inventory.get("exists"):
        reason_codes.add("cli_exists")
    if cli_inventory.get("json_output_claims"):
        reason_codes.add("json_output_claims")
    if should_try_doctor(cli_inventory):
        reason_codes.add("doctor_json_surface")
    if any(item.get("parsed_json") for item in command_evidence):
        reason_codes.add("command_evidence_json_parsed")
    if cli_contract_schemas:
        reason_codes.add("cli_contract_schemas_present")
    if top_level_schemas:
        reason_codes.add("top_level_schemas_present")
    if any(item.get("referenced_by_tests") for item in [*top_level_schemas, *cli_contract_schemas]):
        reason_codes.add("tests_reference_schema")
    if any(item.get("referenced_by_docs") for item in [*top_level_schemas, *cli_contract_schemas]):
        reason_codes.add("docs_reference_schema")
    if MACHINE_CONSUMER_RE.search(text):
        reason_codes.add("machine_consumer_claim")
    if CI_BASELINE_RE.search(text):
        reason_codes.add("ci_or_baseline_claim")
    if GOLDEN_RE.search(text):
        reason_codes.add("golden_fixture_claim")
    if REDACTION_SENSITIVE_RE.search(text) and (cli_inventory.get("json_output_claims") or cli_contract_schemas or "json" in text.lower()):
        reason_codes.add("redaction_sensitive_output")
    if WRAPPER_PARSES_JSON_RE.search(text):
        reason_codes.add("wrapper_parses_json")

    required_triggers = {
        "machine_consumer_claim",
        "ci_or_baseline_claim",
        "golden_fixture_claim",
        "redaction_sensitive_output",
        "wrapper_parses_json",
        "tests_reference_schema",
    }
    if cli_contract_schemas and cli_inventory.get("json_output_claims"):
        required_triggers.add("cli_contract_schemas_present")

    if reason_codes & required_triggers:
        level = "required"
        summary = "Machine-readable contract surface detected; schema contract should be treated as required in a future enforcement phase."
    elif (
        cli_inventory.get("json_output_claims")
        or should_try_doctor(cli_inventory)
        or any(item.get("parsed_json") for item in command_evidence)
        or ([*top_level_schemas, *cli_contract_schemas] and not all(item.get("referenced_by_docs") and item.get("referenced_by_tests") for item in [*top_level_schemas, *cli_contract_schemas]))
        or (cli_inventory.get("exists") and cli_inventory.get("entrypoints") and REPEATED_EXECUTABLE_RE.search(text))
    ):
        level = "recommended"
        summary = "JSON or repeated executable workflow surface detected; schema contract is recommended but advisory."
    elif top_level_schemas or cli_contract_schemas:
        level = "optional"
        summary = "Schema-like files exist, but no stable machine consumer signal was found."
    else:
        level = "not_applicable"
        reason_codes.add("no_machine_contract_surface")
        summary = "No CLI, JSON output claim, schema file, or machine-readable output surface was found."
    return {"level": level, "reason_codes": sorted(reason_codes), "summary": summary}


def schema_summary(schemas: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    return {
        "total": len(schemas),
        "valid_json": sum(1 for item in schemas if item.get("json_valid")),
        "invalid_json": sum(1 for item in schemas if not item.get("json_valid")),
        "meta_valid": sum(1 for item in schemas if item.get("meta_validation", {}).get("performed") and item.get("meta_validation", {}).get("status") == "pass"),
        "meta_invalid": sum(1 for item in schemas if item.get("meta_validation", {}).get("performed") and item.get("meta_validation", {}).get("status") == "warn"),
        "meta_validation_skipped": sum(1 for item in schemas if not item.get("meta_validation", {}).get("performed")),
        "missing_schema_keyword": sum(1 for item in schemas if not item.get("has_schema_keyword")),
        "missing_id_keyword": sum(1 for item in schemas if not item.get("has_id_keyword")),
        "referenced_by_docs": sum(1 for item in schemas if item.get("referenced_by_docs")),
        "referenced_by_tests": sum(1 for item in schemas if item.get("referenced_by_tests")),
    }


def schema_warning_severity(decision: Dict[str, Any], required_only: bool = False) -> str:
    level = decision.get("level")
    if required_only:
        return "warning" if level == "required" else "info"
    return "warning" if level in {"required", "recommended"} else "info"


def schema_advisory_findings(skill_dir: Path, root: Path, schemas: Sequence[Dict[str, Any]], decision: Dict[str, Any]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    level = decision.get("level")
    decision_code = {
        "required": "SCHEMA_DECISION_REQUIRED",
        "recommended": "SCHEMA_DECISION_RECOMMENDED",
        "optional": "SCHEMA_DECISION_OPTIONAL",
        "not_applicable": "SCHEMA_DECISION_NOT_APPLICABLE",
    }.get(str(level), "SCHEMA_DECISION_NOT_APPLICABLE")
    findings.append(make_finding(decision_code, "info", "schema_contract", str(decision.get("summary") or "schema contract decision computed"), skill_dir / "SKILL.md", evidence={"kind": "reason_codes", "value": ",".join(decision.get("reason_codes") or []), "redacted": False}, root=root))
    if not schemas:
        if level == "required":
            findings.append(make_finding("SCHEMA_REQUIRED_BUT_MISSING_ADVISORY", "warning", "schema_contract", "schema contract is required by advisory decision but no schema files were found", skill_dir / "SKILL.md", suggested_fix="Add a JSON Schema when enforcement phase begins, or document why this surface is exempt.", root=root))
        elif level == "recommended":
            findings.append(make_finding("SCHEMA_RECOMMENDED_BUT_MISSING_ADVISORY", "warning", "schema_contract", "schema contract is recommended by advisory decision but no schema files were found", skill_dir / "SKILL.md", suggested_fix="Add a JSON Schema if the JSON output surface is stable.", root=root))
        return findings

    for item in schemas:
        schema_path = item.get("path")
        findings.append(make_finding("SCHEMA_FILE_DETECTED", "info", "schema_contract", "JSON Schema candidate file detected", str(schema_path), evidence={"kind": "schema", "value": str(item.get("filename")), "redacted": False}, root=root))
        if not item.get("json_valid"):
            findings.append(make_finding("SCHEMA_FILE_INVALID_JSON", "warning", "schema_contract", "schema candidate is not valid JSON", str(schema_path), evidence={"kind": "json_parse_error", "value": item.get("json_parse_error"), "redacted": True}, root=root))
        meta = item.get("meta_validation") if isinstance(item.get("meta_validation"), dict) else {}
        if meta.get("performed") and meta.get("status") == "pass":
            findings.append(make_finding("SCHEMA_META_VALIDATION_PASSED", "info", "schema_contract", "schema candidate passed optional JSON Schema meta-validation", str(schema_path), evidence={"kind": "validator", "value": str(meta.get("validator")), "redacted": False}, root=root))
        elif meta.get("performed") and meta.get("status") == "warn":
            findings.append(make_finding("SCHEMA_META_VALIDATION_FAILED", "warning", "schema_contract", "schema candidate failed optional JSON Schema meta-validation", str(schema_path), evidence={"kind": "meta_validation_error", "value": meta.get("error"), "redacted": True}, root=root))
        elif meta.get("status") == "skipped":
            reason = meta.get("skipped_reason") or meta.get("error") or "meta-validation skipped"
            findings.append(make_finding("SCHEMA_META_VALIDATION_SKIPPED", "info", "schema_contract", "optional JSON Schema meta-validation skipped", str(schema_path), evidence={"kind": "skipped_reason", "value": str(reason), "redacted": True}, root=root))
        if not item.get("has_schema_keyword"):
            findings.append(make_finding("SCHEMA_DIALECT_MISSING", schema_warning_severity(decision), "schema_contract", "schema candidate is missing $schema dialect keyword", str(schema_path), root=root))
        elif item.get("dialect") == "unknown":
            findings.append(make_finding("SCHEMA_DIALECT_UNKNOWN", "warning", "schema_contract", "schema candidate has unrecognized $schema dialect", str(schema_path), evidence={"kind": "schema_keyword", "value": item.get("schema_keyword"), "redacted": False}, root=root))
        if not item.get("has_id_keyword"):
            findings.append(make_finding("SCHEMA_ID_MISSING", schema_warning_severity(decision), "schema_contract", "schema candidate is missing $id/id keyword", str(schema_path), root=root))
        ref_severity = "warning" if level == "required" else ("info" if level in {"recommended", "optional"} else "info")
        if not item.get("referenced_by_docs") and level in {"required", "recommended", "optional"}:
            findings.append(make_finding("SCHEMA_NOT_REFERENCED_BY_DOCS", ref_severity, "schema_contract", "schema candidate is not referenced by docs/source files", str(schema_path), root=root))
        if not item.get("referenced_by_tests") and level in {"required", "recommended", "optional"}:
            findings.append(make_finding("SCHEMA_NOT_REFERENCED_BY_TESTS", ref_severity, "schema_contract", "schema candidate is not referenced by tests", str(schema_path), root=root))
        if item.get("additional_properties_policy") in {"open", "unspecified", "mixed"} and level in {"required", "recommended"}:
            findings.append(make_finding("SCHEMA_TOO_OPEN_FOR_MACHINE_CONTRACT", schema_warning_severity(decision, required_only=True), "schema_contract", "schema candidate additionalProperties policy is open, mixed, or unspecified for a machine contract", str(schema_path), evidence={"kind": "additional_properties_policy", "value": str(item.get("additional_properties_policy")), "redacted": False}, root=root))
    return findings


def schema_contract_check(
    top_level_schemas: List[Dict[str, Any]],
    cli_contract_schemas: List[Dict[str, Any]],
    decision: Optional[Dict[str, Any]] = None,
    schema_findings: Optional[Sequence[Dict[str, Any]]] = None,
    schema_output_mappings: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    schemas = [*top_level_schemas, *cli_contract_schemas]
    mappings = list(schema_output_mappings or [])
    decision = decision or {"level": "optional" if schemas else "not_applicable", "reason_codes": [], "summary": "legacy schema inventory decision"}
    warning_codes = {
        "SCHEMA_FILE_INVALID_JSON",
        "SCHEMA_META_VALIDATION_FAILED",
        "SCHEMA_REQUIRED_BUT_MISSING_ADVISORY",
        "SCHEMA_RECOMMENDED_BUT_MISSING_ADVISORY",
        "SCHEMA_DIALECT_UNKNOWN",
        "SCHEMA_ID_MISSING",
        "SCHEMA_DIALECT_MISSING",
        "SCHEMA_NOT_REFERENCED_BY_DOCS",
        "SCHEMA_NOT_REFERENCED_BY_TESTS",
        "SCHEMA_TOO_OPEN_FOR_MACHINE_CONTRACT",
    }
    has_warning = any(item.get("severity") == "warning" and item.get("rule_id") in warning_codes for item in (schema_findings or []))
    if not schemas and decision.get("level") == "not_applicable":
        status = "not_applicable"
    elif has_warning:
        status = "warn"
    else:
        status = "pass"
    return {
        "status": status,
        "mode": "advisory_static",
        "enforced": False,
        "validation_performed": bool(schemas),
        "decision": decision,
        "schema_files_summary": schema_summary(schemas),
        "schemas": schemas,
        "schema_output_mappings": mappings,
        "schema_output_mappings_summary": schema_output_mappings_summary(mappings),
        "missing_schema_advisory": bool(not schemas and decision.get("level") in {"required", "recommended"}),
    }

def target_object(mode: str, skill: Optional[str], path: Optional[Path], repo: Path, input_value: Optional[str] = None) -> Dict[str, Any]:
    return {
        "mode": mode,
        "skill": skill,
        "path": relpath(path, repo) if path is not None else None,
        "input": input_value,
    }


def build_report(
    repo: Path,
    target: Dict[str, Any],
    findings: List[Dict[str, Any]],
    checks: List[Dict[str, Any]],
    evidence_manifest: List[Dict[str, Any]],
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    summary = summary_from_findings(findings)
    blockers = [item for item in findings if item.get("severity") == "blocker"]
    warnings = [item for item in findings if item.get("severity") == "warning"]
    report: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "tool": {"name": "audit_skill", "version": TOOL_VERSION},
        "repo": repo_manifest(repo),
        "target": target,
        "summary": summary,
        "findings": findings,
        "checks": checks,
        "evidence_manifest": evidence_manifest,
        "ok": not blockers,
        "issues": [legacy_issue(item) for item in blockers],
        "warnings": [legacy_issue(item) for item in warnings],
        "issue_count": len(blockers),
        "warning_count": len(warnings),
    }
    if extra:
        report.update(extra)
    return report


def audit_skill_report(
    skill_path: Path,
    repo: Path,
    skill_map: Dict[str, List[Path]],
    input_value: Optional[str] = None,
    deep_cli: bool = False,
    no_exec: bool = False,
    cli_timeout_sec: int = 10,
    max_output_bytes: int = 65536,
    run_cli_tests: bool = False,
) -> Dict[str, Any]:
    root = repo.resolve()
    skill_path = skill_path.resolve()
    skill_dir = skill_path.parent
    findings: List[Dict[str, Any]] = []
    checks: List[Dict[str, Any]] = []

    rel_skill = relpath(skill_path, root)
    if not skill_path.exists():
        findings.append(
            make_finding("MISSING_SKILL", "blocker", "frontmatter", "SKILL.md not found", rel_skill, suggested_fix="Create SKILL.md or fix the target path.")
        )
        return build_report(root, target_object("single", None, skill_dir, root, input_value), findings, checks, [], {"name": None, "path": rel_skill})

    text = read_text(skill_path)
    fm, fm_error = parse_frontmatter(text)
    body = body_after_frontmatter(text)
    support = support_files(skill_dir, include_generated=False)
    files_to_scan = [skill_path] + support

    if fm_error:
        findings.append(
            make_finding(
                "FRONTMATTER_INVALID",
                "blocker",
                "frontmatter",
                fm_error,
                skill_path,
                suggested_fix="Fix SKILL.md YAML frontmatter markers and syntax.",
                root=root,
            )
        )
        checks.append(make_check("FRONTMATTER_VALID", "fail", "frontmatter", fm_error))
        fm = {}
    else:
        checks.append(make_check("FRONTMATTER_VALID", "pass", "frontmatter"))

    name = fm.get("name") if isinstance(fm, dict) else None
    description = fm.get("description") if isinstance(fm, dict) else None

    if not isinstance(name, str) or not name:
        findings.append(make_finding("MISSING_NAME", "blocker", "frontmatter", "frontmatter must include non-empty name", skill_path, suggested_fix="Add a valid name field.", root=root))
    else:
        if len(name) > MAX_NAME_LENGTH or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", name):
            findings.append(make_finding("NAME_SHAPE", "warning", "frontmatter", "name should be lowercase hyphenated and <=64 chars", skill_path, suggested_fix="Rename the skill with lowercase kebab-case.", root=root))
        if skill_dir.name != name:
            findings.append(make_finding("NAME_DIRECTORY_MISMATCH", "warning", "frontmatter", "frontmatter name does not match skill directory name", skill_path, suggested_fix="Align frontmatter name and directory when feasible.", root=root))
        if len(skill_map.get(name, [])) > 1:
            findings.append(make_finding("DUPLICATE_SKILL_NAME", "blocker", "library_architecture", "multiple skills share the same frontmatter name", skill_path, suggested_fix="Give each skill a unique frontmatter name.", root=root))

    if not isinstance(description, str) or not description:
        findings.append(make_finding("MISSING_DESCRIPTION", "blocker", "frontmatter", "frontmatter must include non-empty description", skill_path, suggested_fix="Add a description starting with 'Use when ...'.", root=root))
    elif len(description) > MAX_DESCRIPTION_LENGTH:
        findings.append(make_finding("DESCRIPTION_TOO_LONG", "blocker", "frontmatter", f"description length exceeds {MAX_DESCRIPTION_LENGTH}", skill_path, suggested_fix="Shorten description and move details to the body.", root=root))
    elif not description.lower().startswith("use when"):
        findings.append(make_finding("DESCRIPTION_TRIGGER", "warning", "trigger_clarity", "description should start with 'Use when ...'", skill_path, suggested_fix="Rewrite description as a trigger sentence beginning with 'Use when'.", root=root))

    if isinstance(description, str) and description:
        duplicate_description_paths: List[str] = []
        for other_skill in find_skill_files(root):
            if other_skill.resolve() == skill_path:
                continue
            try:
                other_text = read_text(other_skill)
                other_fm, _ = parse_frontmatter(other_text)
            except Exception:
                continue
            other_description = other_fm.get("description") if isinstance(other_fm, dict) else None
            if other_description == description:
                duplicate_description_paths.append(relpath(other_skill, root))
        if duplicate_description_paths:
            findings.append(
                make_finding(
                    "DUPLICATE_OWNERSHIP_RISK",
                    "warning",
                    "library_architecture",
                    "another skill has the same description trigger; ownership may be duplicated",
                    skill_path,
                    evidence={"kind": "skill_paths", "value": ",".join(duplicate_description_paths), "redacted": False},
                    suggested_fix="Clarify ownership boundaries or merge overlapping skills.",
                    root=root,
                )
            )

    if not body.strip():
        findings.append(make_finding("EMPTY_BODY", "blocker", "frontmatter", "body after frontmatter is empty", skill_path, suggested_fix="Add actionable skill body content.", root=root))

    if len(text) > MAX_SKILL_CONTENT_CHARS:
        findings.append(make_finding("SKILL_TOO_LARGE", "blocker", "maintainability", f"SKILL.md exceeds {MAX_SKILL_CONTENT_CHARS} chars", skill_path, suggested_fix="Move long material into references/.", root=root))
    elif len(text) > 20_000:
        findings.append(make_finding("SKILL_LARGE", "warning", "maintainability", "SKILL.md is large; consider references/ split", skill_path, suggested_fix="Move long evidence or case studies to references/.", root=root))

    for section in REQUIRED_SECTIONS:
        if section not in text:
            findings.append(make_finding("MISSING_SECTION", "warning", "trigger_clarity", f"recommended section missing: {section}", skill_path, suggested_fix=f"Add {section} with concrete guidance.", root=root))

    if "## When to Use" in text and not WHEN_NOT_TO_USE_RE.search(text):
        findings.append(make_finding("MISSING_WHEN_NOT_TO_USE", "warning", "trigger_clarity", "skill lacks explicit when-not-to-use boundary", skill_path, suggested_fix="Add a Do not use / When not to use boundary.", root=root))

    related = related_skills_from_frontmatter(fm if isinstance(fm, dict) else {})
    unresolved = [item for item in related if item not in skill_map]
    for item in unresolved:
        findings.append(make_finding("UNRESOLVED_RELATED_SKILL", "warning", "library_architecture", "related skill not found in repo", skill_path, evidence={"kind": "skill", "value": item, "redacted": False}, suggested_fix="Fix related_skills metadata or add the referenced skill.", root=root))

    children = sorted(child.name for child in skill_dir.iterdir() if child.is_dir())
    unexpected_dirs = [item for item in children if item not in SUPPORT_DIRS and item not in GENERATED_DIR_NAMES]
    for dirname in unexpected_dirs:
        findings.append(make_finding("UNEXPECTED_SUPPORT_DIR", "warning", "support_file_integrity", "unexpected support directory", skill_dir / dirname, evidence={"kind": "directory", "value": dirname, "redacted": False}, suggested_fix="Move support files under references/, templates/, scripts/, assets/, cli/, schemas/, or baselines/.", root=root))

    findings.extend(scan_generated_artifacts(skill_dir, root))
    findings.extend(scan_stale_paths(files_to_scan, root))
    findings.extend(scan_secret_lines(files_to_scan, root))
    findings.extend(scan_unsafe_secret_scan_commands(files_to_scan, root))
    findings.extend(scan_markdown_links(files_to_scan, root))
    findings.extend(scan_python_syntax([path for path in support if "scripts" in path.parts or "cli" in path.parts], root))
    findings.extend(scan_empty_support_files(support, root))
    findings.extend(scan_read_only_contract([path for path in support if path.suffix.lower() in {".py", ".md", ".sh"}], root))

    top_level_schemas, cli_contract_schemas = collect_schema_inventory(skill_dir)
    cli_info = collect_cli_inventory(skill_dir, top_level_schemas, cli_contract_schemas)
    cli_dir = skill_dir / "cli"
    if cli_info["exists"] and not cli_info["python_files"]:
        findings.append(make_finding("CLI_NO_PYTHON", "warning", "executability", "cli/ exists but no Python files found", cli_dir, suggested_fix="Add CLI implementation or remove the empty cli/ directory.", root=root))
    if cli_info["exists"] and not cli_info["entrypoints"]:
        findings.append(make_finding("CLI_ENTRYPOINT_UNRESOLVED", "warning", "cli_contract", "cli/ exists but no static entrypoint could be inferred", cli_dir, suggested_fix="Add [project.scripts], __main__.py, *_cli.py, or documented python -m usage.", root=root))
    if cli_info["exists"]:
        for item in cli_info["json_output_claims"]:
            findings.append(make_finding("CLI_JSON_OUTPUT_CLAIM_DETECTED", "info", "cli_contract", "static JSON output claim detected", item.get("path"), item.get("line"), evidence={"kind": "json_output_claim", "value": item.get("claim_type"), "redacted": False}))
        for item in cli_info["mutating_command_candidates"]:
            findings.append(make_finding("CLI_MUTATION_CANDIDATE_DETECTED", "info", "cli_contract", "static mutating command candidate detected", item.get("path"), item.get("line"), evidence={"kind": "mutation_candidate", "value": item.get("snippet"), "redacted": False}))
        for item in cli_info["wrapper_candidates"]:
            findings.append(make_finding("CLI_WRAPPER_CANDIDATE_DETECTED", "info", "cli_contract", "static wrapper/bypass candidate detected", item.get("path"), item.get("line"), evidence={"kind": "wrapper_candidate", "value": item.get("snippet"), "redacted": False}))
    schema_surface_findings: List[Dict[str, Any]] = []
    for item in cli_contract_schemas:
        schema_surface_findings.append(make_finding("CLI_CONTRACT_SCHEMA_DETECTED", "info", "schema_contract", "CLI-owned contract schema surface detected", item.get("path"), evidence={"kind": "schema", "value": item.get("filename"), "redacted": False}))
    for item in top_level_schemas:
        schema_surface_findings.append(make_finding("SCHEMA_CONTRACT_SURFACE_DETECTED", "info", "schema_contract", "top-level schema contract surface detected", item.get("path"), evidence={"kind": "schema", "value": item.get("filename"), "redacted": False}))
    findings.extend(schema_surface_findings)
    if cli_info["json_output_claims"] and not (top_level_schemas or cli_contract_schemas):
        findings.append(make_finding("JSON_OUTPUT_CLAIM_WITHOUT_SCHEMA", "warning", "schema_contract", "JSON output claim detected but no schema-like files were inventoried", skill_path, suggested_fix="Add a schema/contract file or document why the JSON surface is prose-only for now.", root=root))

    support_summary = {dirname: count_support_files(skill_dir, dirname) for dirname in ["references", "templates", "scripts", "assets", "schemas", "baselines"]}
    skill_name = name if isinstance(name, str) else None
    is_self_audit = skill_name == "skill-audit-and-improvement" or skill_dir.name == "skill-audit-and-improvement"
    cli_command_evidence: List[Dict[str, Any]] = []
    if deep_cli:
        cli_contract, cli_command_evidence = advisory_cli_contract_check(
            cli_info,
            skill_dir,
            max(1, int(cli_timeout_sec)),
            max(1, int(max_output_bytes)),
            run_cli_tests=run_cli_tests,
            no_exec=no_exec,
        )
        findings.extend(advisory_cli_findings(skill_dir, root, cli_command_evidence, cli_contract))
    else:
        cli_contract = cli_contract_check(cli_info)
    schema_decision = decide_schema_contract_need({
        "cli_inventory": cli_info,
        "top_level_schemas": top_level_schemas,
        "cli_contract_schemas": cli_contract_schemas,
        "command_evidence": cli_command_evidence,
        "text": text_for_schema_decision(skill_dir),
    })
    if not (top_level_schemas or cli_contract_schemas) and schema_decision.get("level") in {"required", "recommended"} and not any(item.get("rule_id") == "JSON_OUTPUT_CLAIM_WITHOUT_SCHEMA" for item in findings):
        findings.append(make_finding("JSON_OUTPUT_CLAIM_WITHOUT_SCHEMA", "warning", "schema_contract", "machine-readable output surface detected but no schema-like files were inventoried", skill_path, suggested_fix="Add a schema/contract file or document why the JSON surface is prose-only for now.", root=root))
    schema_findings = schema_advisory_findings(skill_dir, root, [*top_level_schemas, *cli_contract_schemas], schema_decision)
    findings.extend(schema_findings)
    schema_output_mappings = detect_schema_output_mappings(skill_dir, [*top_level_schemas, *cli_contract_schemas])
    for mapping in schema_output_mappings:
        if mapping.get("confidence") != "high":
            continue
        findings.append(
            make_finding(
                "SCHEMA_OUTPUT_MAPPING_DETECTED",
                "info",
                "schema_contract",
                "static high-confidence schema-to-output mapping detected",
                mapping.get("schema_path"),
                evidence={"kind": "schema_output_mapping", "value": str(mapping.get("mapping_kind") or "unknown"), "redacted": False},
                root=root,
            )
        )
    contract_checks = {
        "items": checks,
        "cli_contract": cli_contract,
        "schema_contract": schema_contract_check(
            top_level_schemas,
            cli_contract_schemas,
            schema_decision,
            schema_findings,
            schema_output_mappings,
        ),
    }
    extra = {
        "name": skill_name,
        "path": rel_skill,
        "description_len": len(description) if isinstance(description, str) else None,
        "chars": len(text),
        "lines": text.count("\n") + 1,
        "related_skills": related,
        "support": support_summary,
        "cli": cli_info,
        "top_level_schemas": top_level_schemas,
        "cli_contract_schemas": cli_contract_schemas,
        "self_audit": bool(is_self_audit),
        "self_audit_loop_limited": bool(is_self_audit),
    }
    evidence = evidence_manifest_for(skill_dir, root)
    evidence.extend(cli_command_evidence)
    return build_report(root, target_object("single", skill_name, skill_dir, root, input_value), dedupe_findings(findings), contract_checks, evidence, extra)


def skill_dir_for_changed_path(path: Path, repo: Path) -> Optional[Path]:
    skills_root = (repo / "skills").resolve()
    resolved = path.resolve()
    if not is_relative_to(resolved, skills_root):
        return None
    current = resolved if resolved.is_dir() else resolved.parent
    while is_relative_to(current, skills_root):
        if (current / "SKILL.md").exists():
            return current
        if resolved.name == "SKILL.md" and current != skills_root:
            return current
        if current == skills_root:
            return None
        current = current.parent
    return None


def classify_changed_path(path: Path, repo: Path) -> str:
    rel = relpath(path, repo)
    parts = rel.split("/")
    if len(parts) >= 4 and parts[0] == "skills":
        if parts[-1] == "SKILL.md":
            return "skill_body"
        for kind in ["references", "templates", "scripts", "assets", "cli", "schemas", "baselines", "tests"]:
            if kind in parts:
                return kind
        return "skill_other"
    return "non_skill"


def changed_paths(repo: Path) -> List[Path]:
    names = changed_names(repo)["changed_files"]
    return sorted((repo / name).resolve() for name in names)


def audit_changed_report(
    repo: Path,
    skill_map: Dict[str, List[Path]],
    deep_cli: bool = False,
    no_exec: bool = False,
    cli_timeout_sec: int = 10,
    max_output_bytes: int = 65536,
    run_cli_tests: bool = False,
) -> Dict[str, Any]:
    paths = changed_paths(repo)
    production_scan_paths = [path for path in paths if not is_test_fixture_path(path, repo)]
    affected_dirs = sorted({skill_dir for path in paths if (skill_dir := skill_dir_for_changed_path(path, repo)) is not None})
    affected_results = [
        audit_skill_report(
            skill_dir / "SKILL.md",
            repo,
            skill_map,
            input_value=relpath(skill_dir, repo),
            deep_cli=deep_cli,
            no_exec=no_exec,
            cli_timeout_sec=cli_timeout_sec,
            max_output_bytes=max_output_bytes,
            run_cli_tests=run_cli_tests,
        )
        for skill_dir in affected_dirs
    ]

    findings: List[Dict[str, Any]] = []
    findings.extend(scan_stale_paths(production_scan_paths, repo))
    findings.extend(scan_secret_lines(production_scan_paths, repo))
    findings.extend(scan_unsafe_secret_scan_commands(production_scan_paths, repo))
    for result in affected_results:
        findings.extend(result.get("findings", []))
    findings = dedupe_findings(findings)

    affected_skills = [result.get("target", {}).get("skill") for result in affected_results if result.get("target", {}).get("skill")]
    changed_file_entries = [
        {
            "path": relpath(path, repo),
            "kind": classify_changed_path(path, repo),
            "exists": path.exists(),
            "test_fixture": is_test_fixture_path(path, repo),
        }
        for path in paths
    ]
    extra = {
        "changed_file_count": len(paths),
        "changed_files": [entry["path"] for entry in changed_file_entries],
        "changed_file_details": changed_file_entries,
        "affected_skills": affected_skills,
        "affected_non_skill_files": [entry["path"] for entry in changed_file_entries if entry["kind"] == "non_skill"],
        "affected_results": affected_results,
    }
    checks = [make_check("CHANGED_FILES_COLLECTED", "pass", "git", f"changed_file_count={len(paths)}")]
    evidence = [
        {
            "path": entry["path"],
            "kind": "changed_file",
            "exists": entry["exists"],
            "change_kind": entry["kind"],
        }
        for entry in changed_file_entries
    ]
    return build_report(repo, target_object("changed", None, None, repo), findings, checks, evidence, extra)


def audit_all_report(
    repo: Path,
    skill_map: Dict[str, List[Path]],
    deep_cli: bool = False,
    no_exec: bool = False,
    cli_timeout_sec: int = 10,
    max_output_bytes: int = 65536,
    run_cli_tests: bool = False,
) -> Dict[str, Any]:
    results = [
        audit_skill_report(
            path,
            repo,
            skill_map,
            input_value=relpath(path.parent, repo),
            deep_cli=deep_cli,
            no_exec=no_exec,
            cli_timeout_sec=cli_timeout_sec,
            max_output_bytes=max_output_bytes,
            run_cli_tests=run_cli_tests,
        )
        for path in find_skill_files(repo)
    ]
    findings: List[Dict[str, Any]] = []
    evidence: List[Dict[str, Any]] = []
    for result in results:
        findings.extend(result.get("findings", []))
        evidence.extend(result.get("evidence_manifest", []))
    extra = {
        "results": results,
        "skill_count": len(results),
        "failing_skills": [result.get("target", {}).get("path") for result in results if result.get("summary", {}).get("blockers", 0) > 0],
    }
    checks = [make_check("ALL_SKILLS_AUDITED", "pass", "library_architecture", f"skill_count={len(results)}")]
    return build_report(repo, target_object("all", None, None, repo), dedupe_findings(findings), checks, evidence, extra)


def load_baseline(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AuditInputError("BASELINE_NOT_FOUND", f"baseline file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AuditInputError("BASELINE_INVALID", f"baseline JSON parse error: {exc}") from exc


def baseline_fingerprints(baseline: Dict[str, Any]) -> set[str]:
    fingerprints: set[str] = set()
    for key in ("known_findings", "findings", "allowed_findings"):
        items = baseline.get(key, [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and isinstance(item.get("fingerprint"), str):
                    fingerprints.add(item["fingerprint"])
                elif isinstance(item, str):
                    fingerprints.add(item)
    return fingerprints


def apply_baseline(report: Dict[str, Any], baseline_path: Path) -> Dict[str, Any]:
    baseline = load_baseline(baseline_path)
    known = baseline_fingerprints(baseline)
    findings = report.get("findings", [])
    new_findings = [item for item in findings if item.get("fingerprint") not in known]
    suppressed_findings = [item for item in findings if item.get("fingerprint") in known]
    new_blockers = [item for item in new_findings if item.get("severity") == "blocker"]
    by_severity = {severity: sum(1 for item in new_findings if item.get("severity") == severity) for severity in ["blocker", "warning", "recommendation", "info"]}
    report["baseline"] = {
        "path": str(baseline_path),
        "known_findings_count": len(known),
        "current_findings_count": len(findings),
        "new_findings_count": len(new_findings),
        "new_findings_by_severity": by_severity,
        "suppressed_findings_count": len(suppressed_findings),
        "suppressed_findings": [item.get("fingerprint") for item in suppressed_findings],
        "new_blockers": [item.get("fingerprint") for item in new_blockers],
        "passed": not new_blockers,
    }
    if known:
        report["ok"] = not new_blockers
    else:
        report["ok"] = report.get("summary", {}).get("blockers", 0) == 0
    return report


def validate_report_shape(report: Dict[str, Any]) -> Optional[str]:
    required = ["schema_version", "tool", "repo", "target", "summary", "findings", "checks", "evidence_manifest"]
    for key in required:
        if key not in report:
            return f"missing required report key: {key}"
    if report.get("schema_version") != SCHEMA_VERSION:
        return "unexpected schema_version"
    if not isinstance(report.get("findings"), list):
        return "findings must be a list"
    for finding in report["findings"]:
        for key in ["rule_id", "severity", "category", "message", "location", "fingerprint"]:
            if key not in finding:
                return f"finding missing required key: {key}"
    return None


def error_report(code: str, message: str, repo: Optional[Path] = None) -> Dict[str, Any]:
    manifest = repo_manifest(repo) if repo is not None else {"root": None, "branch": None, "commit": None, "dirty": None, "changed_files": [], "staged_files": [], "untracked_files": []}
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": {"name": "audit_skill", "version": TOOL_VERSION},
        "repo": manifest,
        "target": {"mode": "error", "skill": None, "path": None, "input": None},
        "summary": {"blockers": 0, "warnings": 0, "recommendations": 0, "info": 1},
        "findings": [],
        "checks": [make_check(code, "fail", "input", message)],
        "evidence_manifest": [],
        "ok": False,
        "error": {"code": code, "message": redact_sensitive_text(message)},
    }


def emit(report: Dict[str, Any], args: argparse.Namespace, repo: Optional[Path], exit_code: int) -> int:
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        if repo is not None and is_relative_to(output_path, repo):
            err = error_report("OUTPUT_INSIDE_REPO", "--output must not write inside the audited repo", repo)
            print(json.dumps(err, ensure_ascii=False, indent=2, sort_keys=True))
            return 2
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        if report.get("target", {}).get("mode") == "single":
            print(f"skill: {report.get('name') or report.get('target', {}).get('input')}")
        else:
            print(f"mode: {report.get('target', {}).get('mode')}")
        print(f"ok: {report.get('ok')}")
        print(json.dumps(report.get("summary", {}), ensure_ascii=False, indent=2, sort_keys=True))
        for item in report.get("findings", []):
            sev = str(item.get("severity", "")).upper()
            print(f"{sev} {item.get('rule_id')}: {item.get('message')}")
    return exit_code


def determine_exit_code(report: Dict[str, Any], baseline_mode: bool = False) -> int:
    if baseline_mode and "baseline" in report:
        return 0 if report["baseline"].get("passed") else 1
    return 0 if report.get("summary", {}).get("blockers", 0) == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only Hermes skill audit quality gate")
    parser.add_argument("--repo", default=os.getcwd(), help="Hermes repo root (default: cwd)")
    parser.add_argument("--skill", help="Skill frontmatter name; path-like values are accepted for backward compatibility")
    parser.add_argument("--path", help="Skill directory or SKILL.md path under repo skills/")
    parser.add_argument("--all", action="store_true", help="Audit all in-repo skills")
    parser.add_argument("--changed", action="store_true", help="Audit changed, staged, and untracked affected skills")
    parser.add_argument("--json", action="store_true", help="Emit stable JSON report")
    parser.add_argument("--output", help="Write JSON report to a path outside the audited repo")
    parser.add_argument("--baseline", help="Compare findings against a baseline JSON file")
    parser.add_argument("--deep-cli", action="store_true", help="Enable advisory executable CLI checks (opt-in, non-blocking)")
    parser.add_argument("--no-exec", action="store_true", help="Disable all executable checks even when --deep-cli is present")
    parser.add_argument("--cli-timeout-sec", type=int, default=10, help="Per-command advisory CLI timeout in seconds (default: 10)")
    parser.add_argument("--max-output-bytes", type=int, default=65536, help="Maximum stdout/stderr preview bytes per command (default: 65536)")
    parser.add_argument("--run-cli-tests", action="store_true", help="Run cli/tests unittest discovery during --deep-cli (not enabled by default)")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    repo, repo_error = resolve_repo(args.repo)
    if repo_error:
        report = error_report(repo_error.code, repo_error.message)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) if args.json else f"ERROR: {repo_error.message}")
        return 2
    assert repo is not None

    mode_count = sum(1 for active in [bool(args.skill), bool(args.path), args.all, args.changed] if active)
    if mode_count != 1:
        report = error_report("INVALID_MODE", "provide exactly one of --skill, --path, --all, or --changed", repo)
        return emit(report, args, repo, 2)

    skill_map = collect_skill_map(repo)
    try:
        if args.changed:
            report = audit_changed_report(
                repo,
                skill_map,
                deep_cli=args.deep_cli,
                no_exec=args.no_exec,
                cli_timeout_sec=args.cli_timeout_sec,
                max_output_bytes=args.max_output_bytes,
                run_cli_tests=args.run_cli_tests,
            )
        elif args.all:
            report = audit_all_report(
                repo,
                skill_map,
                deep_cli=args.deep_cli,
                no_exec=args.no_exec,
                cli_timeout_sec=args.cli_timeout_sec,
                max_output_bytes=args.max_output_bytes,
                run_cli_tests=args.run_cli_tests,
            )
        elif args.path:
            target = resolve_path_target(repo, args.path)
            report = audit_skill_report(
                target,
                repo,
                skill_map,
                input_value=args.path,
                deep_cli=args.deep_cli,
                no_exec=args.no_exec,
                cli_timeout_sec=args.cli_timeout_sec,
                max_output_bytes=args.max_output_bytes,
                run_cli_tests=args.run_cli_tests,
            )
        else:
            target = resolve_skill_target(repo, args.skill or "", skill_map)
            report = audit_skill_report(
                target,
                repo,
                skill_map,
                input_value=args.skill,
                deep_cli=args.deep_cli,
                no_exec=args.no_exec,
                cli_timeout_sec=args.cli_timeout_sec,
                max_output_bytes=args.max_output_bytes,
                run_cli_tests=args.run_cli_tests,
            )

        if args.baseline:
            report = apply_baseline(report, Path(args.baseline).expanduser().resolve())

        validation_error = validate_report_shape(report)
        if validation_error:
            err = error_report("REPORT_SCHEMA_INVALID", validation_error, repo)
            return emit(err, args, repo, 2)

        exit_code = determine_exit_code(report, baseline_mode=bool(args.baseline))
        return emit(report, args, repo, exit_code)
    except AuditInputError as exc:
        report = error_report(exc.code, exc.message, repo)
        return emit(report, args, repo, 2)


if __name__ == "__main__":
    raise SystemExit(main())
