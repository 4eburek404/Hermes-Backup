#!/usr/bin/env python3
"""Verify the Hermes backup repository without printing secret values."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HOME = Path.home()
REPO = Path(__file__).resolve().parents[1]
DEFAULT_IDENTITY_FILE = HOME / ".ssh" / "server_monitor_iOS_app_ed25519"
GITHUB_LIMIT = 100 * 1024 * 1024
NOW = dt.datetime.now(dt.timezone.utc)
DEFAULT_MAX_ENCRYPTED_AGE_DAYS = 8

STRICT_SECRET_PATTERNS = {
    "private_key_block": re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "github_token": re.compile(rb"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b"),
    "github_pat": re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    "openrouter_key": re.compile(rb"\bsk-or-v1-[A-Za-z0-9_-]{20,}\b"),
    "openai_like_key": re.compile(rb"\bsk-[A-Za-z0-9][A-Za-z0-9_-]{24,}\b"),
    "slack_token": re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    "google_api_key": re.compile(rb"\bAIza[0-9A-Za-z_-]{25,}\b"),
    "oauth_access": re.compile(rb"\bya29\.[A-Za-z0-9_-]{20,}\b"),
}

SKIP_SCAN_DIRS = {".git", "secrets-encrypted", "session-history-encrypted"}
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp3", ".ogg", ".mp4", ".sqlite", ".db", ".pyc", ".pyo"}
FORBIDDEN_PATH_PARTS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "venv", "node_modules", "dist", "build"}
FORBIDDEN_FILENAMES = {".env", "auth.json", "gmail_app_password", "state.db"}


def run(cmd: list[str], *, input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, input=input_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or b"").decode("utf-8", "replace")[:2000])
    return result


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def iter_plaintext_files():
    for p in REPO.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_SCAN_DIRS for part in p.parts):
            continue
        if p.suffix.lower() in BINARY_SUFFIXES:
            continue
        yield p


def secret_scan() -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for p in iter_plaintext_files():
        try:
            data = p.read_bytes()
        except OSError:
            continue
        for rule, regex in STRICT_SECRET_PATTERNS.items():
            if regex.search(data):
                findings.append({"path": str(p.relative_to(REPO)), "rule": rule})
    return findings


def raw_forbidden_scan() -> list[str]:
    findings: list[str] = []
    for p in REPO.rglob("*"):
        if not p.exists():
            continue
        rel = p.relative_to(REPO)
        rel_parts = rel.parts
        if rel_parts and rel_parts[0] in {".git", "secrets-encrypted", "session-history-encrypted"}:
            continue
        # Ignore untracked files that gitignore already excludes (for example py_compile-created __pycache__).
        ignored = subprocess.run(["git", "check-ignore", "-q", str(rel)], cwd=REPO, check=False).returncode == 0
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str(rel)], cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False).returncode == 0
        if ignored and not tracked:
            continue
        if p.is_dir() and (p.name in FORBIDDEN_PATH_PARTS or p.name.endswith(".egg-info")):
            findings.append(str(rel))
        if p.is_file() and p.name in FORBIDDEN_FILENAMES:
            findings.append(str(rel))
        if p.is_file() and p.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
            findings.append(str(rel))
    return findings


def verify_cli_backup() -> dict[str, object]:
    agent_manifest_path = REPO / "cli" / "hermes-agent" / "manifest.json"
    skill_clis_manifest_path = REPO / "cli" / "skill-clis" / "manifest.json"
    if not agent_manifest_path.exists():
        raise RuntimeError("Missing CLI backup manifest: cli/hermes-agent/manifest.json")
    if not skill_clis_manifest_path.exists():
        raise RuntimeError("Missing skill CLIs manifest: cli/skill-clis/manifest.json")

    agent = json.loads(agent_manifest_path.read_text(encoding="utf-8"))
    skill_clis = json.loads(skill_clis_manifest_path.read_text(encoding="utf-8"))
    if agent.get("tracked_diff_files") and not (REPO / "cli" / "hermes-agent" / "tracked-changes.patch").exists():
        raise RuntimeError("Hermes Agent tracked changes exist but tracked-changes.patch is missing")
    entries = [entry.get("name") for entry in skill_clis.get("entries", [])]
    for expected in ["article", "flights", "hh-ru", "knowledge"]:
        if expected not in entries:
            raise RuntimeError(f"Skill CLI snapshot missing expected directory: {expected}")
    return {
        "hermes_agent_status_count": agent.get("status_count"),
        "hermes_agent_head_short": agent.get("git_head_short"),
        "skill_clis_entries": entries,
    }


def check_sqlite(path: Path) -> str:
    conn = sqlite3.connect(path)
    try:
        return conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()


def latest_manifest(directory: Path) -> Path:
    manifests = sorted(directory.glob("manifest-*.json"))
    if not manifests:
        raise RuntimeError(f"No manifest found in {directory}")
    return manifests[-1]


def artifact_paths_from_manifest(manifest: dict) -> list[Path]:
    paths = [REPO / item["path"] for item in manifest.get("artifacts", [])]
    if not paths:
        raise RuntimeError(f"No artifacts in manifest {manifest.get('kind')}")
    return paths


def verify_artifacts(manifest_path: Path) -> tuple[dict, list[Path]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = artifact_paths_from_manifest(manifest)
    for item, p in zip(manifest["artifacts"], paths):
        if not p.exists():
            raise RuntimeError(f"Missing artifact: {p}")
        if p.stat().st_size != item["size_bytes"]:
            raise RuntimeError(f"Size mismatch: {p}")
        if sha256_file(p) != item["sha256"]:
            raise RuntimeError(f"SHA256 mismatch: {p}")
    return manifest, paths


def parse_manifest_time(manifest: dict) -> dt.datetime:
    raw = manifest.get("created_at_utc")
    if isinstance(raw, str):
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    ts = manifest.get("timestamp")
    if isinstance(ts, str):
        return dt.datetime.strptime(ts, "%Y%m%d-%H%M%S").replace(tzinfo=dt.timezone.utc)
    raise RuntimeError(f"Encrypted manifest has no parseable timestamp: {manifest.get('kind')}")


def manifest_age_days(manifest: dict) -> float:
    return max(0.0, (NOW - parse_manifest_time(manifest)).total_seconds() / 86400)


def assert_fresh(manifest: dict, max_age_days: float | None) -> float:
    age_days = manifest_age_days(manifest)
    if max_age_days is not None and age_days > max_age_days:
        raise RuntimeError(
            f"Encrypted {manifest.get('kind')} manifest is stale: age_days={age_days:.2f}, max={max_age_days}"
        )
    return age_days


def generated_encrypted_files(directory: Path, artifact_prefix: str) -> list[Path]:
    files: list[Path] = []
    for pattern in ("manifest-*.json", f"{artifact_prefix}-*.tar.zst.age*"):
        files.extend(p for p in directory.glob(pattern) if p.is_file())
    return sorted(set(files))


def single_active_generation_report(
    secret_manifest_path: Path,
    secret_paths: list[Path],
    state_manifest_path: Path,
    state_paths: list[Path],
) -> dict[str, object]:
    allowed = {secret_manifest_path.resolve(), state_manifest_path.resolve()}
    allowed.update(p.resolve() for p in secret_paths)
    allowed.update(p.resolve() for p in state_paths)
    extras: list[str] = []
    for directory, prefix in (
        (REPO / "secrets-encrypted", "hermes-secrets"),
        (REPO / "session-history-encrypted", "hermes-state-and-sessions"),
    ):
        for path in generated_encrypted_files(directory, prefix):
            if path.resolve() not in allowed:
                extras.append(str(path.relative_to(REPO)))
    return {"ok": not extras, "extra_generated_files": extras}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the Hermes backup repository without printing secret values.")
    parser.add_argument(
        "--max-encrypted-age-days",
        type=float,
        default=None,
        help="Fail if latest encrypted manifests are older than this many days. Recommended: 8.",
    )
    parser.add_argument(
        "--require-single-active-generation",
        action="store_true",
        help="Fail if generated encrypted files outside the latest manifest references remain in HEAD.",
    )
    parser.add_argument(
        "--identity-file",
        default=str(DEFAULT_IDENTITY_FILE),
        help="age/SSH identity file used to test-decrypt encrypted artifacts.",
    )
    return parser.parse_args(argv)


def decrypt_tar_list(paths: list[Path], identity_file: Path) -> list[str]:
    cat = subprocess.Popen(["cat", *map(str, paths)], stdout=subprocess.PIPE)
    age = subprocess.Popen(["age", "-d", "-i", str(identity_file)], stdin=cat.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert cat.stdout is not None
    cat.stdout.close()
    tar = subprocess.Popen(["tar", "--zstd", "-tf", "-"], stdin=age.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert age.stdout is not None
    age.stdout.close()
    out, tar_err = tar.communicate()
    age_err = age.stderr.read() if age.stderr else b""
    cat.wait()
    age_rc = age.wait()
    if age_rc != 0:
        raise RuntimeError(f"age decrypt failed: {age_err.decode('utf-8', 'replace')[:1000]}")
    if tar.returncode != 0:
        raise RuntimeError(f"tar list failed: {tar_err.decode('utf-8', 'replace')[:1000]}")
    return [line.strip() for line in out.decode("utf-8", "replace").splitlines() if line.strip()]


def extract_member(paths: list[Path], member: str, out_path: Path, identity_file: Path) -> None:
    cat = subprocess.Popen(["cat", *map(str, paths)], stdout=subprocess.PIPE)
    age = subprocess.Popen(["age", "-d", "-i", str(identity_file)], stdin=cat.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert cat.stdout is not None
    cat.stdout.close()
    with out_path.open("wb") as f:
        tar = subprocess.Popen(["tar", "--zstd", "-xOf", "-", member], stdin=age.stdout, stdout=f, stderr=subprocess.PIPE)
        assert age.stdout is not None
        age.stdout.close()
        _, tar_err = tar.communicate()
    age_err = age.stderr.read() if age.stderr else b""
    cat.wait()
    age_rc = age.wait()
    if age_rc != 0:
        raise RuntimeError(f"age decrypt failed: {age_err.decode('utf-8', 'replace')[:1000]}")
    if tar.returncode != 0:
        raise RuntimeError(f"tar extract failed for {member}: {tar_err.decode('utf-8', 'replace')[:1000]}")


def norm_names(names: list[str]) -> set[str]:
    return {name[2:] if name.startswith("./") else name for name in names}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    identity_file = Path(args.identity_file).expanduser()
    if not identity_file.exists():
        raise RuntimeError(f"Missing age identity file: {identity_file}")
    required = [
        REPO / "README.md",
        REPO / "MANIFEST.json",
        REPO / "hermes" / "SOUL.md",
        REPO / "hermes" / "memories" / "USER.md",
        REPO / "hermes" / "memories" / "MEMORY.md",
        REPO / "hermes" / "cron" / "jobs.json",
        REPO / "hermes" / "config.yaml.redacted",
        REPO / "hermes" / "env.keys",
        REPO / "hermes" / "holographic-memory" / "memory_store.sqlite",
        REPO / "cli" / "README.md",
        REPO / "cli" / "hermes-agent" / "manifest.json",
        REPO / "cli" / "skill-clis" / "manifest.json",
    ]
    missing = [str(p.relative_to(REPO)) for p in required if not p.exists()]
    if missing:
        raise RuntimeError(f"Missing required files: {missing}")

    large = []
    for p in REPO.rglob("*"):
        if p.is_file() and ".git" not in p.parts and p.stat().st_size >= GITHUB_LIMIT:
            large.append({"path": str(p.relative_to(REPO)), "size_bytes": p.stat().st_size})
    if large:
        raise RuntimeError(f"Files exceed GitHub 100MiB limit: {large}")

    mem_integrity = check_sqlite(REPO / "hermes" / "holographic-memory" / "memory_store.sqlite")
    if mem_integrity != "ok":
        raise RuntimeError(f"memory_store snapshot integrity failed: {mem_integrity}")

    secret_manifest_path = latest_manifest(REPO / "secrets-encrypted")
    state_manifest_path = latest_manifest(REPO / "session-history-encrypted")
    secret_manifest, secret_paths = verify_artifacts(secret_manifest_path)
    state_manifest, state_paths = verify_artifacts(state_manifest_path)
    secret_age_days = assert_fresh(secret_manifest, args.max_encrypted_age_days)
    state_age_days = assert_fresh(state_manifest, args.max_encrypted_age_days)
    single_active = single_active_generation_report(secret_manifest_path, secret_paths, state_manifest_path, state_paths)
    if args.require_single_active_generation and not single_active["ok"]:
        raise RuntimeError(f"More than one active encrypted generation in HEAD: {single_active['extra_generated_files'][:50]}")

    secret_names = norm_names(decrypt_tar_list(secret_paths, identity_file))
    for expected in [".hermes/.env", ".hermes/auth.json", ".hermes/config.yaml"]:
        if expected not in secret_names:
            raise RuntimeError(f"Encrypted secrets archive missing expected path: {expected}")

    state_names = norm_names(decrypt_tar_list(state_paths, identity_file))
    if ".hermes/state.db.sqlite" not in state_names:
        raise RuntimeError("Encrypted state archive missing .hermes/state.db.sqlite")
    if not any(name.startswith(".hermes/sessions/") for name in state_names):
        raise RuntimeError("Encrypted state archive missing sessions")

    with tempfile.TemporaryDirectory(prefix="hermes-backup-verify-") as td:
        tmp_db = Path(td) / "state.db.sqlite"
        extract_member(state_paths, "./.hermes/state.db.sqlite", tmp_db, identity_file)
        state_integrity = check_sqlite(tmp_db)
        if state_integrity != "ok":
            raise RuntimeError(f"state.db snapshot integrity failed: {state_integrity}")

    findings = secret_scan()
    if findings:
        raise RuntimeError(f"Plaintext high-risk secret scan findings (values not printed): {findings}")

    forbidden = raw_forbidden_scan()
    if forbidden:
        raise RuntimeError(f"Forbidden raw/cache paths present in plaintext repo: {forbidden[:50]}")

    cli = verify_cli_backup()
    top_manifest = json.loads((REPO / "MANIFEST.json").read_text(encoding="utf-8"))

    print(json.dumps({
        "ok": True,
        "memory_store_integrity": mem_integrity,
        "state_db_integrity": "ok",
        "secret_artifact_count": len(secret_paths),
        "state_artifact_count": len(state_paths),
        "secret_archive_members": len(secret_names),
        "state_archive_members": len(state_names),
        "latest_secret_timestamp": secret_manifest.get("timestamp"),
        "latest_state_timestamp": state_manifest.get("timestamp"),
        "secret_age_days": round(secret_age_days, 4),
        "state_age_days": round(state_age_days, 4),
        "encrypted_refreshed": top_manifest.get("encrypted_refreshed"),
        "encrypted_policy": top_manifest.get("encrypted_policy"),
        "single_active_generation": bool(single_active["ok"]),
        "extra_encrypted_generated_files": single_active["extra_generated_files"],
        "plaintext_secret_findings": 0,
        "forbidden_plaintext_paths": 0,
        "files_over_github_limit": 0,
        "cli_backup": cli,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
