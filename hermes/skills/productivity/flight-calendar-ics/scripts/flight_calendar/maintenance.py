"""Read-only maintenance diagnostics for flight-calendar-ics."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import travelpayouts_airport_catalog as airport_catalog

GENERATED_IGNORED = ["__pycache__/", ".pytest_cache/", "*.pyc"]
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def _is_generated(path: Path, root: Path) -> bool:
    rel_parts = path.relative_to(root).parts
    if any(part in {"__pycache__", ".pytest_cache"} for part in rel_parts):
        return True
    return path.suffix == ".pyc"


def _relative_files(root: Path) -> dict[str, str]:
    root = root.resolve()
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if _is_generated(path, root):
            continue
        rel = path.relative_to(root).as_posix()
        files[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def _is_local_markdown_link(target: str) -> bool:
    target = target.strip()
    if not target or target.startswith("#"):
        return False
    lowered = target.lower()
    if "://" in lowered or lowered.startswith(("mailto:", "tel:", "data:")):
        return False
    path_part = target.split("#", 1)[0].split("?", 1)[0]
    return path_part.endswith(".md")


def _markdown_link_target_path(source: Path, raw_target: str) -> Path:
    path_part = raw_target.strip().split("#", 1)[0].split("?", 1)[0]
    return (source.parent / path_part).resolve()


def _reference_source_name(path: Path, skill_root: Path, references_dir: Path) -> str:
    if path == skill_root / "SKILL.md":
        return "SKILL.md"
    if path.is_relative_to(references_dir):
        return path.relative_to(references_dir).as_posix()
    return path.relative_to(skill_root).as_posix()


def _broken_markdown_links(skill_root: Path) -> list[dict[str, str]]:
    skill_root = skill_root.resolve()
    references_dir = skill_root / "references"
    markdown_files = [skill_root / "SKILL.md"] + sorted(references_dir.rglob("*.md"))
    broken: list[dict[str, str]] = []
    for source in markdown_files:
        if not source.exists():
            continue
        source_text = source.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK_RE.finditer(source_text):
            raw_target = match.group(1).strip()
            if not _is_local_markdown_link(raw_target):
                continue
            target_path = _markdown_link_target_path(source, raw_target)
            if not target_path.exists():
                broken.append(
                    {
                        "source": _reference_source_name(source, skill_root, references_dir),
                        "target": raw_target,
                    }
                )
    return sorted(broken, key=lambda item: (item["source"], item["target"]))


def _source_runtime_base(source_dir: Path, runtime_dir: Path) -> dict[str, Any]:
    source_files = _relative_files(source_dir)
    runtime_files = _relative_files(runtime_dir)
    source_names = set(source_files)
    runtime_names = set(runtime_files)
    shared = source_names & runtime_names
    changed = sorted(name for name in shared if source_files[name] != runtime_files[name])
    same = sorted(name for name in shared if source_files[name] == runtime_files[name])
    return {
        "source_only": sorted(source_names - runtime_names),
        "runtime_only": sorted(runtime_names - source_names),
        "changed_shared": changed,
        "same_count": len(same),
        "source_count": len(source_files),
        "runtime_count": len(runtime_files),
    }


def source_runtime_sync_report(source_dir: Path, runtime_dir: Path) -> dict[str, Any]:
    """Return path/hash drift only; never include file contents."""
    return _source_runtime_base(source_dir, runtime_dir)


def source_runtime_diff_report(source_dir: Path, runtime_dir: Path) -> dict[str, Any]:
    """Read-only source/runtime diff with explicit no-content metadata."""
    data = _source_runtime_base(source_dir, runtime_dir)
    data.update(
        {
            "source_path": str(source_dir.resolve()),
            "runtime_path": str(runtime_dir.resolve()),
            "generated_ignored": GENERATED_IGNORED,
            "file_contents_included": False,
        }
    )
    return data


def contracts_report(command_registry: dict[str, list[str]]) -> dict[str, Any]:
    return {
        "checks": {
            "command_registry_present": bool(command_registry),
            "production_happy_path_present": "build auto" in command_registry.get("production", []),
            "diagnose_namespace_present": any(item.startswith("diagnose ") for item in command_registry.get("diagnostic", [])),
            "maint_namespace_present": any(item.startswith("maint ") for item in command_registry.get("maintenance", [])),
        }
    }


def refs_registry_check_report(skill_root: Path) -> dict[str, Any]:
    references_dir = skill_root / "references"
    registry_path = references_dir / "registry.md"
    registry_text = registry_path.read_text(encoding="utf-8")
    canonical_section = registry_text.split("## Canonical owners", 1)[1].split("## Absorbed legacy map", 1)[0]
    owner_paths: list[str] = []
    for line in canonical_section.splitlines():
        match = re.match(r"^\s*-\s+`([^`]+\.md)`", line)
        if match:
            owner_paths.append(match.group(1))
    references_seen = sorted(
        path.relative_to(references_dir).as_posix()
        for path in references_dir.rglob("*.md")
        if path.name != "registry.md"
    )
    seen_counts = {name: owner_paths.count(name) for name in set(owner_paths)}
    duplicate_owners = sorted(name for name, count in seen_counts.items() if count > 1)
    registered = set(owner_paths)
    actual = set(references_seen)
    unregistered = sorted(actual - registered)
    broken_links = sorted(registered - actual)
    broken_markdown_links = _broken_markdown_links(skill_root)
    return {
        "registry_path": str(registry_path.resolve()),
        "references_seen": references_seen,
        "unregistered": unregistered,
        "duplicate_owners": duplicate_owners,
        "broken_links": broken_links,
        "broken_markdown_links": broken_markdown_links,
        "ok": not (unregistered or duplicate_owners or broken_links or broken_markdown_links),
    }


def clean_dry_run_report(target_dir: Path) -> dict[str, Any]:
    target_dir = target_dir.resolve()
    candidates: list[str] = []
    for path in sorted(target_dir.rglob("*")):
        rel = path.relative_to(target_dir).as_posix()
        if path.is_dir() and path.name in {"__pycache__", ".pytest_cache"}:
            candidates.append(f"{rel}/")
        elif path.is_file() and path.suffix == ".pyc":
            candidates.append(rel)
    return {"dry_run": True, "candidates": candidates, "deletions_performed": False}


def timezone_catalog_report(skill_root: Path) -> dict[str, Any]:
    catalog_path = skill_root / "assets" / "travelpayouts" / "airport_timezones.json"
    document = airport_catalog.load_catalog_document(catalog_path)
    timezones = airport_catalog.load_airport_timezones(catalog_path)
    return {
        "catalog_path": str(catalog_path.resolve()),
        "airports_count": len(timezones),
        "timezones_count": len(set(timezones.values())),
        "sample_airports": sorted(timezones)[:8],
        "catalog_schema_version": document.get("schema_version"),
    }


def audit_report(skill_root: Path, source_dir: Path, runtime_dir: Path, target_dir: Path, command_registry: dict[str, list[str]]) -> dict[str, Any]:
    registry = refs_registry_check_report(skill_root)
    return {
        "reports": {
            "contracts": contracts_report(command_registry),
            "refs_registry": {
                "ok": registry["ok"],
                "unregistered_count": len(registry["unregistered"]),
                "broken_links_count": len(registry["broken_links"]),
                "broken_markdown_links_count": len(registry["broken_markdown_links"]),
            },
            "source_runtime": {
                key: value
                for key, value in source_runtime_diff_report(source_dir, runtime_dir).items()
                if key in {"source_only", "runtime_only", "changed_shared", "same_count", "source_count", "runtime_count", "generated_ignored", "file_contents_included"}
            },
            "clean": clean_dry_run_report(target_dir),
            "timezone_catalog": timezone_catalog_report(skill_root),
        }
    }
