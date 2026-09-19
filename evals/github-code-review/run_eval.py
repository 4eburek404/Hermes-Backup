#!/usr/bin/env python3
"""Run the deterministic github-code-review local-diff evaluation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
SCENARIOS = ("scenario-a", "scenario-b", "scenario-c")
MODEL = "gpt-5.6-luna"
PROVIDER = "openai-codex"
HERMES = shutil.which("hermes") or "hermes"


def run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None,
        check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True, check=check)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git(repo: Path, *args: str, check: bool = True) -> str:
    return run(["git", "-C", str(repo), *args], check=check).stdout.strip()


def materialize(scenario: str, destination: Path) -> dict[str, str]:
    source = ROOT / "fixtures" / scenario
    destination.mkdir(parents=True)
    for item in source.iterdir():
        if item.name in {"review.patch", "__pycache__"}:
            continue
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
    run(["git", "init", "-q"], cwd=destination)
    run(["git", "config", "user.name", "Hermes Eval Fixture"], cwd=destination)
    run(["git", "config", "user.email", "fixture@example.invalid"], cwd=destination)
    run(["git", "add", "."], cwd=destination)
    base_env = {**os.environ, "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z"}
    run(["git", "commit", "-q", "-m", "fixture base"], cwd=destination, env=base_env)
    base_sha = git(destination, "rev-parse", "HEAD")
    patch = source / "review.patch"
    run(["git", "apply", str(patch)], cwd=destination)
    run(["git", "add", "."], cwd=destination)
    run(["git", "commit", "-q", "-m", "fixture review change"], cwd=destination, env=base_env)
    review_sha = git(destination, "rev-parse", "HEAD")
    run(["git", "reset", "-q", "--mixed", base_sha], cwd=destination)
    return {"base_sha": base_sha, "review_commit_sha": review_sha}


def snapshot(repo: Path) -> dict:
    status = git(repo, "status", "--porcelain=v1")
    names = set(git(repo, "ls-files").splitlines())
    names.update(git(repo, "ls-files", "--others", "--exclude-standard").splitlines())
    files = {}
    for name in sorted(n for n in names if n):
        path = repo / name
        if path.is_file():
            files[name] = sha256(path)
    return {"head": git(repo, "rev-parse", "HEAD"), "status_porcelain": status, "file_sha256": files}


def build_skill_root(version: str, root: Path) -> tuple[Path, str, str]:
    target = root / "skills"
    shutil.copytree(REPO_ROOT / "hermes" / "skills", target, symlinks=False)
    skill = target / "github" / "github-code-review" / "SKILL.md"
    if version == "baseline":
        skill.write_text(run(["git", "show", "0239f4d:hermes/skills/github/github-code-review/SKILL.md"], cwd=REPO_ROOT).stdout, encoding="utf-8")
    else:
        shutil.copy2(REPO_ROOT / "hermes/skills/github/github-code-review/SKILL.md", skill)
    return target, sha256(skill), sha256(REPO_ROOT / "hermes/skills/github/github-code-review/SKILL.md")


def make_home(home: Path, skill_root: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "skills").symlink_to(skill_root, target_is_directory=True)
    for name in (".env", "auth.json"):
        source = Path.home() / ".hermes" / name
        if source.exists():
            (home / name).symlink_to(source)


def event_summary(stdout: str) -> dict:
    events = []
    for line in stdout.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value.get("type"):
            events.append(value)
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    tools = [e for e in events if e.get("type") in {"tool_use", "tool_result"}]
    commands = []
    for event in events:
        if event.get("type") == "tool_use" and event.get("name") == "terminal":
            args = event.get("input") or {}
            command = args.get("command") if isinstance(args, dict) else None
            if command:
                commands.append(command)
    return {"event_count": len(events), "tool_event_count": len(tools), "tool_calls": commands,
            "terminal_result": result, "verification_commands": commands}


def prepare_only() -> int:
    with tempfile.TemporaryDirectory(prefix="github-review-fixture-") as temp:
        output = {}
        for scenario in SCENARIOS:
            output[scenario] = materialize(scenario, Path(temp) / scenario)
        print(json.dumps(output, indent=2, sort_keys=True))
    return 0


def run_one(scenario: str, version: str, run_dir: Path) -> dict:
    run_dir.mkdir(parents=True, exist_ok=False)
    fixture = run_dir / "fixture-repo"
    versions = materialize(scenario, fixture)
    expected_manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))["scenarios"][scenario]
    if versions["base_sha"] != expected_manifest["fixture_base_sha"] or versions["review_commit_sha"] != expected_manifest["fixture_review_commit_sha"]:
        raise RuntimeError(f"fixture SHA drift for {scenario}: {versions} != {expected_manifest}")
    prompt = ROOT / "prompt" / f"{scenario}.txt"
    (run_dir / "prompt.txt").write_text(prompt.read_text(encoding="utf-8"), encoding="utf-8")
    pre = snapshot(fixture)
    home = Path(tempfile.mkdtemp(prefix="hermes-home-", dir="/tmp"))
    skill_home = Path(tempfile.mkdtemp(prefix="hermes-skills-", dir="/tmp"))
    try:
        skill_root, skill_sha, candidate_sha = build_skill_root(version, skill_home)
        make_home(home, skill_root)
        env = os.environ.copy()
        env.update({"HERMES_HOME": str(home), "HOME": str(Path.home()), "TERMINAL_CWD": str(fixture), "PYTHONDONTWRITEBYTECODE": "1"})
        command = [HERMES, "chat", "--query-file", str(prompt), "--oneshot", "--quiet",
                   "--format", "stream-json", "--model", MODEL, "--provider", PROVIDER,
                   "--toolsets", "terminal,file,skills", "--skills", "github-code-review",
                   "--max-turns", "30", "--run-budget", "180", "--yolo", "--source", "eval"]
        started = datetime.now(timezone.utc)
        started_mono = time.monotonic()
        proc = subprocess.run(command, cwd=fixture, env=env, text=True, capture_output=True)
        ended = datetime.now(timezone.utc)
        elapsed = time.monotonic() - started_mono
        (run_dir / "raw_stream.jsonl").write_text(proc.stdout, encoding="utf-8")
        (run_dir / "raw_stderr.txt").write_text(proc.stderr, encoding="utf-8")
        summary = event_summary(proc.stdout)
        final_text = str(summary.get("terminal_result", {}).get("text", ""))
        (run_dir / "raw_final_answer.txt").write_text(final_text, encoding="utf-8")
        post = snapshot(fixture)
        if pre != post:
            (run_dir / "post_mutation.diff").write_text(git(fixture, "diff", "--binary"), encoding="utf-8")
            mutation_dir = run_dir / "mutation_files"
            mutation_dir.mkdir()
            for name in post["file_sha256"]:
                if pre["file_sha256"].get(name) != post["file_sha256"].get(name):
                    source = fixture / name
                    if source.is_file():
                        target = mutation_dir / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, target)
        run(["git", "reset", "-q", "--hard", versions["base_sha"]], cwd=fixture, check=False)
        run(["git", "clean", "-q", "-fdx"], cwd=fixture, check=False)
        run(["git", "apply", str(ROOT / "fixtures" / scenario / "review.patch")], cwd=fixture)
        restored = snapshot(fixture)
        atif_atof = [str(path.relative_to(home)) for path in home.rglob("*") if path.is_file() and any(token in path.name.lower() for token in ("atif", "atof"))]
        metadata = {
            "scenario": scenario, "skill_version": version, "skill_sha256": skill_sha,
            "candidate_skill_sha256": candidate_sha, "baseline_commit": "0239f4d",
            "candidate_commit": "98c4db2", "fixture_base_sha": versions["base_sha"],
            "fixture_review_commit_sha": versions["review_commit_sha"], "hermes_executable": HERMES,
            "hermes_version": run([HERMES, "--version"], env=env).stdout.strip(),
            "model": MODEL, "provider": PROVIDER, "toolsets": ["terminal", "file", "skills"],
            "command": command, "started_at": started.isoformat(), "ended_at": ended.isoformat(),
            "elapsed_seconds": elapsed, "exit_code": proc.returncode, "pre_snapshot": pre,
            "post_snapshot": post, "restored_snapshot": restored, "raw_trace_format": "hermes-stream-json",
            "atif_atof_files": atif_atof, "atif_atof_available": bool(atif_atof), "event_summary": summary,
            "mutation_detected": pre != post,
        }
        (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return metadata
    finally:
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(skill_home, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--version", choices=("baseline", "candidate"), default=None)
    parser.add_argument("--runs", type=int, default=3, help="number of scenarios; default 3")
    args = parser.parse_args()
    if args.prepare_only:
        return prepare_only()
    versions = (args.version,) if args.version else ("baseline", "candidate")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    batch = ROOT / "runs" / stamp
    batch.mkdir(parents=True, exist_ok=False)
    all_metadata = []
    for version in versions:
        for scenario in SCENARIOS[:args.runs]:
            run_id = f"{scenario}-{version}"
            print(f"running {run_id}", flush=True)
            all_metadata.append(run_one(scenario, version, batch / run_id))
    (batch / "batch_manifest.json").write_text(json.dumps(all_metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"batch={batch}")
    return 0 if all(item["exit_code"] == 0 for item in all_metadata) else 1


if __name__ == "__main__":
    raise SystemExit(main())
