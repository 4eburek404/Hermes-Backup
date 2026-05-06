#!/usr/bin/env python3
"""Verify the Hermes backup repository without printing secret values."""
from __future__ import annotations

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
IDENTITY_FILE = HOME / ".ssh" / "server_monitor_iOS_app_ed25519"
GITHUB_LIMIT = 100 * 1024 * 1024

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
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp3", ".ogg", ".mp4", ".sqlite", ".db"}


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


def decrypt_tar_list(paths: list[Path]) -> list[str]:
    cat = subprocess.Popen(["cat", *map(str, paths)], stdout=subprocess.PIPE)
    age = subprocess.Popen(["age", "-d", "-i", str(IDENTITY_FILE)], stdin=cat.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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


def extract_member(paths: list[Path], member: str, out_path: Path) -> None:
    cat = subprocess.Popen(["cat", *map(str, paths)], stdout=subprocess.PIPE)
    age = subprocess.Popen(["age", "-d", "-i", str(IDENTITY_FILE)], stdin=cat.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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


def main() -> int:
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

    secret_manifest, secret_paths = verify_artifacts(latest_manifest(REPO / "secrets-encrypted"))
    state_manifest, state_paths = verify_artifacts(latest_manifest(REPO / "session-history-encrypted"))

    secret_names = norm_names(decrypt_tar_list(secret_paths))
    for expected in [".hermes/.env", ".hermes/auth.json", ".hermes/config.yaml"]:
        if expected not in secret_names:
            raise RuntimeError(f"Encrypted secrets archive missing expected path: {expected}")

    state_names = norm_names(decrypt_tar_list(state_paths))
    if ".hermes/state.db.sqlite" not in state_names:
        raise RuntimeError("Encrypted state archive missing .hermes/state.db.sqlite")
    if not any(name.startswith(".hermes/sessions/") for name in state_names):
        raise RuntimeError("Encrypted state archive missing sessions")

    with tempfile.TemporaryDirectory(prefix="hermes-backup-verify-") as td:
        tmp_db = Path(td) / "state.db.sqlite"
        extract_member(state_paths, "./.hermes/state.db.sqlite", tmp_db)
        state_integrity = check_sqlite(tmp_db)
        if state_integrity != "ok":
            raise RuntimeError(f"state.db snapshot integrity failed: {state_integrity}")

    findings = secret_scan()
    if findings:
        raise RuntimeError(f"Plaintext high-risk secret scan findings (values not printed): {findings}")

    print(json.dumps({
        "ok": True,
        "memory_store_integrity": mem_integrity,
        "state_db_integrity": "ok",
        "secret_artifact_count": len(secret_paths),
        "state_artifact_count": len(state_paths),
        "secret_archive_members": len(secret_names),
        "state_archive_members": len(state_names),
        "plaintext_secret_findings": 0,
        "files_over_github_limit": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
