from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evals.harness.core import RunSpec
from evals.harness.process import run_with_timeout
from evals.harness.skill_source import materialize_skill_source


def _decode_tool_output(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {"output": value}
        return decoded if isinstance(decoded, dict) else {"output": value}
    return {}


def _is_verification_file(path: str) -> bool:
    parts = [part.lower() for part in Path(path).parts]
    name = parts[-1] if parts else ""
    return (
        any(part in {"test", "tests", "spec", "specs", "checks", "contracts", "features"} for part in parts)
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith(".feature")
    )


def _is_test_result(command: str, output: str) -> tuple[bool, bool]:
    text = f"{command}\n{output}"
    failure = bool(re.search(
        r"(?:\bFAILED\b|\bFAILURES\b|\bAssertionError\b|\bassertion failed\b|"
        r"\b[1-9][0-9]* failed\b|\bnot ok\b)", text, re.IGNORECASE
    ))
    success = bool(re.search(
        r"(?:\b[0-9]+ passed\b|\btests? passed\b|\bOK\b|\bPASS\b|"
        r"\ball tests passed\b|\btests? successful\b)", text, re.IGNORECASE
    ))
    recognized = failure or success or bool(re.search(
        r"\b(?:pytest|unittest|vitest|jest|phpunit|cargo test|go test)\b", command,
        re.IGNORECASE
    ))
    return recognized, failure


def _workflow_events(events: list[dict[str, Any]], cfg: dict[str, Any], fixture: Path) -> list[dict[str, Any]]:
    pending: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    records: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        kind = event.get("type")
        name = str(event.get("name", ""))
        if kind == "tool_use":
            pending[name].append({"index": index, "input": event.get("input") or {}})
            continue
        if kind != "tool_result" or not pending[name]:
            continue
        call = pending[name].popleft()
        args = call["input"] if isinstance(call["input"], dict) else {}
        result = _decode_tool_output(event.get("output"))
        output = str(result.get("output", ""))
        command = str(args.get("command", "")) if name == "terminal" else ""
        record = {"index": call["index"], "tool": name, "output": output, "command": command}
        if name == "terminal":
            record["exit_code"] = result.get("exit_code")
            recognized, failed = _is_test_result(command, output)
            if recognized:
                record["check_result"] = "failed" if failed or result.get("exit_code", 0) else "passed"
        paths: list[str] = []
        changed_text = ""
        if name == "patch":
            paths = [str(path) for path in result.get("files_modified", [])]
            changed_text = str(args.get("patch", "")) + "\n" + output
        elif name == "write_file":
            path = args.get("path")
            if path:
                paths = [str(path)]
            changed_text = str(args.get("content", ""))
        elif name == "edit_file":
            path = args.get("path")
            if path:
                paths = [str(path)]
            changed_text = json.dumps(args, ensure_ascii=False)
        for path in paths:
            try:
                resolved = Path(path).resolve()
                resolved.relative_to(fixture.resolve())
            except (OSError, ValueError):
                continue
            record.setdefault("file_changes", []).append({
                "path": str(resolved),
                "verification_file": _is_verification_file(path),
                "text": changed_text,
            })
        records.append(record)

    facts: list[dict[str, Any]] = []
    verification_changes = [
        rec for rec in records
        if any(change["verification_file"] for change in rec.get("file_changes", []))
    ]
    for probe_index, probe in enumerate(cfg.get("current_behavior_probes", [])):
        matched = next((rec for rec in records if rec["tool"] == "terminal"
                        and rec.get("exit_code") == probe.get("exit_code")
                        and rec["output"] == probe.get("stdout")
                        and all(str(signal) in rec["command"]
                                for signal in probe.get("input_signals", []))), None)
        if matched:
            facts.append({"kind": "current_behavior_observed", "index": matched["index"],
                          "probe_index": probe_index})
    signals = [str(item) for item in cfg.get("target_check_signals", [])]
    matching_check_change = next((rec for rec in verification_changes
                                  if any(all(signal in change.get("text", "") for signal in signals)
                                         for change in rec.get("file_changes", []))), None)
    if matching_check_change:
        facts.append({"kind": "target_check_changed", "index": matching_check_change["index"]})
    for rec in records:
        if rec.get("check_result"):
            facts.append({"kind": "target_check_" + rec["check_result"], "index": rec["index"], "output": rec["output"]})
        if any(not change["verification_file"] for change in rec.get("file_changes", [])):
            facts.append({"kind": "production_changed", "index": rec["index"]})
    source_change_indices = [rec["index"] for rec in records
                             if any(not change["verification_file"]
                                    for change in rec.get("file_changes", []))]
    first_source_change = min(source_change_indices) if source_change_indices else None
    for probe_index, probe in enumerate(cfg.get("preserved_behavior_probes", [])):
        matched = next((rec for rec in records if rec["tool"] == "terminal"
                        and rec.get("exit_code") == probe.get("exit_code")
                        and rec["output"] == probe.get("stdout")
                        and all(str(signal) in rec["command"]
                                for signal in probe.get("input_signals", []))
                        and first_source_change is not None
                        and rec["index"] > first_source_change), None)
        if matched:
            facts.append({"kind": "preserved_behavior_observed", "index": matched["index"],
                          "probe_index": probe_index})
    return facts


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class DevelopmentWorkflowConsumer:
    name = "development-workflow"

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

    def materialize_fixture(self, cfg: dict[str, Any], destination: Path) -> str:
        destination.mkdir(parents=True)
        for relative, content in cfg["fixture_files"].items():
            path = destination / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        self._run(["git", "init", "-q"], cwd=destination)
        self._run(["git", "config", "user.name", "Hermes BDD Eval"], cwd=destination)
        self._run(
            ["git", "config", "user.email", "bdd-eval@example.invalid"],
            cwd=destination,
        )
        self._run(["git", "add", "."], cwd=destination)
        env = {
            **os.environ,
            "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z",
            "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
        }
        self._run(
            ["git", "commit", "-q", "-m", "fixture baseline"],
            cwd=destination,
            env=env,
        )
        return self._git(destination, "rev-parse", "HEAD")

    def snapshot(self, repo: Path) -> dict[str, Any]:
        tracked = set(self._git(repo, "ls-files").splitlines())
        untracked = set(
            self._git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
        )
        files: dict[str, str] = {}
        for name in sorted(tracked | untracked):
            if not name:
                continue
            path = repo / name
            if path.is_file():
                files[name] = self.sha256(path)
        return {
            "head": self._git(repo, "rev-parse", "HEAD"),
            "status_porcelain": self._git(repo, "status", "--porcelain=v1"),
            "file_sha256": files,
        }

    def _build_skill_root(
        self,
        version: str,
        root: Path,
    ) -> tuple[Path, list[dict[str, Any]]]:
        target = root / "skills"
        shutil.copytree(self.repo_root / "hermes" / "skills", target, symlinks=False)

        source_cfg = self.manifest["skill_versions"][version]
        identities: list[dict[str, Any]] = []
        prefix = Path("hermes") / "skills"

        for raw_path in self.manifest["skill_paths"]:
            repo_path = Path(raw_path)
            destination = target / repo_path.relative_to(prefix)
            if destination.exists() or destination.is_symlink():
                if destination.is_dir() and not destination.is_symlink():
                    shutil.rmtree(destination)
                else:
                    destination.unlink()

            identities.append(
                materialize_skill_source(
                    self.repo_root,
                    repo_path,
                    source_cfg,
                    destination,
                )
            )

        return target, identities

    @staticmethod
    def _make_home(home: Path, skill_root: Path) -> None:
        home.mkdir(parents=True, exist_ok=True)
        (home / "skills").symlink_to(skill_root, target_is_directory=True)
        source_home = Path.home() / ".hermes"
        for name in (".env", "auth.json", "config.yaml"):
            source = source_home / name
            if source.exists():
                (home / name).symlink_to(source)

    @staticmethod
    def event_summary(
        stdout: str,
        cfg: dict[str, Any] | None = None,
        fixture: Path | None = None,
    ) -> dict[str, Any]:
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
        commands: list[str] = []
        tool_names: list[str] = []
        skill_views: list[Any] = []
        for event in events:
            if event.get("type") != "tool_use":
                continue
            name = str(event.get("name", ""))
            if name:
                tool_names.append(name)
            args = event.get("input") or {}
            if name == "terminal" and isinstance(args, dict) and args.get("command"):
                commands.append(str(args["command"]))
            if name == "skill_view":
                skill_views.append(args)

        return {
            "event_count": len(events),
            "tool_calls": commands,
            "tool_names": tool_names,
            "skill_views": skill_views,
            "terminal_result": result,
            "workflow_events": _workflow_events(events, cfg or {}, fixture) if fixture else [],
        }

    @staticmethod
    def _probe(cwd: Path, probe: dict[str, Any]) -> dict[str, Any]:
        proc = subprocess.run(
            list(probe["command"]),
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        return {
            "name": probe["name"],
            "command": probe["command"],
            "expected_exit_code": probe["exit_code"],
            "actual_exit_code": proc.returncode,
            "expected_stdout": probe["stdout"],
            "actual_stdout": proc.stdout,
            "stderr": proc.stderr,
        }

    def _verify_behavior_equivalent_implementation(
        self,
        fixture: Path,
        cfg: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        replacements = cfg.get("equivalent_implementation_files") or {}
        if not replacements:
            return [], {"command": cfg["test_command"], "exit_code": 0, "stdout": "", "stderr": ""}

        with tempfile.TemporaryDirectory(prefix="bdd-equivalent-") as temp:
            candidate = Path(temp) / "fixture"
            shutil.copytree(
                fixture,
                candidate,
                ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"),
            )
            for relative, content in replacements.items():
                path = candidate / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            probes = [
                self._probe(candidate, item)
                for item in cfg["behavior_probes"]
            ]
            proc = subprocess.run(
                list(cfg["test_command"]),
                cwd=candidate,
                text=True,
                capture_output=True,
                check=False,
                timeout=60,
            )
            result = {
                "command": cfg["test_command"],
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
            return probes, result

    def prepare(
        self,
        spec: RunSpec,
        run_dir: Path,
        case: dict[str, Any],
    ) -> dict[str, Any]:
        cfg = self.manifest["scenarios"][spec.scenario]
        scratch = Path(os.environ.get("TMPDIR") or tempfile.gettempdir())
        scratch.mkdir(parents=True, exist_ok=True)
        fixture_parent = Path(tempfile.mkdtemp(prefix="hermes-bdd-fixture-", dir=scratch))
        fixture = fixture_parent / "fixture-repo"
        baseline_head = self.materialize_fixture(cfg, fixture)

        prompt_text = str(cfg["prompt"])
        prompt_sha = canonical_sha256(prompt_text)
        if prompt_sha != spec.prompt_version:
            shutil.rmtree(fixture_parent, ignore_errors=True)
            raise RuntimeError(
                f"prompt drift for {spec.scenario}: {prompt_sha} != {spec.prompt_version}"
            )

        fixture_version = canonical_sha256(
            {
                "fixture_files": cfg["fixture_files"],
                "equivalent_implementation_files": cfg.get(
                    "equivalent_implementation_files", {}
                ),
            }
        )
        if fixture_version != spec.fixture_version:
            shutil.rmtree(fixture_parent, ignore_errors=True)
            raise RuntimeError(
                f"fixture drift for {spec.scenario}: "
                f"{fixture_version} != {spec.fixture_version}"
            )

        prompt_path = run_dir / "prompt.txt"
        prompt_path.write_text(prompt_text, encoding="utf-8")
        return {
            "fixture": fixture,
            "fixture_parent": fixture_parent,
            "baseline_head": baseline_head,
            "prompt": prompt_path,
            "pre_snapshot": self.snapshot(fixture),
            "actual_fixture_version": fixture_version,
            "prompt_sha256": prompt_sha,
        }

    def execute(
        self,
        spec: RunSpec,
        run_dir: Path,
        prepared: dict[str, Any],
        case: dict[str, Any],
    ) -> dict[str, Any]:
        cfg = self.manifest["scenarios"][spec.scenario]
        fixture: Path = prepared["fixture"]
        prompt: Path = prepared["prompt"]
        pre = prepared["pre_snapshot"]

        home = Path(tempfile.mkdtemp(prefix="hermes-bdd-home-", dir="/tmp"))
        skill_home = Path(tempfile.mkdtemp(prefix="hermes-bdd-skills-", dir="/tmp"))
        try:
            skill_root, source_identities = self._build_skill_root(
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
                ",".join(execution["toolsets"]),
                "--max-turns",
                str(execution["max_turns"]),
                "--run-budget",
                str(execution["run_budget"]),
            ]
            mode = spec.mode.split(":", 1)[0]
            if mode == "skill-behavior" and execution["skill_behavior"].get("force_owner_skill"):
                command.extend(["--skills", str(execution["skill_behavior"]["owner_skill"])])
            if execution.get("yolo"):
                command.append("--yolo")
            if execution.get("source"):
                command.extend(["--source", str(execution["source"])])

            started = datetime.now(timezone.utc)
            started_mono = time.monotonic()
            proc, timed_out = run_with_timeout(
                command,
                cwd=fixture,
                env=env,
                timeout_seconds=float(execution["eval_timeout_seconds"]),
            )
            ended = datetime.now(timezone.utc)
            elapsed = time.monotonic() - started_mono

            if timed_out:
                execution_status = "RUNTIME_FAILURE"
            elif proc.returncode == 0:
                execution_status = "COMPLETED"
            else:
                execution_status = "AGENT_FAILURE"

            raw_stream = run_dir / "raw_stream.jsonl"
            raw_stderr = run_dir / "raw_stderr.txt"
            raw_final = run_dir / "raw_final_answer.txt"
            raw_stream.write_text(proc.stdout, encoding="utf-8")
            raw_stderr.write_text(proc.stderr, encoding="utf-8")

            summary = self.event_summary(proc.stdout, cfg, fixture)
            final_text = str(summary.get("terminal_result", {}).get("text", ""))
            raw_final.write_text(final_text, encoding="utf-8")

            probes = [self._probe(fixture, item) for item in cfg["behavior_probes"]]
            test_proc = subprocess.run(
                list(cfg["test_command"]),
                cwd=fixture,
                text=True,
                capture_output=True,
                check=False,
                timeout=60,
            )
            test_result = {
                "command": cfg["test_command"],
                "exit_code": test_proc.returncode,
                "stdout": test_proc.stdout,
                "stderr": test_proc.stderr,
            }

            equivalent_behavior_probes, equivalent_test_result = (
                self._verify_behavior_equivalent_implementation(fixture, cfg)
            )

            post = self.snapshot(fixture)
            repository_changed = (
                pre["status_porcelain"] != post["status_porcelain"]
                or pre["file_sha256"] != post["file_sha256"]
            )
            protected = {
                path: pre["file_sha256"].get(path) == post["file_sha256"].get(path)
                for path in cfg.get("protected_paths", [])
            }

            diff_text = self._git(fixture, "diff", "--binary", check=False)
            (run_dir / "final.diff").write_text(
                diff_text + ("\n" if diff_text else ""),
                encoding="utf-8",
            )

            metadata = {
                "scenario": spec.scenario,
                "skill_version": spec.skill_version,
                "skill_sources": source_identities,
                "model": spec.model,
                "provider": spec.provider,
                "command": command,
                "started_at": started.isoformat(),
                "ended_at": ended.isoformat(),
                "elapsed_seconds": elapsed,
                "exit_code": proc.returncode,
                "execution_status": execution_status,
                "timed_out": timed_out,
                "pre_snapshot": pre,
                "post_snapshot": post,
                "repository_changed": repository_changed,
                "protected_paths_unchanged": protected,
                "behavior_probes": probes,
                "test_result": test_result,
                "equivalent_behavior_probes": equivalent_behavior_probes,
                "equivalent_test_result": equivalent_test_result,
                "event_summary": summary,
                "prompt_sha256": prepared["prompt_sha256"],
            }
            (run_dir / "metadata.json").write_text(
                json.dumps(metadata, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return {
                **metadata,
                "final_answer": final_text,
                "tool_calls": summary["tool_calls"],
                "tool_names": summary["tool_names"],
                "skill_views": summary["skill_views"],
                "raw_stream_path": str(raw_stream),
                "raw_stderr_path": str(raw_stderr),
                "raw_final_answer_path": str(raw_final),
                "metadata_path": str(run_dir / "metadata.json"),
            }
        finally:
            shutil.rmtree(home, ignore_errors=True)
            shutil.rmtree(skill_home, ignore_errors=True)
            shutil.rmtree(prepared.get("fixture_parent", fixture.parent), ignore_errors=True)

    def evaluate_dimension_diagnostic(
        self,
        dimension: str,
        evidence: dict[str, Any],
        rules: dict[str, Any],
    ) -> dict[str, Any]:
        if dimension == "outcome":
            failures: list[str] = []
            if evidence.get("execution_status") != "COMPLETED":
                failures.append(
                    f"agent execution status is {evidence.get('execution_status')}"
                )

            for probe in evidence.get("behavior_probes", []):
                if probe.get("actual_exit_code") != probe.get("expected_exit_code"):
                    failures.append(
                        f"{probe.get('name')}: exit "
                        f"{probe.get('actual_exit_code')} != {probe.get('expected_exit_code')}"
                    )
                if probe.get("actual_stdout") != probe.get("expected_stdout"):
                    failures.append(f"{probe.get('name')}: stdout mismatch")

            test_result = evidence.get("test_result") or {}
            if test_result.get("exit_code") != 0:
                failures.append("project executable verification failed")

            equivalent_fixture_errors: list[str] = []
            for probe in evidence.get("equivalent_behavior_probes", []):
                if probe.get("actual_exit_code") != probe.get("expected_exit_code"):
                    equivalent_fixture_errors.append(
                        f"{probe.get('name')}: exit mismatch"
                    )
                if probe.get("actual_stdout") != probe.get("expected_stdout"):
                    equivalent_fixture_errors.append(
                        f"{probe.get('name')}: stdout mismatch"
                    )
            if equivalent_fixture_errors:
                return {
                    "status": "ERROR",
                    "reason": "behavior-equivalent evaluator fixture is invalid: "
                    + "; ".join(equivalent_fixture_errors),
                }

            equivalent_test_result = evidence.get("equivalent_test_result") or {}
            if equivalent_test_result.get("exit_code") != 0:
                failures.append(
                    "project tests reject a behavior-equivalent implementation"
                )

            protected = evidence.get("protected_paths_unchanged") or {}
            changed_protected = sorted(
                path for path, unchanged in protected.items() if not unchanged
            )
            if changed_protected:
                failures.append(
                    "protected unrelated content changed: "
                    + ", ".join(changed_protected)
                )

            if rules.get("require_repository_change") and not evidence.get(
                "repository_changed"
            ):
                failures.append("requested repository change was not made")

            return {
                "status": "FAIL" if failures else "PASS",
                "reason": "; ".join(failures) if failures else None,
            }

        if dimension == "trajectory":
            commands = "\n".join(
                str(item) for item in evidence.get("tool_calls", [])
            )
            matched = [
                pattern
                for pattern in rules.get("forbidden_command_patterns", [])
                if re.search(pattern, commands, flags=re.IGNORECASE)
            ]
            if matched:
                return {
                    "status": "FAIL",
                    "reason": "forbidden externally meaningful action: "
                    + ", ".join(matched),
                }
            events = evidence.get("workflow_events")
            if events is None:
                events = (evidence.get("event_summary") or {}).get("workflow_events", [])
            events = [
                {**event, "index": int(event.get("index", ordinal))}
                for ordinal, event in enumerate(events or [])
            ]
            positions: dict[str, list[int]] = defaultdict(list)
            for event in events:
                positions[str(event.get("kind", ""))].append(int(event["index"]))
            current = positions.get("current_behavior_observed", [])
            production = positions.get("production_changed", [])
            passed = positions.get("target_check_passed", [])
            preserved = [event for event in events if event.get("kind") == "preserved_behavior_observed"]
            reasons: list[str] = []
            first_production = min(production) if production else None
            required_current = int(rules.get("current_probe_count", 1))
            current_before_change = [event for event in events
                                     if event.get("kind") == "current_behavior_observed"
                                     and (first_production is None or int(event["index"]) < first_production)]
            current_ids = {event.get("probe_index") for event in current_before_change}
            current_count = len(current_ids) if None not in current_ids else len(current_before_change)
            if current_count < required_current:
                reasons.append("current observable behavior is UNCONFIRMED")
            first_production = min(production) if production else None
            if first_production is None:
                reasons.append("production change is UNCONFIRMED")
            if rules.get("requires_red", True):
                changed = positions.get("target_check_changed", [])
                failed = [event for event in events if event.get("kind") == "target_check_failed"]
                red_signal = rules.get("target_failure_signal")
                red = (
                    [event for event in failed if str(red_signal) in str(event.get("output", ""))]
                    if red_signal
                    else failed
                )
                if not changed:
                    reasons.append("executable target check change is UNCONFIRMED")
                if not red:
                    reasons.append("target check RED before production change is UNCONFIRMED")
                elif first_production is not None and not any(
                    changed_index < int(event.get("index", -1)) < first_production
                    for event in red for changed_index in changed
                ):
                    reasons.append("target check RED was not observed between check change and production change")
                elif first_production is not None and min(event.get("index", -1) for event in red) >= first_production:
                    reasons.append("target check RED occurred after production change")
            elif first_production is not None and not any(
                index < first_production for index in passed
            ):
                reasons.append("executable verification GREEN before refactor is UNCONFIRMED")
            if current and first_production is not None and min(current) >= first_production:
                reasons.append("current behavior was not observed before production change")
            if first_production is not None and not any(index > first_production for index in passed):
                reasons.append("executable verification GREEN after production change is UNCONFIRMED")
            required_preserved = int(rules.get("preserved_probe_count", 0))
            after_change = [event for event in preserved if first_production is not None
                            and int(event.get("index", -1)) > first_production]
            observed_ids = {event.get("probe_index") for event in after_change}
            preserved_count = len(observed_ids) if None not in observed_ids else len(after_change)
            if preserved_count < required_preserved:
                reasons.append("required preserved behavior is UNCONFIRMED after production change")
            return {
                "status": "FAIL" if reasons else "PASS",
                "reason": "; ".join(reasons) if reasons else None,
            }

        if dimension == "privacy":
            return {
                "status": "UNDEFINED",
                "reason": "no privacy contract in this fixture",
            }

        return {
            "status": "UNDEFINED",
            "reason": f"unknown dimension: {dimension}",
        }

    def evaluate_dimension(
        self,
        dimension: str,
        evidence: dict[str, Any],
        rules: dict[str, Any],
    ) -> str:
        return str(
            self.evaluate_dimension_diagnostic(
                dimension,
                evidence,
                rules,
            )["status"]
        )
