from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]


def load_script(relative_path: str):
    path = REPO / relative_path
    spec = importlib.util.spec_from_file_location(path.stem.replace('-', '_'), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_verify_cli_backup_allows_absent_legacy_skill_clis(tmp_path):
    verify = load_script("scripts/verify-hermes-backup.py")
    verify.REPO = tmp_path

    agent_dir = tmp_path / "cli" / "hermes-agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "manifest.json").write_text(
        json.dumps({"status_count": 0, "git_head_short": "abc123", "tracked_diff_files": []}) + "\n",
        encoding="utf-8",
    )

    result = verify.verify_cli_backup()

    assert result["hermes_agent_status_count"] == 0
    assert result["hermes_agent_head_short"] == "abc123"
    assert result["legacy_skill_clis_present"] is False
    assert "skill_clis_entries" not in result


def test_verify_cli_backup_rejects_legacy_skill_clis_if_present(tmp_path):
    verify = load_script("scripts/verify-hermes-backup.py")
    verify.REPO = tmp_path

    agent_dir = tmp_path / "cli" / "hermes-agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "manifest.json").write_text(
        json.dumps({"status_count": 0, "git_head_short": "abc123", "tracked_diff_files": []}) + "\n",
        encoding="utf-8",
    )
    legacy_dir = tmp_path / "cli" / "skill-clis"
    legacy_dir.mkdir()
    (legacy_dir / "manifest.json").write_text(
        json.dumps({"entries": [{"name": "flights"}]}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Legacy skill CLIs backup layer should be absent"):
        verify.verify_cli_backup()


def test_collect_cli_backup_does_not_create_legacy_skill_clis(tmp_path, monkeypatch):
    collect = load_script("scripts/collect-hermes-backup.py")
    repo = tmp_path / "backup"
    hermes_agent = tmp_path / "hermes-agent"
    legacy_skill_clis = tmp_path / "legacy-clis"
    (legacy_skill_clis / "flights").mkdir(parents=True)
    (legacy_skill_clis / "flights" / "pyproject.toml").write_text("[project]\nname='flights-cli'\n", encoding="utf-8")

    collect.REPO = repo
    collect.HERMES_AGENT = hermes_agent
    collect.SKILL_CLIS = legacy_skill_clis
    monkeypatch.setattr(collect, "git_text", lambda _repo, _args: "")
    monkeypatch.setattr(collect, "command_text", lambda _cmd: "Hermes Agent test")
    monkeypatch.setattr(collect.shutil, "which", lambda name: "/usr/bin/hermes" if name == "hermes" else None)

    summary: dict[str, object] = {}
    collect.collect_cli_backup(summary)

    assert (repo / "cli" / "hermes-agent" / "manifest.json").exists()
    assert not (repo / "cli" / "skill-clis").exists()
    assert summary["cli_backup"] == {
        "hermes_agent_manifest": "cli/hermes-agent/manifest.json",
        "hermes_agent_patch": None,
        "hermes_agent_untracked_copied": 0,
    }
    assert "skill-clis" not in (repo / "cli" / "README.md").read_text(encoding="utf-8")


def test_write_manifest_omits_legacy_skill_clis_source(tmp_path):
    collect = load_script("scripts/collect-hermes-backup.py")
    collect.REPO = tmp_path

    collect.write_manifest({"cli_backup": {"hermes_agent_manifest": "cli/hermes-agent/manifest.json"}})

    manifest = json.loads((tmp_path / "MANIFEST.json").read_text(encoding="utf-8"))
    manifest_md = (tmp_path / "MANIFEST.md").read_text(encoding="utf-8")
    assert "skill_clis_source" not in manifest
    assert "Skill CLIs source" not in manifest_md
    assert "skill-clis" not in manifest_md
