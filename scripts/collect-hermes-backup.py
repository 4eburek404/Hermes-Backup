#!/usr/bin/env python3
"""Collect Konstantin's personal Hermes overlay backup.

Safety properties:
- never prints raw secret contents;
- raw credentials and runtime history are staged only in /tmp and committed only as age-encrypted archives;
- live SQLite databases are snapshotted through sqlite3 backup API;
- encrypted archives are split below GitHub's 100 MB regular-file limit when needed.
"""
from __future__ import annotations

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
from typing import Iterable

HOME = Path.home()
HERMES = HOME / ".hermes"
DOCS = HOME / "docs"
CODE = HOME / "code"
HERMES_AGENT = HERMES / "hermes-agent"
SKILL_CLIS = CODE / "clis"
REPO = Path(__file__).resolve().parents[1]
RECIPIENT_FILE = HOME / ".ssh" / "server_monitor_iOS_app_ed25519.pub"
IDENTITY_FILE = HOME / ".ssh" / "server_monitor_iOS_app_ed25519"
SPLIT_BYTES = 45 * 1024 * 1024
NOW = dt.datetime.now(dt.timezone.utc)
TS = os.environ.get("HERMES_BACKUP_TS") or NOW.strftime("%Y%m%d-%H%M%S")

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


def copy_to_stage(src: Path, stage_root: Path, manifest_entries: list[dict[str, object]], *, dest_rel: str | None = None) -> None:
    if not src.exists():
        return
    rel = Path(dest_rel) if dest_rel else Path(relhome(src))
    dst = stage_root / rel
    manifest_entries.append(entry_meta(src))
    if src.is_dir():
        copy_tree(src, dst)
    elif src.is_file():
        copy_file(src, dst)


def make_archive(stage_root: Path, out_file: Path) -> None:
    ensure_parent(out_file)
    if out_file.exists():
        out_file.unlink()
    # Archive contents of stage root, not the temp parent. Deterministic metadata is not required for disaster backup.
    cmd = 'set -euo pipefail; tar -C "$1" -cf - . | zstd -10 -T0 -q | age -R "$2" -o "$3"'
    run(["bash", "-c", cmd, "bash", str(stage_root), str(RECIPIENT_FILE), str(out_file)], capture=True)


def split_if_needed(path: Path) -> list[Path]:
    if path.stat().st_size <= SPLIT_BYTES:
        return [path]
    prefix = path.with_name(path.name + ".part")
    for old in path.parent.glob(path.name + ".part*"):
        old.unlink()
    run(["split", "-b", str(SPLIT_BYTES), "-d", "-a", "3", str(path), str(prefix)], capture=True)
    path.unlink()
    return sorted(path.parent.glob(path.name + ".part*"))


def artifact_manifest(kind: str, sources: list[dict[str, object]], artifact_paths: list[Path], archive_basename: str) -> dict[str, object]:
    return {
        "kind": kind,
        "created_at_utc": NOW.isoformat(),
        "timestamp": TS,
        "encryption": {
            "tool": "age",
            "recipient_file": str(RECIPIENT_FILE),
            "recipient_public_key_type": RECIPIENT_FILE.read_text(encoding="utf-8", errors="replace").split()[0] if RECIPIENT_FILE.exists() else None,
            "identity_file_for_test_decrypt": str(IDENTITY_FILE),
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


def collect_encrypted(summary: dict[str, object]) -> None:
    for cmd in ["tar", "zstd", "age", "split"]:
        ensure_command(cmd)
    if not RECIPIENT_FILE.exists():
        raise RuntimeError(f"Missing age recipient public key: {RECIPIENT_FILE}")
    if not IDENTITY_FILE.exists():
        raise RuntimeError(f"Missing age identity private key for test-decrypt: {IDENTITY_FILE}")

    (REPO / "secrets-encrypted").mkdir(exist_ok=True)
    (REPO / "session-history-encrypted").mkdir(exist_ok=True)
    (REPO / "restore").mkdir(exist_ok=True)
    copy_file(RECIPIENT_FILE, REPO / "restore" / "age-recipient.pub")

    with tempfile.TemporaryDirectory(prefix="hermes-backup-stage-") as td:
        tmp = Path(td)

        # Secrets bundle.
        secrets_stage = tmp / "secrets"
        secrets_stage.mkdir()
        secret_sources: list[dict[str, object]] = []
        for src in [
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
        ]:
            copy_to_stage(src, secrets_stage, secret_sources)
        for src in sorted(HERMES.glob(".env.bak.*")) + sorted(HERMES.glob("config.yaml.bak*")):
            copy_to_stage(src, secrets_stage, secret_sources)
        (secrets_stage / "MANIFEST.json").write_text(
            json.dumps({"kind": "secrets", "created_at_utc": NOW.isoformat(), "sources": secret_sources}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        secret_base = f"hermes-secrets-{TS}.tar.zst.age"
        secret_out = REPO / "secrets-encrypted" / secret_base
        make_archive(secrets_stage, secret_out)
        secret_artifacts = split_if_needed(secret_out)
        secret_manifest = artifact_manifest("secrets", secret_sources, secret_artifacts, secret_base)
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
        make_archive(state_stage, state_out)
        state_artifacts = split_if_needed(state_out)
        state_manifest = artifact_manifest("state-and-sessions", state_sources, state_artifacts, state_base)
        (REPO / "session-history-encrypted" / f"manifest-{TS}.json").write_text(json.dumps(state_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        summary["state_artifacts"] = [str(p.relative_to(REPO)) for p in state_artifacts]


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
    ]
    for key in ("secret_artifacts", "state_artifacts"):
        md.append(f"### {key}\n")
        for p in summary.get(key, []):
            md.append(f"- `{p}`\n")
        md.append("\n")
    md.append("Raw secret values and transcript contents are intentionally absent from this manifest.\n")
    (REPO / "MANIFEST.md").write_text("".join(md), encoding="utf-8")


def main() -> int:
    if not HERMES.exists():
        raise RuntimeError(f"Hermes home not found: {HERMES}")
    summary: dict[str, object] = {}
    collect_plaintext(summary)
    summary["plaintext_files_sanitized"] = sanitize_plaintext_tree()
    collect_encrypted(summary)
    write_manifest(summary)
    print(json.dumps({"ok": True, "timestamp": TS, **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
