#!/usr/bin/env python3
"""Collect Konstantin's personal Hermes overlay backup.

Safety properties:
- never prints raw secret contents;
- raw credentials and runtime history are staged only in /tmp and committed only as age-encrypted archives;
- live SQLite databases are snapshotted through sqlite3 backup API;
- encrypted archives are split below GitHub's 100 MB regular-file limit when needed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Iterable

HOME = Path.home()
HERMES = HOME / ".hermes"
DOCS = HOME / "docs"
CODE = HOME / "code"
HERMES_AGENT = HERMES / "hermes-agent"
SKILL_CLIS = CODE / "clis"
REPO = Path(__file__).resolve().parents[1]
DEFAULT_RECIPIENTS_FILE = REPO / "backup" / "age-recipients.txt"
DEFAULT_IDENTITY_FILE = HOME / ".ssh" / "server_monitor_iOS_app_ed25519"
SPLIT_BYTES = 45 * 1024 * 1024
NOW = dt.datetime.now(dt.timezone.utc)
LOCAL_NOW = NOW.astimezone()
TS = os.environ.get("HERMES_BACKUP_TS") or NOW.strftime("%Y%m%d-%H%M%S")
DEFAULT_MAX_ENCRYPTED_AGE_DAYS = 8
DEFAULT_WEEKLY_ENCRYPTED_DOW = 6  # Python weekday(): Monday=0, Sunday=6.
ENCRYPTED_RETENTION = "latest"
SECRET_CHANGE_DETECT_EXCLUDE_SOURCES = {str(HERMES / "channel_directory.json")}

SECRET_KEY_RE = (
    "token", "secret", "password", "passwd", "pwd", "api_key", "apikey", "key", "credential",
    "auth", "refresh", "access", "private", "client_secret", "app_password", "bearer",
)

COPY_EXCLUDE_DIRS = {
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules",
    ".venv", "venv", "dist", "build", ".tox", ".nox", ".cache",
}
COPY_EXCLUDE_PATTERNS = {"*.egg-info"}
COPY_EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp", ".swp"}

STRICT_SECRET_TEXT_PATTERNS = [
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-or-v1-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_-]{24,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{25,}\b"),
    re.compile(r"\bya29\.[A-Za-z0-9_-]{20,}\b"),
]
SANITIZE_SKIP_DIRS = {".git", "secrets-encrypted", "session-history-encrypted"}
SANITIZE_BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp3", ".ogg", ".mp4", ".sqlite", ".db"}

HERMES_EXCLUDE_TOP = {
    "hermes-agent", "logs", "cache", "audio_cache", "image_cache", "sessions", "bin",
}


def relhome(path: Path) -> str:
    try:
        return str(path.relative_to(HOME))
    except ValueError:
        return str(path)


def run(cmd: list[str], *, cwd: Path | None = None, input_bytes: bytes | None = None, capture: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        input=input_bytes,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=False,
    )
    if result.returncode != 0:
        stderr = (result.stderr or b"").decode("utf-8", "replace")
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(cmd)}\n{stderr[:2000]}")
    return result


def ensure_command(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"Required command missing: {name}")


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def copy_file(src: Path, dst: Path) -> None:
    if not src.exists() or not src.is_file():
        return
    ensure_parent(dst)
    shutil.copy2(src, dst)


def ignore_names(_dir: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        if name in COPY_EXCLUDE_DIRS or any(fnmatch.fnmatch(name, pat) for pat in COPY_EXCLUDE_PATTERNS):
            ignored.add(name)
            continue
        if Path(name).suffix.lower() in COPY_EXCLUDE_SUFFIXES:
            ignored.add(name)
    return ignored


def copy_tree(src: Path, dst: Path, *, extra_ignore: Iterable[str] = ()) -> None:
    if not src.exists() or not src.is_dir():
        return
    extra = set(extra_ignore)

    def _ignore(dirpath: str, names: list[str]) -> set[str]:
        ignored = ignore_names(dirpath, names)
        for name in names:
            if name in extra:
                ignored.add(name)
        return ignored

    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=_ignore, symlinks=True)


def redact_text(text: str) -> str:
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            out.append(line)
            continue
        lower = stripped.lower()
        # ENV-like KEY=VALUE.
        if "=" in stripped and not stripped.startswith(("-", "*")):
            key, sep, value = line.partition("=")
            if any(marker in key.lower() for marker in SECRET_KEY_RE) and value.strip():
                out.append(f"{key}{sep}[REDACTED]")
                continue
        # YAML/TOML-like key: value or key = value.
        for sep in (":", "="):
            if sep in stripped:
                prefix, _, value = line.partition(sep)
                key = prefix.strip().strip('"\'')
                if any(marker in key.lower() for marker in SECRET_KEY_RE) and value.strip():
                    out.append(f"{prefix}{sep} [REDACTED]")
                    break
        else:
            out.append(line)
            continue
        if len(out) and out[-1].endswith("[REDACTED]"):
            continue
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def redact_file(src: Path, dst: Path) -> None:
    if not src.exists() or not src.is_file():
        return
    ensure_parent(dst)
    data = src.read_text(encoding="utf-8", errors="replace")
    dst.write_text(redact_text(data), encoding="utf-8")


def write_env_keys(src: Path, dst: Path) -> None:
    ensure_parent(dst)
    lines: list[str] = ["# Variable names from ~/.hermes/.env. Values intentionally omitted.\n"]
    if src.exists():
        for raw in src.read_text(encoding="utf-8", errors="replace").splitlines():
            s = raw.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            key = s.split("=", 1)[0].strip()
            if key:
                lines.append(f"{key}\n")
    dst.write_text("".join(lines), encoding="utf-8")


def sanitize_plaintext_tree() -> int:
    """Replace high-risk token-shaped literals in plaintext backup copies.

    This is intentionally applied to the backup repository copy, not the source Hermes home.
    It catches example tokens in skills/docs as well as accidental raw credentials.
    """
    changed = 0
    for path in REPO.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SANITIZE_SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in SANITIZE_BINARY_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        new = text
        for regex in STRICT_SECRET_TEXT_PATTERNS:
            new = regex.sub("[REDACTED_TOKEN_LIKE_LITERAL]", new)
        if new != text:
            path.write_text(new, encoding="utf-8")
            changed += 1
    return changed


def auth_inventory(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    ensure_parent(dst)
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except Exception as exc:
        dst.write_text(json.dumps({"error": f"could not parse auth.json: {type(exc).__name__}"}, indent=2), encoding="utf-8")
        return
    inv: dict[str, object] = {"top_level_keys": sorted(data.keys())}
    providers = data.get("providers") if isinstance(data, dict) else None
    if isinstance(providers, dict):
        inv["providers"] = {
            name: {
                "keys": sorted(v.keys()) if isinstance(v, dict) else [],
                "token_keys": sorted(v.get("tokens", {}).keys()) if isinstance(v, dict) and isinstance(v.get("tokens"), dict) else [],
            }
            for name, v in providers.items()
        }
    dst.write_text(json.dumps(inv, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sqlite_backup(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    ensure_parent(dst)
    if dst.exists():
        dst.unlink()
    src_conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        dst_conn = sqlite3.connect(dst)
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()
    conn = sqlite3.connect(dst)
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()
    if result != "ok":
        raise RuntimeError(f"SQLite integrity check failed for {dst}: {result}")
    return True


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def entry_meta(path: Path) -> dict[str, object]:
    st = path.stat()
    meta: dict[str, object] = {
        "source": str(path),
        "relative_to_home": relhome(path),
        "type": "dir" if path.is_dir() else "file",
        "mode": oct(stat.S_IMODE(st.st_mode)),
        "mtime_utc": dt.datetime.fromtimestamp(st.st_mtime, dt.timezone.utc).isoformat(),
    }
    if path.is_file():
        meta["size_bytes"] = st.st_size
    elif path.is_dir():
        count = 0
        total = 0
        for dp, dns, fns in os.walk(path):
            dns[:] = [d for d in dns if d not in COPY_EXCLUDE_DIRS]
            for fn in fns:
                fp = Path(dp) / fn
                try:
                    total += fp.stat().st_size
                    count += 1
                except OSError:
                    pass
        meta["file_count"] = count
        meta["size_bytes"] = total
    return meta


def safe_secret_entry_meta(path: Path) -> dict[str, object]:
    """Metadata used for secret-change detection without reading or hashing values.

    File contents are never inspected here. For credential directories, include a bounded
    child inventory of relative paths, file modes, sizes, and mtimes so changes inside a
    directory do not wait until the weekly refresh.
    """
    meta = entry_meta(path)
    if not path.is_dir():
        return meta

    children: list[dict[str, object]] = []
    for dp, dns, fns in os.walk(path):
        dns[:] = [d for d in dns if d not in COPY_EXCLUDE_DIRS and not any(fnmatch.fnmatch(d, pat) for pat in COPY_EXCLUDE_PATTERNS)]
        for fn in sorted(fns):
            fp = Path(dp) / fn
            if fp.suffix.lower() in COPY_EXCLUDE_SUFFIXES:
                continue
            try:
                st = fp.stat()
            except OSError:
                continue
            children.append({
                "relative_path": str(fp.relative_to(path)),
                "type": "dir" if fp.is_dir() else "file",
                "mode": oct(stat.S_IMODE(st.st_mode)),
                "mtime_utc": dt.datetime.fromtimestamp(st.st_mtime, dt.timezone.utc).isoformat(),
                "size_bytes": st.st_size if fp.is_file() else None,
            })
    children.sort(key=lambda item: str(item.get("relative_path", "")))
    meta["child_inventory"] = children[:1000]
    meta["child_inventory_truncated"] = len(children) > 1000
    meta["child_inventory_count"] = len(children)
    return meta


def secret_source_paths() -> list[Path]:
    paths = [
        HERMES / ".env",
        HERMES / "auth.json",
        HERMES / "credentials",
        HERMES / "gmail_app_password",
        HERMES / "config.yaml",
        HERMES / "channel_directory.json",
        HERMES / "pairing",
        HOME / ".codex" / "auth.json",
        HOME / ".codex" / "config.toml",
        HOME / ".config" / "himalaya" / "config.toml",
    ]
    paths.extend(sorted(HERMES.glob(".env.bak.*")))
    paths.extend(sorted(HERMES.glob("config.yaml.bak*")))
    return paths


def current_secret_source_entries() -> list[dict[str, object]]:
    return [safe_secret_entry_meta(src) for src in secret_source_paths() if src.exists()]


def normalize_source_entries(entries: list[dict[str, object]] | None) -> list[dict[str, object]]:
    return sorted(entries or [], key=lambda item: str(item.get("source", "")))


def change_detection_source_entries(entries: list[dict[str, object]] | None) -> list[dict[str, object]]:
    """Filter high-churn non-credential private metadata out of on-change detection.

    These sources still stay inside the encrypted weekly bundle; they just do not force
    fresh `age` ciphertext on ordinary daily/chat activity.
    """
    return normalize_source_entries([
        entry for entry in (entries or [])
        if str(entry.get("source")) not in SECRET_CHANGE_DETECT_EXCLUDE_SOURCES
    ])


def copy_to_stage(
    src: Path,
    stage_root: Path,
    manifest_entries: list[dict[str, object]],
    *,
    dest_rel: str | None = None,
    meta_fn: Callable[[Path], dict[str, object]] = entry_meta,
) -> None:
    if not src.exists():
        return
    rel = Path(dest_rel) if dest_rel else Path(relhome(src))
    dst = stage_root / rel
    manifest_entries.append(meta_fn(src))
    if src.is_dir():
        copy_tree(src, dst)
    elif src.is_file():
        copy_file(src, dst)


def load_age_recipients(recipients_file: Path) -> list[str]:
    if not recipients_file.exists():
        raise RuntimeError(f"Missing age recipients file: {recipients_file}")
    recipients: list[str] = []
    for raw in recipients_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        recipients.append(line)
    if not recipients:
        raise RuntimeError(f"Age recipients file is empty: {recipients_file}")
    return recipients


def recipient_metadata(recipients: list[str]) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for recipient in recipients:
        parts = recipient.split(maxsplit=2)
        entries.append({
            "type": parts[0] if parts else None,
            "comment": parts[2] if len(parts) > 2 else None,
        })
    return entries


def make_archive(stage_root: Path, out_file: Path, recipients_file: Path) -> None:
    ensure_parent(out_file)
    if out_file.exists():
        out_file.unlink()
    # Archive contents of stage root, not the temp parent. Deterministic metadata is not required for disaster backup.
    cmd = 'set -euo pipefail; tar -C "$1" -cf - . | zstd -10 -T0 -q | age -R "$2" -o "$3"'
    run(["bash", "-c", cmd, "bash", str(stage_root), str(recipients_file), str(out_file)], capture=True)


def split_if_needed(path: Path) -> list[Path]:
    if path.stat().st_size <= SPLIT_BYTES:
        return [path]
    prefix = path.with_name(path.name + ".part")
    for old in path.parent.glob(path.name + ".part*"):
        old.unlink()
    run(["split", "-b", str(SPLIT_BYTES), "-d", "-a", "3", str(path), str(prefix)], capture=True)
    path.unlink()
    return sorted(path.parent.glob(path.name + ".part*"))


def artifact_manifest(
    kind: str,
    sources: list[dict[str, object]],
    artifact_paths: list[Path],
    archive_basename: str,
    recipients_file: Path,
    identity_file_for_test_decrypt: Path,
    recipients: list[str],
) -> dict[str, object]:
    return {
        "kind": kind,
        "created_at_utc": NOW.isoformat(),
        "timestamp": TS,
        "encryption": {
            "tool": "age",
            "recipients_file": str(recipients_file),
            "recipient_count": len(recipients),
            "recipients": recipient_metadata(recipients),
            "identity_file_for_test_decrypt": str(identity_file_for_test_decrypt),
        },
        "archive_basename": archive_basename,
        "source_entries": sources,
        "artifacts": [
            {
                "path": str(p.relative_to(REPO)),
                "size_bytes": p.stat().st_size,
                "sha256": sha256_file(p),
            }
            for p in artifact_paths
        ],
        "split": len(artifact_paths) > 1,
        "split_bytes": SPLIT_BYTES if len(artifact_paths) > 1 else None,
    }


def git_text(repo: Path, args: list[str]) -> str | None:
    if not (repo / ".git").exists():
        return None
    result = subprocess.run(["git", *args], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", "replace").rstrip("\n")


def command_text(args: list[str]) -> str | None:
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", "replace").rstrip("\n")


def safe_untracked_file(path: Path) -> bool:
    if not path.is_file():
        return False
    if any(part in COPY_EXCLUDE_DIRS or any(fnmatch.fnmatch(part, pat) for pat in COPY_EXCLUDE_PATTERNS) for part in path.parts):
        return False
    name = path.name.lower()
    if name in {".env", "auth.json", "credentials.json", "gmail_app_password"}:
        return False
    if any(marker in name for marker in ("secret", "token", "password", "passwd", "private_key")):
        return False
    if path.suffix.lower() in COPY_EXCLUDE_SUFFIXES | {".db", ".sqlite", ".sqlite3", ".pem", ".key", ".p12", ".pfx"}:
        return False
    try:
        return path.stat().st_size < 10 * 1024 * 1024
    except OSError:
        return False


def tree_summary(root: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    if not root.exists() or not root.is_dir():
        return entries
    for child in sorted(p for p in root.iterdir() if not p.name.startswith(".")):
        if child.name in COPY_EXCLUDE_DIRS or any(fnmatch.fnmatch(child.name, pat) for pat in COPY_EXCLUDE_PATTERNS):
            continue
        if child.is_dir():
            count = 0
            total = 0
            for dp, dns, fns in os.walk(child):
                dns[:] = [d for d in dns if d not in COPY_EXCLUDE_DIRS and not any(fnmatch.fnmatch(d, pat) for pat in COPY_EXCLUDE_PATTERNS)]
                for fn in fns:
                    fp = Path(dp) / fn
                    if fp.suffix.lower() in COPY_EXCLUDE_SUFFIXES:
                        continue
                    try:
                        total += fp.stat().st_size
                        count += 1
                    except OSError:
                        pass
            entries.append({"name": child.name, "type": "dir", "file_count": count, "size_bytes": total})
        elif child.is_file() and child.suffix.lower() not in COPY_EXCLUDE_SUFFIXES:
            entries.append({"name": child.name, "type": "file", "file_count": 1, "size_bytes": child.stat().st_size})
    return entries


def collect_cli_backup(summary: dict[str, object]) -> None:
    """Collect reproducible CLI state without vendoring upstream git/venv/cache."""
    cli_root = REPO / "cli"
    reset_dir(cli_root)

    agent_dir = cli_root / "hermes-agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    status_lines = (git_text(HERMES_AGENT, ["status", "--short"]) or "").splitlines()
    tracked_diff_files = (git_text(HERMES_AGENT, ["diff", "--name-only"]) or "").splitlines()
    untracked_files = (git_text(HERMES_AGENT, ["ls-files", "--others", "--exclude-standard"]) or "").splitlines()

    manifest = {
        "kind": "hermes-agent-cli-source-state",
        "created_at_utc": NOW.isoformat(),
        "executable": shutil.which("hermes"),
        "version_output": command_text(["hermes", "--version"]) if shutil.which("hermes") else None,
        "source_path": str(HERMES_AGENT),
        "source_exists": HERMES_AGENT.exists(),
        "git_remote": git_text(HERMES_AGENT, ["remote", "get-url", "origin"]),
        "git_branch": git_text(HERMES_AGENT, ["branch", "--show-current"]),
        "git_head": git_text(HERMES_AGENT, ["rev-parse", "HEAD"]),
        "git_head_short": git_text(HERMES_AGENT, ["rev-parse", "--short=12", "HEAD"]),
        "status_count": len(status_lines),
        "status": status_lines,
        "tracked_diff_files": tracked_diff_files,
        "untracked_files": untracked_files,
        "backup_mode": "manifest + tracked git patch + safe untracked source files; full upstream repo, .git, venv, caches excluded",
    }
    (agent_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if tracked_diff_files:
        diff = git_text(HERMES_AGENT, ["diff", "--binary", "--full-index"])
        if diff:
            (agent_dir / "tracked-changes.patch").write_text(diff + "\n", encoding="utf-8")

    copied_untracked: list[str] = []
    untracked_root = agent_dir / "untracked"
    for rel in untracked_files:
        src = HERMES_AGENT / rel
        if safe_untracked_file(src):
            copy_file(src, untracked_root / rel)
            copied_untracked.append(rel)
    (agent_dir / "untracked-manifest.json").write_text(
        json.dumps({"copied": copied_untracked, "skipped_count": len(untracked_files) - len(copied_untracked)}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    skill_clis_dst = cli_root / "skill-clis"
    copy_tree(SKILL_CLIS, skill_clis_dst)
    skill_clis_manifest = {
        "kind": "skill-related-local-clis",
        "created_at_utc": NOW.isoformat(),
        "source_path": str(SKILL_CLIS),
        "source_exists": SKILL_CLIS.exists(),
        "entries": tree_summary(SKILL_CLIS),
        "excluded": sorted(COPY_EXCLUDE_DIRS | COPY_EXCLUDE_PATTERNS | COPY_EXCLUDE_SUFFIXES),
    }
    (skill_clis_dst / "manifest.json").write_text(json.dumps(skill_clis_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    (cli_root / "README.md").write_text(
        "# CLI backup layer\n\n"
        "This directory stores reproducible CLI/source state needed beyond the Hermes overlay.\n\n"
        "## `hermes-agent/`\n\n"
        "The upstream Hermes Agent checkout is **not** vendored wholesale. Restore by installing/cloning upstream, checking out the recorded commit, then applying `tracked-changes.patch` and copying safe files from `untracked/` if still needed.\n\n"
        "## `skill-clis/`\n\n"
        "Source snapshots from `/home/konstantin/code/clis` used by local skills. Generated caches, `.git`, virtualenvs, build outputs, and pycache files are excluded.\n",
        encoding="utf-8",
    )

    summary["cli_backup"] = {
        "hermes_agent_manifest": "cli/hermes-agent/manifest.json",
        "hermes_agent_patch": "cli/hermes-agent/tracked-changes.patch" if tracked_diff_files else None,
        "hermes_agent_untracked_copied": len(copied_untracked),
        "skill_clis": "cli/skill-clis",
        "skill_clis_entries": [entry["name"] for entry in skill_clis_manifest["entries"]],
    }


def collect_plaintext(summary: dict[str, object]) -> None:
    reset_dir(REPO / "docs")
    copy_tree(DOCS, REPO / "docs")

    reset_dir(REPO / "hermes")
    copy_file(HERMES / "SOUL.md", REPO / "hermes" / "SOUL.md")
    copy_tree(HERMES / "memories", REPO / "hermes" / "memories")
    copy_tree(HERMES / "skills", REPO / "hermes" / "skills")
    copy_tree(HERMES / "plugins", REPO / "hermes" / "plugins")
    copy_tree(HERMES / "hooks", REPO / "hermes" / "hooks")
    copy_tree(HERMES / "backups", REPO / "hermes" / "backups")
    copy_tree(HERMES / "plans", REPO / "hermes" / "legacy-plans")
    (REPO / "hermes" / "cron").mkdir(parents=True, exist_ok=True)
    copy_file(HERMES / "cron" / "jobs.json", REPO / "hermes" / "cron" / "jobs.json")

    redact_file(HERMES / "config.yaml", REPO / "hermes" / "config.yaml.redacted")
    write_env_keys(HERMES / ".env", REPO / "hermes" / "env.keys")
    auth_inventory(HERMES / "auth.json", REPO / "hermes" / "auth.inventory.json")

    reset_dir(REPO / "external-integrations")
    redact_file(HOME / ".config" / "himalaya" / "config.toml", REPO / "external-integrations" / "himalaya" / "config.toml.redacted")
    redact_file(HOME / ".codex" / "config.toml", REPO / "external-integrations" / "codex" / "config.toml.redacted")

    mem_dst = REPO / "hermes" / "holographic-memory" / "memory_store.sqlite"
    copied = sqlite_backup(HERMES / "memory_store.db", mem_dst)
    summary["memory_store_snapshot"] = str(mem_dst.relative_to(REPO)) if copied else None

    collect_cli_backup(summary)


def collect_encrypted(summary: dict[str, object], args: argparse.Namespace) -> None:
    for cmd in ["tar", "zstd", "age", "split"]:
        ensure_command(cmd)
    recipients_file = Path(args.recipients_file).expanduser()
    if not recipients_file.is_absolute():
        recipients_file = (REPO / recipients_file).resolve()
    identity_file = Path(args.identity_file_for_test_decrypt).expanduser()
    recipients = load_age_recipients(recipients_file)
    if not identity_file.exists():
        raise RuntimeError(f"Missing age identity private key for test-decrypt: {identity_file}")

    (REPO / "secrets-encrypted").mkdir(exist_ok=True)
    (REPO / "session-history-encrypted").mkdir(exist_ok=True)
    (REPO / "restore").mkdir(exist_ok=True)
    copy_file(recipients_file, REPO / "restore" / "age-recipients.txt")

    with tempfile.TemporaryDirectory(prefix="hermes-backup-stage-") as td:
        tmp = Path(td)

        # Secrets bundle.
        secrets_stage = tmp / "secrets"
        secrets_stage.mkdir()
        secret_sources: list[dict[str, object]] = []
        for src in secret_source_paths():
            copy_to_stage(src, secrets_stage, secret_sources, meta_fn=safe_secret_entry_meta)
        (secrets_stage / "MANIFEST.json").write_text(
            json.dumps({"kind": "secrets", "created_at_utc": NOW.isoformat(), "sources": secret_sources}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        secret_base = f"hermes-secrets-{TS}.tar.zst.age"
        secret_out = REPO / "secrets-encrypted" / secret_base
        make_archive(secrets_stage, secret_out, recipients_file)
        secret_artifacts = split_if_needed(secret_out)
        secret_manifest = artifact_manifest("secrets", secret_sources, secret_artifacts, secret_base, recipients_file, identity_file, recipients)
        (REPO / "secrets-encrypted" / f"manifest-{TS}.json").write_text(json.dumps(secret_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        summary["secret_artifacts"] = [str(p.relative_to(REPO)) for p in secret_artifacts]

        # State + sessions bundle.
        state_stage = tmp / "state"
        state_stage.mkdir()
        state_sources: list[dict[str, object]] = []
        state_db_src = HERMES / "state.db"
        if state_db_src.exists():
            state_sources.append(entry_meta(state_db_src))
            sqlite_backup(state_db_src, state_stage / ".hermes" / "state.db.sqlite")
        copy_to_stage(HERMES / "sessions", state_stage, state_sources)
        copy_to_stage(HERMES / ".hermes_history", state_stage, state_sources)
        for src in sorted(HERMES.glob("state.db.bak-*")):
            copy_to_stage(src, state_stage, state_sources)
        (state_stage / "MANIFEST.json").write_text(
            json.dumps({"kind": "state-and-sessions", "created_at_utc": NOW.isoformat(), "sources": state_sources}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        state_base = f"hermes-state-and-sessions-{TS}.tar.zst.age"
        state_out = REPO / "session-history-encrypted" / state_base
        make_archive(state_stage, state_out, recipients_file)
        state_artifacts = split_if_needed(state_out)
        state_manifest = artifact_manifest("state-and-sessions", state_sources, state_artifacts, state_base, recipients_file, identity_file, recipients)
        (REPO / "session-history-encrypted" / f"manifest-{TS}.json").write_text(json.dumps(state_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        summary["state_artifacts"] = [str(p.relative_to(REPO)) for p in state_artifacts]


def latest_manifest_path(directory: Path) -> Path:
    manifests = sorted(directory.glob("manifest-*.json"))
    if not manifests:
        raise RuntimeError(f"No encrypted manifest found in {directory.relative_to(REPO)}")
    return manifests[-1]


def load_manifest(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def artifact_paths_from_manifest(manifest: dict[str, object]) -> list[Path]:
    paths = [REPO / str(item["path"]) for item in manifest.get("artifacts", [])]
    if not paths:
        raise RuntimeError(f"No artifacts recorded in encrypted manifest {manifest.get('kind')}")
    return paths


def assert_manifest_artifacts_exist(manifest: dict[str, object]) -> list[Path]:
    paths = artifact_paths_from_manifest(manifest)
    missing = [str(p.relative_to(REPO)) for p in paths if not p.exists()]
    if missing:
        raise RuntimeError(f"Encrypted manifest references missing artifacts: {missing}")
    return paths


def parse_manifest_time(manifest: dict[str, object]) -> dt.datetime:
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


def manifest_age_days(manifest: dict[str, object]) -> float:
    return max(0.0, (NOW - parse_manifest_time(manifest)).total_seconds() / 86400)


def load_latest_encrypted_manifests() -> tuple[Path, dict[str, object], Path, dict[str, object]]:
    secret_path = latest_manifest_path(REPO / "secrets-encrypted")
    state_path = latest_manifest_path(REPO / "session-history-encrypted")
    secret_manifest = load_manifest(secret_path)
    state_manifest = load_manifest(state_path)
    assert_manifest_artifacts_exist(secret_manifest)
    assert_manifest_artifacts_exist(state_manifest)
    return secret_path, secret_manifest, state_path, state_manifest


def generated_encrypted_files(directory: Path, artifact_prefix: str) -> list[Path]:
    files: list[Path] = []
    for pattern in ("manifest-*.json", f"{artifact_prefix}-*.tar.zst.age*"):
        files.extend(p for p in directory.glob(pattern) if p.is_file())
    return sorted(set(files))


def apply_latest_retention(secret_manifest_path: Path, secret_manifest: dict[str, object], state_manifest_path: Path, state_manifest: dict[str, object]) -> list[str]:
    keep = {secret_manifest_path.resolve(), state_manifest_path.resolve()}
    keep.update(p.resolve() for p in artifact_paths_from_manifest(secret_manifest))
    keep.update(p.resolve() for p in artifact_paths_from_manifest(state_manifest))

    removed: list[str] = []
    for directory, prefix in (
        (REPO / "secrets-encrypted", "hermes-secrets"),
        (REPO / "session-history-encrypted", "hermes-state-and-sessions"),
    ):
        for path in generated_encrypted_files(directory, prefix):
            if path.resolve() in keep:
                continue
            removed.append(str(path.relative_to(REPO)))
            path.unlink()
    return removed


def populate_encrypted_summary(
    summary: dict[str, object],
    secret_manifest_path: Path,
    secret_manifest: dict[str, object],
    state_manifest_path: Path,
    state_manifest: dict[str, object],
    *,
    refreshed: bool,
    policy: dict[str, object],
) -> None:
    secret_paths = artifact_paths_from_manifest(secret_manifest)
    state_paths = artifact_paths_from_manifest(state_manifest)
    summary["secret_artifacts"] = [str(p.relative_to(REPO)) for p in secret_paths]
    summary["state_artifacts"] = [str(p.relative_to(REPO)) for p in state_paths]
    summary["secret_manifest"] = str(secret_manifest_path.relative_to(REPO))
    summary["state_manifest"] = str(state_manifest_path.relative_to(REPO))
    summary["latest_secret_timestamp"] = secret_manifest.get("timestamp")
    summary["latest_state_timestamp"] = state_manifest.get("timestamp")
    summary["encrypted_refreshed"] = refreshed
    summary["encrypted_policy"] = policy


def decide_encrypted_refresh(args: argparse.Namespace) -> tuple[bool, str, dict[str, object]]:
    policy: dict[str, object] = {
        "mode": args.encrypted_mode,
        "weekly_encrypted_dow": args.weekly_encrypted_dow,
        "local_weekday": LOCAL_NOW.weekday(),
        "local_time": LOCAL_NOW.isoformat(),
        "max_encrypted_age_days": args.max_encrypted_age_days,
        "retention": args.retention,
    }

    try:
        _secret_path, secret_manifest, _state_path, state_manifest = load_latest_encrypted_manifests()
        secret_age = manifest_age_days(secret_manifest)
        state_age = manifest_age_days(state_manifest)
        policy.update({
            "latest_secret_timestamp": secret_manifest.get("timestamp"),
            "latest_state_timestamp": state_manifest.get("timestamp"),
            "secret_age_days": round(secret_age, 4),
            "state_age_days": round(state_age, 4),
        })
    except Exception as exc:
        policy["existing_encrypted_ok"] = False
        policy["existing_encrypted_error"] = f"{type(exc).__name__}: {exc}"
        if args.encrypted_mode == "never":
            raise RuntimeError(f"--encrypted-mode never cannot run without valid existing encrypted artifacts: {exc}") from exc
        return True, "missing_or_invalid_existing_encrypted", policy

    policy["existing_encrypted_ok"] = True
    stale = secret_age > args.max_encrypted_age_days or state_age > args.max_encrypted_age_days
    policy["encrypted_stale"] = stale

    current_secret_entries = change_detection_source_entries(current_secret_source_entries())
    latest_secret_entries = change_detection_source_entries(secret_manifest.get("source_entries") if isinstance(secret_manifest.get("source_entries"), list) else [])
    secret_metadata_changed = current_secret_entries != latest_secret_entries
    policy["secret_metadata_changed"] = secret_metadata_changed
    policy["secret_source_count"] = len(current_secret_entries)
    policy["secret_change_detection_excluded_sources"] = sorted(SECRET_CHANGE_DETECT_EXCLUDE_SOURCES)

    if args.encrypted_mode == "always":
        return True, "forced_always", policy
    if stale:
        if args.encrypted_mode == "never":
            raise RuntimeError("--encrypted-mode never refused: existing encrypted artifacts are stale")
        return True, "stale_existing_encrypted", policy
    if secret_metadata_changed:
        if args.encrypted_mode == "never":
            raise RuntimeError("--encrypted-mode never refused: secret source metadata changed")
        return True, "secret_metadata_changed", policy
    if args.encrypted_mode == "never":
        return False, "forced_never_reuse", policy
    if LOCAL_NOW.weekday() == args.weekly_encrypted_dow:
        return True, "weekly_due", policy
    return False, "fresh_reuse", policy


def apply_encrypted_policy(summary: dict[str, object], args: argparse.Namespace) -> None:
    should_refresh, reason, policy = decide_encrypted_refresh(args)
    policy["refresh_reason"] = reason

    if should_refresh:
        collect_encrypted(summary, args)
        secret_path, secret_manifest, state_path, state_manifest = load_latest_encrypted_manifests()
        refreshed = True
    else:
        secret_path, secret_manifest, state_path, state_manifest = load_latest_encrypted_manifests()
        refreshed = False

    removed: list[str] = []
    if args.retention == "latest":
        removed = apply_latest_retention(secret_path, secret_manifest, state_path, state_manifest)
        # Re-assert after cleanup to catch stale manifest references immediately.
        assert_manifest_artifacts_exist(secret_manifest)
        assert_manifest_artifacts_exist(state_manifest)
    policy["retention_removed_count"] = len(removed)
    policy["retention_removed"] = removed
    populate_encrypted_summary(
        summary,
        secret_path,
        secret_manifest,
        state_path,
        state_manifest,
        refreshed=refreshed,
        policy=policy,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect Konstantin's Hermes overlay backup safely.")
    parser.add_argument(
        "--encrypted-mode",
        choices=["auto", "always", "never"],
        default="auto",
        help="auto refreshes weekly/on-change/stale/missing encrypted artifacts; always forces refresh; never reuses existing fresh artifacts or fails safe.",
    )
    parser.add_argument(
        "--weekly-encrypted-dow",
        type=int,
        default=DEFAULT_WEEKLY_ENCRYPTED_DOW,
        choices=range(7),
        metavar="0-6",
        help="Local weekday for scheduled encrypted refresh, Python convention Monday=0 ... Sunday=6. Default: Sunday.",
    )
    parser.add_argument(
        "--max-encrypted-age-days",
        type=float,
        default=DEFAULT_MAX_ENCRYPTED_AGE_DAYS,
        help="Fail or refresh when latest encrypted artifacts are older than this many days.",
    )
    parser.add_argument(
        "--retention",
        choices=["latest", "keep"],
        default=ENCRYPTED_RETENTION,
        help="Retention for generated encrypted artifacts in HEAD. Default latest keeps only the latest active generation.",
    )
    parser.add_argument(
        "--recipients-file",
        default=str(DEFAULT_RECIPIENTS_FILE),
        help="age recipients file used for encrypted artifacts. Relative paths resolve from the backup repo root.",
    )
    parser.add_argument(
        "--identity-file-for-test-decrypt",
        default=str(DEFAULT_IDENTITY_FILE),
        help="Local age/SSH identity expected to decrypt the archive during verifier runs on this machine.",
    )
    return parser.parse_args(argv)


def write_manifest(summary: dict[str, object]) -> None:
    manifest = {
        "created_at_utc": NOW.isoformat(),
        "timestamp": TS,
        "source_home": str(HOME),
        "hermes_home": str(HERMES),
        "upstream_source_checkout": str(HERMES_AGENT),
        "upstream_source_backup_mode": "manifest+patch, not full vendored repo",
        "skill_clis_source": str(SKILL_CLIS),
        **summary,
    }
    (REPO / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md = [
        "# Backup manifest\n\n",
        f"Created UTC: `{NOW.isoformat()}`\n\n",
        f"Hermes home: `{HERMES}`\n\n",
        f"Hermes Agent source checkout: `{HERMES_AGENT}`\n\n",
        "Upstream source backup mode: `manifest + patch`, not full vendored repo.\n\n",
        f"Skill CLIs source: `{SKILL_CLIS}`\n\n",
        "## Plaintext snapshot\n\n",
        f"- Holographic memory snapshot: `{summary.get('memory_store_snapshot')}`\n",
        f"- CLI backup: `{summary.get('cli_backup')}`\n\n",
        "## Encrypted artifacts\n\n",
        f"- Policy: `{summary.get('encrypted_policy')}`\n",
        f"- Refreshed this run: `{summary.get('encrypted_refreshed')}`\n",
        f"- Secrets manifest: `{summary.get('secret_manifest')}`\n",
        f"- State/sessions manifest: `{summary.get('state_manifest')}`\n\n",
    ]
    for key in ("secret_artifacts", "state_artifacts"):
        md.append(f"### {key}\n")
        for p in summary.get(key, []):
            md.append(f"- `{p}`\n")
        md.append("\n")
    md.append("Raw secret values and transcript contents are intentionally absent from this manifest.\n")
    (REPO / "MANIFEST.md").write_text("".join(md), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not HERMES.exists():
        raise RuntimeError(f"Hermes home not found: {HERMES}")
    summary: dict[str, object] = {}
    collect_plaintext(summary)
    summary["plaintext_files_sanitized"] = sanitize_plaintext_tree()
    apply_encrypted_policy(summary, args)
    write_manifest(summary)
    print(json.dumps({"ok": True, "timestamp": TS, **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
