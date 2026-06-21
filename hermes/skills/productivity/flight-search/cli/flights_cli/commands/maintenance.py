from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from .. import __version__
from ..commands.basic import command_doctor
from ..store import Store
from ..version_manifest import expected_command_surface, load_version_manifest, manifest_mismatches, manifest_path

_GENERATED_DIR_NAMES = {"__pycache__", ".pytest_cache"}
_GENERATED_SUFFIXES = (".pyc", ".pyo")
_GENERATED_NAME_SUFFIXES = (".egg-info",)
_SKILL_RELATIVE_PATH = Path("skills") / "productivity" / "flight-search"


def _source_skill_path() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_runtime_skill_path() -> Path:
    hermes_home = Path(os.getenv("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser()
    return hermes_home / _SKILL_RELATIVE_PATH


def _read_skill_version(skill_path: Path) -> str | None:
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return None
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"(?m)^version:\s*['\"]?([^'\"\s]+)", text)
    return match.group(1) if match else None


def _git_output(args: list[str], cwd: Path) -> str | None:
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _git_info(skill_path: Path) -> dict[str, Any]:
    repo_root = _git_output(["rev-parse", "--show-toplevel"], skill_path)
    if not repo_root:
        return {"status": "not_git", "repo_root": None, "branch": None, "head": None, "dirty": None}
    branch = _git_output(["branch", "--show-current"], skill_path) or None
    head = _git_output(["rev-parse", "--short=12", "HEAD"], skill_path) or None
    porcelain = _git_output(["status", "--porcelain=v1", "--untracked-files=all"], skill_path)
    return {
        "status": "ok",
        "repo_root": repo_root,
        "branch": branch,
        "head": head,
        "dirty": bool(porcelain),
    }


def _is_generated_path(path: Path) -> bool:
    name = path.name
    return (
        name in _GENERATED_DIR_NAMES
        or name.endswith(_GENERATED_NAME_SUFFIXES)
        or name.endswith(_GENERATED_SUFFIXES)
    )


def _generated_artifacts(root: Path, *, sample_limit: int = 20) -> dict[str, Any]:
    if not root.exists():
        return {"count": 0, "sample": []}
    count = 0
    sample: list[str] = []
    for current, dirnames, filenames in os.walk(root):
        current_path = Path(current)
        generated_dirs = [name for name in list(dirnames) if _is_generated_path(current_path / name)]
        for name in sorted(generated_dirs):
            count += 1
            if len(sample) < sample_limit:
                sample.append(str((current_path / name).relative_to(root)))
        dirnames[:] = [name for name in dirnames if name not in generated_dirs]
        for name in sorted(filenames):
            path = current_path / name
            if not _is_generated_path(path):
                continue
            count += 1
            if len(sample) < sample_limit:
                sample.append(str(path.relative_to(root)))
    return {"count": count, "sample": sample}


def _reference_count(root: Path) -> int:
    references = root / "references"
    if not references.exists():
        return 0
    return sum(1 for path in references.glob("*.md") if path.is_file())


def _manifest(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not root.exists():
        return result
    for current, dirnames, filenames in os.walk(root):
        current_path = Path(current)
        dirnames[:] = [name for name in dirnames if not _is_generated_path(current_path / name)]
        for name in filenames:
            path = current_path / name
            if _is_generated_path(path):
                continue
            rel = str(path.relative_to(root))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            result[rel] = digest
    return result


def _source_runtime_parity(source_path: Path, runtime_path: Path) -> dict[str, Any]:
    if not runtime_path.exists():
        return {
            "status": "runtime_missing",
            "checked": False,
            "ignored_generated": True,
            "source_only_count": None,
            "runtime_only_count": None,
            "changed_count": None,
        }
    if source_path.resolve() == runtime_path.resolve():
        return {
            "status": "same_path",
            "checked": True,
            "ignored_generated": True,
            "source_only_count": 0,
            "runtime_only_count": 0,
            "changed_count": 0,
        }
    source_manifest = _manifest(source_path)
    runtime_manifest = _manifest(runtime_path)
    source_keys = set(source_manifest)
    runtime_keys = set(runtime_manifest)
    changed = {key for key in source_keys & runtime_keys if source_manifest[key] != runtime_manifest[key]}
    source_only = source_keys - runtime_keys
    runtime_only = runtime_keys - source_keys
    equal = not changed and not source_only and not runtime_only
    return {
        "status": "equal" if equal else "different",
        "checked": True,
        "ignored_generated": True,
        "source_only_count": len(source_only),
        "runtime_only_count": len(runtime_only),
        "changed_count": len(changed),
    }


def _doctor_status(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    try:
        doctor = command_doctor(args, store)
    except Exception as exc:  # pragma: no cover - defensive status reporting
        return {"status": "error", "issues": [f"{type(exc).__name__}: {exc}"]}
    return {
        "status": "ok",
        "issues": [],
        "cli_version": (doctor.get("cli") or {}).get("version"),
        "skill_version": (doctor.get("skill") or {}).get("version"),
    }


def _branch_workflow_summary(
    *,
    source_path: Path,
    runtime_path: Path,
    source_git: dict[str, Any],
    manifest: dict[str, Any],
    manifest_mismatch_keys: list[str],
    parity: dict[str, Any],
) -> dict[str, Any]:
    skill_manifest = manifest.get("skill") if isinstance(manifest.get("skill"), dict) else {}
    cli_manifest = manifest.get("cli") if isinstance(manifest.get("cli"), dict) else {}
    command_surface = manifest.get("command_surface") if isinstance(manifest.get("command_surface"), dict) else {}
    parity_status = str(parity.get("status") or "unknown")
    runtime_claims_allowed = parity_status in {"same_path", "equal"} and not manifest_mismatch_keys
    return {
        "development_branch": "refactor_flights-search",
        "source": {
            "path": str(source_path),
            "branch": source_git.get("branch"),
            "head": source_git.get("head"),
            "dirty": source_git.get("dirty"),
        },
        "runtime": {
            "path": str(runtime_path),
            "exists": runtime_path.exists(),
        },
        "manifest": {
            "skill_version": skill_manifest.get("version"),
            "cli_version": cli_manifest.get("version"),
            "command_surface_version": command_surface.get("version"),
            "mismatches": manifest_mismatch_keys,
        },
        "command_surface": {
            **expected_command_surface(),
            "removed_commands": list(command_surface.get("removed_commands") or []),
        },
        "parity": {
            "status": parity_status,
            "runtime_claims_allowed": runtime_claims_allowed,
            "claim_basis": "runtime_matches_source" if runtime_claims_allowed else "source_only_not_runtime_proven",
        },
    }


def build_maintenance_report(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    source_path = _source_skill_path()
    runtime_path = Path(args.runtime_path).expanduser() if getattr(args, "runtime_path", None) else _default_runtime_skill_path()
    source_generated = _generated_artifacts(source_path)
    runtime_generated = _generated_artifacts(runtime_path)
    source_manifest = load_version_manifest(source_path)
    source_manifest_path = manifest_path(source_path)
    source_git = _git_info(source_path)
    mismatches = manifest_mismatches(source_manifest)
    parity = _source_runtime_parity(source_path, runtime_path)
    return {
        "source": {
            "skill_path": str(source_path),
            "exists": source_path.exists(),
            "git": source_git,
        },
        "runtime": {
            "skill_path": str(runtime_path),
            "exists": runtime_path.exists(),
        },
        "versions": {
            "skill_md": _read_skill_version(source_path),
            "cli": __version__,
        },
        "version_manifest": {
            "path": str(source_manifest_path),
            "exists": source_manifest_path.exists(),
            "data": source_manifest,
            "mismatches": mismatches,
        },
        "source_runtime_parity": parity,
        "branch_workflow": _branch_workflow_summary(
            source_path=source_path,
            runtime_path=runtime_path,
            source_git=source_git,
            manifest=source_manifest,
            manifest_mismatch_keys=mismatches,
            parity=parity,
        ),
        "doctor": _doctor_status(args, store),
        "references": {
            "source_count": _reference_count(source_path),
            "runtime_count": _reference_count(runtime_path),
        },
        "generated_artifacts": {
            "source_count": source_generated["count"],
            "runtime_count": runtime_generated["count"],
            "source_sample": source_generated["sample"],
            "runtime_sample": runtime_generated["sample"],
        },
    }


def command_maintenance_check(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    return build_maintenance_report(args, store)
