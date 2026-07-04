from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from .. import __skill_name__, __skill_version__, __version__
from ..command_surface import (
    CATALOG_AUTO_REFRESH_COMMANDS,
    CATALOG_READ_COMMANDS,
    CATALOG_REFRESH_COMMANDS,
    LIVE_PROVIDER_COMMANDS,
    PRIMARY_ROUTE_COMMAND,
    TARGETED_PROBE_COMMANDS,
)
from ..config import (
    DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS,
    DEFAULT_ROUTE_HUB_NOTES,
    DEFAULT_ROUTE_HUBS,
    RISK_PROFILES,
)
from ..providers.route_intel import svx_route_index_path
from ..providers.static_catalog import (
    active_catalog_manifest,
    catalog_staleness,
    download_static_catalog,
    parse_ttl_seconds,
)
from ..store import Store
from ..version_manifest import (
    expected_command_surface,
    load_version_manifest,
    manifest_mismatches,
    manifest_path,
    source_skill_path,
)
from .metadata import metadata_evidence_scope


def command_maint_doctor(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    cache_files = {}
    for name in [
        "countries.json",
        "cities_ru.json",
        "cities_en.json",
        "airports_en.json",
        "airports_ru.json",
        "airlines_en.json",
        "airlines_ru.json",
        "alliances.json",
        "planes.json",
        "catalog_manifest.json",
    ]:
        path = store.cache_dir / name
        cache_files[name] = {"exists": path.exists(), "path": str(path)}
    route_index_path = svx_route_index_path(store.cache_dir / "route_intel")
    max_age_seconds = parse_ttl_seconds(args.catalog_max_age)
    skill_path = source_skill_path()
    manifest = load_version_manifest(skill_path)
    return {
        "version": __version__,
        "cli": {"name": "flights-cli", "version": __version__},
        "skill": {"name": __skill_name__, "version": __skill_version__},
        "version_manifest": {
            "path": str(manifest_path(skill_path)),
            "exists": bool(manifest),
            "mismatches": manifest_mismatches(manifest),
        },
        "python": sys.executable,
        "offline_first": True,
        "cache_dir": str(store.cache_dir),
        "cache_dir_exists": store.cache_dir.exists(),
        "cache_files": cache_files,
        "route_intel_cache": {
            "svx_official_route_index": {
                "exists": route_index_path.exists(),
                "path": str(route_index_path),
            }
        },
        "cache_counts": store.cache_counts(),
        "catalog_auto_refresh_policy": {
            "mode": args.catalog_refresh,
            "max_age": args.catalog_max_age,
            "max_age_seconds": max_age_seconds,
            "timeout": args.catalog_refresh_timeout,
            "applies_to": list(CATALOG_AUTO_REFRESH_COMMANDS),
            "auto_refresh_commands": list(CATALOG_AUTO_REFRESH_COMMANDS),
            "catalog_read_commands": list(CATALOG_READ_COMMANDS),
            "manual_refresh_commands": list(CATALOG_REFRESH_COMMANDS),
            "explicit_refresh_command": "maint catalog refresh",
        },
        "catalog_staleness": catalog_staleness(
            store.cache_dir, max_age_seconds=max_age_seconds
        ),
        "runtime_evidence_policy": {
            "live_cache": {
                "status_values": [
                    "live",
                    "cache_hit",
                    "stale_cache_used",
                    "disabled",
                    "unknown",
                ],
                "default_ttl_seconds": DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS,
            },
            "request_deduplication": {
                "scope": "in_process_identical_segment_probes",
                "network_calls_for_duplicates": False,
            },
            "retry_policy": {
                "active_retry": False,
                "retry_after_is_classified_only": True,
            },
            "failure_classification": {
                "preserves_original_error_type": True,
                "classes": [
                    "rate_limited",
                    "timeout",
                    "provider_unavailable",
                    "blocked_response",
                    "parse_error",
                    "upstream_error",
                ],
            },
            "live_network_checks_in_doctor": False,
        },
        "default_route_hubs": [
            {"code": hub, "note": DEFAULT_ROUTE_HUB_NOTES.get(hub)}
            for hub in DEFAULT_ROUTE_HUBS
        ],
        "safety": {
            "booking_or_purchase": False,
            "docker_touched": False,
            "primary_route_command": PRIMARY_ROUTE_COMMAND,
            "targeted_probe_commands": list(TARGETED_PROBE_COMMANDS),
            "live_provider_commands": list(LIVE_PROVIDER_COMMANDS),
        },
        "risk_profiles": {
            name: {
                "description": config["description"],
                "rank_order": config["rank_order"],
                "ideal_same_min": config["ideal_same_min"],
                "ideal_same_max": config["ideal_same_max"],
            }
            for name, config in RISK_PROFILES.items()
        },
    }


def command_maint_catalog_refresh(
    args: argparse.Namespace, store: Store
) -> dict[str, Any]:
    result = download_static_catalog(
        store.cache_dir,
        names=args.only,
        timeout=args.timeout,
        dry_run=args.dry_run,
    )
    result["evidence_scope"] = metadata_evidence_scope("maint catalog refresh")
    return result


def command_maint_catalog_manifest(
    args: argparse.Namespace, store: Store
) -> dict[str, Any]:
    max_age_seconds = parse_ttl_seconds(args.catalog_max_age)
    manifest = active_catalog_manifest(store.load_manifest())
    return {
        "cache_dir": str(store.cache_dir),
        "evidence_scope": metadata_evidence_scope("maint catalog manifest"),
        "manifest": manifest,
        "cache_counts": store.cache_counts(),
        "catalog_staleness": catalog_staleness(
            store.cache_dir, max_age_seconds=max_age_seconds
        ),
    }


_GENERATED_DIR_NAMES = {"__pycache__", ".pytest_cache"}
_GENERATED_SUFFIXES = (".pyc", ".pyo")
_GENERATED_NAME_SUFFIXES = (".egg-info",)
_SKILL_RELATIVE_PATH = Path("skills") / "productivity" / "flight-search"


def _source_skill_path() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_runtime_skill_path() -> Path:
    hermes_home = Path(
        os.getenv("HERMES_HOME", str(Path.home() / ".hermes"))
    ).expanduser()
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
        return {
            "status": "not_git",
            "repo_root": None,
            "branch": None,
            "head": None,
            "dirty": None,
        }
    branch = _git_output(["branch", "--show-current"], skill_path) or None
    head = _git_output(["rev-parse", "--short=12", "HEAD"], skill_path) or None
    porcelain = _git_output(
        ["status", "--porcelain=v1", "--untracked-files=all"], skill_path
    )
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
        generated_dirs = [
            name for name in list(dirnames) if _is_generated_path(current_path / name)
        ]
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
        dirnames[:] = [
            name for name in dirnames if not _is_generated_path(current_path / name)
        ]
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
    changed = {
        key
        for key in source_keys & runtime_keys
        if source_manifest[key] != runtime_manifest[key]
    }
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
        doctor = command_maint_doctor(args, store)
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
    skill_manifest = (
        manifest.get("skill") if isinstance(manifest.get("skill"), dict) else {}
    )
    cli_manifest = manifest.get("cli") if isinstance(manifest.get("cli"), dict) else {}
    command_surface = (
        manifest.get("command_surface")
        if isinstance(manifest.get("command_surface"), dict)
        else {}
    )
    parity_status = str(parity.get("status") or "unknown")
    runtime_claims_allowed = (
        parity_status in {"same_path", "equal"} and not manifest_mismatch_keys
    )
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
        "command_surface": expected_command_surface(),
        "parity": {
            "status": parity_status,
            "runtime_claims_allowed": runtime_claims_allowed,
            "claim_basis": "runtime_matches_source"
            if runtime_claims_allowed
            else "source_only_not_runtime_proven",
        },
    }


def build_maintenance_report(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    source_path = _source_skill_path()
    runtime_path = (
        Path(args.runtime_path).expanduser()
        if getattr(args, "runtime_path", None)
        else _default_runtime_skill_path()
    )
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
