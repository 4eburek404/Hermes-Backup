from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evals.harness.core import RunSpec


class GithubCodeReviewConsumer:
    name = "github-code-review"

    def __init__(
        self,
        root: Path,
        repo_root: Path,
        manifest: dict[str, Any],
        hermes_command: list[str] | None = None,
    ) -> None:
        self.root = root
        self.repo_root = repo_root
        self.manifest = manifest
        self.hermes_command = hermes_command or [shutil.which("hermes") or "hermes"]

    @staticmethod
    def _run(
        cmd: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            check=check,
        )

    @staticmethod
    def sha256(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def _git(self, repo: Path, *args: str, check: bool = True) -> str:
        return self._run(["git", "-C", str(repo), *args], check=check).stdout.strip()

    @staticmethod
    def fixture_version(versions: dict[str, str]) -> str:
        return f'{versions["base_sha"]}:{versions["review_commit_sha"]}'

    def materialize(self, scenario: str, destination: Path) -> dict[str, str]:
        source = self.root / "fixtures" / scenario
        destination.mkdir(parents=True)
        for item in source.iterdir():
            if item.name in {"review.patch", "__pycache__"}:
                continue
            target = destination / item.name
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)

        self._run(["git", "init", "-q"], cwd=destination)
        self._run(["git", "config", "user.name", "Hermes Eval Fixture"], cwd=destination)
        self._run(["git", "config", "user.email", "fixture@example.invalid"], cwd=destination)
        self._run(["git", "add", "."], cwd=destination)
        base_env = {
            **os.environ,
            "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z",
            "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
        }
        self._run(["git", "commit", "-q", "-m", "fixture base"], cwd=destination, env=base_env)
        base_sha = self._git(destination, "rev-parse", "HEAD")

        patch = source / "review.patch"
        self._run(["git", "apply", str(patch)], cwd=destination)
        self._run(["git", "add", "."], cwd=destination)
        self._run(
            ["git", "commit", "-q", "-m", "fixture review change"],
            cwd=destination,
            env=base_env,
        )
        review_sha = self._git(destination, "rev-parse", "HEAD")
        self._run(["git", "reset", "-q", "--mixed", base_sha], cwd=destination)
        return {"base_sha": base_sha, "review_commit_sha": review_sha}

    def inspect_fixture(self, scenario: str) -> dict[str, str]:
        with tempfile.TemporaryDirectory(prefix="github-review-fixture-") as temp:
            return self.materialize(scenario, Path(temp) / scenario)

    def snapshot(self, repo: Path) -> dict[str, Any]:
        status = self._git(repo, "status", "--porcelain=v1")
        names = set(self._git(repo, "ls-files").splitlines())
        names.update(
            self._git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
        )
        files: dict[str, str] = {}
        for name in sorted(n for n in names if n):
            path = repo / name
            if path.is_file():
                files[name] = self.sha256(path)
        return {
            "head": self._git(repo, "rev-parse", "HEAD"),
            "status_porcelain": status,
            "file_sha256": files,
        }

    def _build_skill_root(
        self,
        version: str,
        root: Path,
    ) -> tuple[Path, str, str, str]:
        target = root / "skills"
        shutil.copytree(self.repo_root / "hermes" / "skills", target, symlinks=False)

        skill_path = Path(self.manifest["skill"]["path"])
        relative_skill = skill_path.relative_to(Path("hermes") / "skills")
        target_skill = target / relative_skill
        version_cfg = self.manifest["skill_versions"][version]

        if version_cfg["source"] == "git":
            ref = version_cfg["ref"]
            content = self._run(
                ["git", "show", f"{ref}:{skill_path.as_posix()}"],
                cwd=self.repo_root,
            ).stdout
            target_skill.write_text(content, encoding="utf-8")
            source_identity = ref
        elif version_cfg["source"] == "working_tree":
            shutil.copy2(self.repo_root / skill_path, target_skill)
            source_identity = self._git(self.repo_root, "rev-parse", "HEAD")
        else:
            raise ValueError(f"unsupported skill source: {version_cfg['source']}")

        current_skill = self.repo_root / skill_path
        return (
            target,
            self.sha256(target_skill),
            self.sha256(current_skill),
            source_identity,
        )

    @staticmethod
    def _make_home(home: Path, skill_root: Path) -> None:
        home.mkdir(parents=True, exist_ok=True)
        (home / "skills").symlink_to(skill_root, target_is_directory=True)
        for name in (".env", "auth.json"):
            source = Path.home() / ".hermes" / name
            if source.exists():
                (home / name).symlink_to(source)

    @staticmethod
    def event_summary(stdout: str) -> dict[str, Any]:
        events: list[dict[str, Any]] = []
        for line in stdout.splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and value.get("type"):
                events.append(value)

        result = next(
            (event for event in reversed(events) if event.get("type") == "result"),
            {},
        )
        tool_events = [
            event
            for event in events
            if event.get("type") in {"tool_use", "tool_result"}
        ]
        commands: list[str] = []
        tool_names: list[str] = []
        for event in events:
            if event.get("type") != "tool_use":
                continue
            name = str(event.get("name", ""))
            if name:
                tool_names.append(name)
            if name == "terminal":
                args = event.get("input") or {}
                command = args.get("command") if isinstance(args, dict) else None
                if command:
                    commands.append(str(command))

        return {
            "event_count": len(events),
            "tool_event_count": len(tool_events),
            "tool_calls": commands,
            "tool_names": tool_names,
            "terminal_result": result,
            "verification_commands": commands,
        }

    def prepare(
        self,
        spec: RunSpec,
        run_dir: Path,
        case: dict[str, Any],
    ) -> dict[str, Any]:
        fixture = run_dir / "fixture-repo"
        versions = self.materialize(spec.scenario, fixture)
        actual_fixture_version = self.fixture_version(versions)

        scenario_cfg = self.manifest["scenarios"][spec.scenario]
        prompt = self.root / scenario_cfg["prompt"]
        prompt_sha = self.sha256(prompt)
        if prompt_sha != spec.prompt_version:
            raise RuntimeError(
                f"prompt drift for {spec.scenario}: {prompt_sha} != {spec.prompt_version}"
            )
        (run_dir / "prompt.txt").write_text(
            prompt.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        return {
            "fixture": fixture,
            "versions": versions,
            "prompt": prompt,
            "pre_snapshot": self.snapshot(fixture),
            "actual_fixture_version": actual_fixture_version,
            "prompt_sha256": prompt_sha,
        }

    def execute(
        self,
        spec: RunSpec,
        run_dir: Path,
        prepared: dict[str, Any],
        case: dict[str, Any],
    ) -> dict[str, Any]:
        fixture: Path = prepared["fixture"]
        versions: dict[str, str] = prepared["versions"]
        prompt: Path = prepared["prompt"]
        pre = prepared["pre_snapshot"]

        home = Path(tempfile.mkdtemp(prefix="hermes-home-", dir="/tmp"))
        skill_home = Path(tempfile.mkdtemp(prefix="hermes-skills-", dir="/tmp"))
        try:
            skill_root, skill_sha, candidate_sha, source_identity = self._build_skill_root(
                spec.skill_version,
                skill_home,
            )
            self._make_home(home, skill_root)

            env = os.environ.copy()
            env.update(
                {
                    "HERMES_HOME": str(home),
                    "HOME": str(Path.home()),
                    "TERMINAL_CWD": str(fixture),
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
            )

            execution = self.manifest["execution"]
            toolsets = ",".join(execution["toolsets"])
            command = [
                *self.hermes_command,
                "chat",
                "--query-file",
                str(prompt),
                "--oneshot",
                "--quiet",
                "--format",
                "stream-json",
                "--model",
                spec.model,
                "--provider",
                spec.provider,
                "--toolsets",
                toolsets,
                "--skills",
                self.manifest["skill"]["name"],
                "--max-turns",
                str(execution["max_turns"]),
                "--run-budget",
                str(execution["run_budget"]),
            ]
            if execution.get("yolo"):
                command.append("--yolo")
            if execution.get("source"):
                command.extend(["--source", str(execution["source"])])

            started = datetime.now(timezone.utc)
            started_mono = time.monotonic()
            proc = subprocess.run(
                command,
                cwd=fixture,
                env=env,
                text=True,
                capture_output=True,
            )
            ended = datetime.now(timezone.utc)
            elapsed = time.monotonic() - started_mono

            raw_stream = run_dir / "raw_stream.jsonl"
            raw_stderr = run_dir / "raw_stderr.txt"
            raw_final = run_dir / "raw_final_answer.txt"
            raw_stream.write_text(proc.stdout, encoding="utf-8")
            raw_stderr.write_text(proc.stderr, encoding="utf-8")

            summary = self.event_summary(proc.stdout)
            final_text = str(summary.get("terminal_result", {}).get("text", ""))
            raw_final.write_text(final_text, encoding="utf-8")

            post = self.snapshot(fixture)
            if pre != post:
                (run_dir / "post_mutation.diff").write_text(
                    self._git(fixture, "diff", "--binary"),
                    encoding="utf-8",
                )
                mutation_dir = run_dir / "mutation_files"
                mutation_dir.mkdir()
                for name in post["file_sha256"]:
                    if pre["file_sha256"].get(name) == post["file_sha256"].get(name):
                        continue
                    source = fixture / name
                    if source.is_file():
                        target = mutation_dir / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, target)

            self._run(
                ["git", "reset", "-q", "--hard", versions["base_sha"]],
                cwd=fixture,
                check=False,
            )
            self._run(["git", "clean", "-q", "-fdx"], cwd=fixture, check=False)
            patch = self.root / self.manifest["scenarios"][spec.scenario]["patch"]
            self._run(["git", "apply", str(patch)], cwd=fixture)
            restored = self.snapshot(fixture)

            atif_atof = [
                str(path.relative_to(home))
                for path in home.rglob("*")
                if path.is_file()
                and any(token in path.name.lower() for token in ("atif", "atof"))
            ]
            version_proc = self._run(
                [*self.hermes_command, "--version"],
                env=env,
                check=False,
            )
            repo_head = self._git(self.repo_root, "rev-parse", "HEAD")
            baseline_ref = self.manifest["skill_versions"].get("baseline", {}).get("ref")
            metadata = {
                "scenario": spec.scenario,
                "skill_version": spec.skill_version,
                "skill_sha256": skill_sha,
                "candidate_skill_sha256": candidate_sha,
                "skill_source_identity": source_identity,
                "baseline_commit": baseline_ref,
                "candidate_commit": repo_head,
                "candidate_skill_origin_commit": self.manifest["skill_versions"].get("candidate", {}).get("reference_commit"),
                "fixture_base_sha": versions["base_sha"],
                "fixture_review_commit_sha": versions["review_commit_sha"],
                "hermes_executable": self.hermes_command[0],
                "hermes_command_prefix": self.hermes_command,
                "hermes_version": version_proc.stdout.strip(),
                "model": spec.model,
                "provider": spec.provider,
                "toolsets": execution["toolsets"],
                "command": command,
                "started_at": started.isoformat(),
                "ended_at": ended.isoformat(),
                "elapsed_seconds": elapsed,
                "exit_code": proc.returncode,
                "pre_snapshot": pre,
                "post_snapshot": post,
                "restored_snapshot": restored,
                "raw_trace_format": "hermes-stream-json",
                "atif_atof_files": atif_atof,
                "atif_atof_available": bool(atif_atof),
                "event_summary": summary,
                "mutation_detected": pre != post,
                "prompt_sha256": prepared["prompt_sha256"],
            }
            (run_dir / "metadata.json").write_text(
                json.dumps(metadata, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            return {
                **metadata,
                "execution_status": (
                    "COMPLETED" if proc.returncode == 0 else "RUNTIME_FAILURE"
                ),
                "fixture_before": pre,
                "fixture_after": post,
                "mutation_evidence": pre != post,
                "final_answer": final_text,
                "tool_calls": summary["tool_calls"],
                "tool_names": summary["tool_names"],
                "raw_stream_path": str(raw_stream),
                "raw_stderr_path": str(raw_stderr),
                "raw_final_answer_path": str(raw_final),
                "metadata_path": str(run_dir / "metadata.json"),
            }
        finally:
            shutil.rmtree(home, ignore_errors=True)
            shutil.rmtree(skill_home, ignore_errors=True)

    def evaluate_dimension(
        self,
        dimension: str,
        evidence: dict[str, Any],
        rules: dict[str, Any],
    ) -> str:
        if dimension == "outcome":
            return "UNDEFINED"

        if dimension == "trajectory":
            if not rules:
                return "UNDEFINED"
            if rules.get("forbid_fixture_mutation") and evidence.get("mutation_detected"):
                return "FAIL"
            commands = "\n".join(evidence.get("tool_calls", []))
            for pattern in rules.get("forbidden_command_patterns", []):
                if re.search(pattern, commands, flags=re.IGNORECASE):
                    return "FAIL"
            return "PASS"

        if dimension == "privacy":
            markers = rules.get("forbidden_markers")
            if markers is None:
                return "UNDEFINED"
            text = "\n".join(
                [
                    str(evidence.get("final_answer", "")),
                    self._read_optional_text(evidence.get("raw_stderr_path")),
                ]
            )
            return "FAIL" if any(marker in text for marker in markers) else "PASS"

        return "UNDEFINED"

    @staticmethod
    def _read_optional_text(path: Any) -> str:
        if not path:
            return ""
        candidate = Path(str(path))
        return candidate.read_text(encoding="utf-8") if candidate.is_file() else ""
