#!/usr/bin/env python3
"""Deterministic, read-only Hermes skill audit helper.

The helper audits in-repo Hermes skills and emits a stable JSON report suitable
for local automation and future CI gates. It does not mutate audited skills,
execute skill-owned CLIs, install packages, or run service commands.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SCHEMA_VERSION = "1.0.0"
TOOL_VERSION = "0.2.0"
MAX_DESCRIPTION_LENGTH = 1024
MAX_SKILL_CONTENT_CHARS = 100_000
MAX_NAME_LENGTH = 64

TEXT_SUFFIXES = {".md", ".py", ".toml", ".yaml", ".yml", ".txt", ".json", ".sh"}
SUPPORT_DIRS = ("references", "templates", "scripts", "assets", "cli", "schemas", "baselines")
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
SECRET_KEYWORD_RE = re.compile(
    r"(?i)(api[_-]?key|secret|password|passwd|token|authorization|cookie|private[_-]?key|access[_-]?key|database_url|dsn|connection_string)"
)
INTENTIONAL_UNSAFE_SCAN_CONTEXT_RE = re.compile(
    r"(?i)(do not|don't|avoid|not recommend|instead|this skill wins|fails on|detect|fixture|example of unsafe|should flag)"
)


def redact_sensitive_text(value: str) -> str:
    redacted = SENSITIVE_ASSIGNMENT_LINE_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)
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


def audit_skill_report(skill_path: Path, repo: Path, skill_map: Dict[str, List[Path]], input_value: Optional[str] = None) -> Dict[str, Any]:
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

    cli_dir = skill_dir / "cli"
    cli_info: Dict[str, Any] = {"exists": cli_dir.exists()}
    if cli_dir.exists():
        py_files = sorted(relpath(path, skill_dir) for path in cli_dir.rglob("*.py") if not is_generated_artifact(path))
        cli_info.update({
            "python_files": py_files,
            "has_pyproject": (cli_dir / "pyproject.toml").exists(),
            "has_tests": (cli_dir / "tests").exists(),
        })
        if not py_files:
            findings.append(make_finding("CLI_NO_PYTHON", "warning", "executability", "cli/ exists but no Python files found", cli_dir, suggested_fix="Add CLI implementation or remove the empty cli/ directory.", root=root))

    support_summary = {dirname: count_support_files(skill_dir, dirname) for dirname in ["references", "templates", "scripts", "assets", "schemas", "baselines"]}
    skill_name = name if isinstance(name, str) else None
    is_self_audit = skill_name == "skill-audit-and-improvement" or skill_dir.name == "skill-audit-and-improvement"
    extra = {
        "name": skill_name,
        "path": rel_skill,
        "description_len": len(description) if isinstance(description, str) else None,
        "chars": len(text),
        "lines": text.count("\n") + 1,
        "related_skills": related,
        "support": support_summary,
        "cli": cli_info,
        "self_audit": bool(is_self_audit),
        "self_audit_loop_limited": bool(is_self_audit),
    }
    return build_report(root, target_object("single", skill_name, skill_dir, root, input_value), dedupe_findings(findings), checks, evidence_manifest_for(skill_dir, root), extra)


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
        for kind in ["references", "templates", "scripts", "assets", "cli", "schemas", "baselines"]:
            if kind in parts:
                return kind
        return "skill_other"
    return "non_skill"


def changed_paths(repo: Path) -> List[Path]:
    names = changed_names(repo)["changed_files"]
    return sorted((repo / name).resolve() for name in names)


def audit_changed_report(repo: Path, skill_map: Dict[str, List[Path]]) -> Dict[str, Any]:
    paths = changed_paths(repo)
    production_scan_paths = [path for path in paths if not is_test_fixture_path(path, repo)]
    affected_dirs = sorted({skill_dir for path in paths if (skill_dir := skill_dir_for_changed_path(path, repo)) is not None})
    affected_results = [audit_skill_report(skill_dir / "SKILL.md", repo, skill_map, input_value=relpath(skill_dir, repo)) for skill_dir in affected_dirs]

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


def audit_all_report(repo: Path, skill_map: Dict[str, List[Path]]) -> Dict[str, Any]:
    results = [audit_skill_report(path, repo, skill_map, input_value=relpath(path.parent, repo)) for path in find_skill_files(repo)]
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
            report = audit_changed_report(repo, skill_map)
        elif args.all:
            report = audit_all_report(repo, skill_map)
        elif args.path:
            target = resolve_path_target(repo, args.path)
            report = audit_skill_report(target, repo, skill_map, input_value=args.path)
        else:
            target = resolve_skill_target(repo, args.skill or "", skill_map)
            report = audit_skill_report(target, repo, skill_map, input_value=args.skill)

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
