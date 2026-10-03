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
        if "output" not in value and isinstance(value.get("content"), str):
            return {**value, "output": value["content"]}
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {"output": value}
        if isinstance(decoded, dict):
            if "output" not in decoded and isinstance(decoded.get("content"), str):
                return {**decoded, "output": decoded["content"]}
            return decoded
        return {"output": value}
    return {}


def _skill_id_from_path(path: str) -> str | None:
    normalized = str(path).replace("\\", "/")
    match = re.search(r"(?:^|/)skills/(.+?)/SKILL\.md$", normalized, re.IGNORECASE)
    return match.group(1) if match else None


def _terminal_skill_reads(command: str) -> list[str]:
    read_command = re.compile(
        r"(?:^|[;&|]\s*)(?:cat|head|tail|less|more|sed|grep)\b([^;&|]*)",
        re.IGNORECASE,
    )
    skill_path = re.compile(
        r"['\"]?((?:[^'\"\s;&|]+/)?skills/(?:[^'\"\s;&|]+/)+SKILL\.md)['\"]?",
        re.IGNORECASE,
    )
    found: list[str] = []
    for command_match in read_command.finditer(command):
        for path_match in skill_path.finditer(command_match.group(1)):
            skill = _skill_id_from_path(path_match.group(1))
            if skill and skill not in found:
                found.append(skill)
    return found


def _tool_result_has_content(result: dict[str, Any]) -> bool:
    return (
        result.get("success") is not False
        and not result.get("error")
        and bool(str(result.get("output", "")))
    )


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


def _contract_covers_probe(fixture: Path, probe: dict[str, Any]) -> bool:
    outputs = {
        str(probe.get("stdout", "")),
        json.dumps(str(probe.get("stdout", "")), ensure_ascii=False)[1:-1],
        str(probe.get("stdout", "")).rstrip("\n"),
    }
    outputs.discard("")
    for path in fixture.rglob("*"):
        if not path.is_file() or not _is_verification_file(str(path.relative_to(fixture))):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        signals_present = all(
            re.search(
                rf"(?<![A-Za-z0-9_.]){re.escape(str(signal))}(?![A-Za-z0-9_.])",
                text,
            )
            for signal in probe.get("input_signals", [])
        )
        if signals_present and any(output in text for output in outputs):
            return True
    return False


def _review_finding_supported(answer: str, review_evidence: list[dict[str, Any]]) -> bool:
    text = answer.lower()
    mentions_subject = bool(re.search(r"shipping|delivery|доставк", text))
    mentions_boundary = bool(re.search(r"\b100(?:\.00)?\b", text))
    mentions_expected = bool(re.search(r"free|no\s+charge|zero|бесплатн|без\s+оплаты|\$?0(?:\.00)?", text))
    mentions_actual = bool(re.search(r"\$?10(?:\.00)?", text))
    inspected = "\n".join(
        str(item.get("output", "")) for item in review_evidence
        if item.get("kind") == "change_inspected"
    ).lower()
    checked = "\n".join(
        str(item.get("command", "")) + "\n" + str(item.get("output", ""))
        for item in review_evidence if item.get("kind") == "check_observed"
    ).lower()
    documented_rule = "100" in inspected and bool(re.search(r"free|бесплатн", inspected))
    observed_bug = "100" in checked and "10" in checked
    return all((mentions_subject, mentions_boundary, mentions_expected, mentions_actual, documented_rule, observed_bug))


def _review_trace(
    events: list[dict[str, Any]], fixture: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pending: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    evidence: list[dict[str, Any]] = []
    mutations: list[dict[str, Any]] = []
    unsafe = re.compile(
        r"\bgit\s+(?:add|commit|push|merge|checkout|switch|reset|clean|apply)\b|"
        r"\bgh\s+pr\s+(?:create|merge)\b|\brm\s+-|\b(?:mv|tee)\s+",
        re.IGNORECASE,
    )
    for event in events:
        kind = event.get("type")
        name = str(event.get("name", ""))
        if kind == "tool_use":
            args = event.get("input") or {}
            pending[name].append({"args": args if isinstance(args, dict) else {}})
            command = str(args.get("command", "")) if isinstance(args, dict) else ""
            if name == "terminal" and unsafe.search(command):
                mutations.append({"command": command})
            continue
        if kind != "tool_result" or not pending[name]:
            continue
        call = pending[name].popleft()
        args = call["args"]
        result = _decode_tool_output(event.get("output"))
        output = str(result.get("output", ""))
        command = str(args.get("command", "")) if name == "terminal" else ""
        inspected = name in {"read_file", "file_read"} or bool(re.search(
            r"\bgit\s+(?:diff|show|status)\b|\b(?:cat|sed|less)\s+",
            command,
            re.IGNORECASE,
        ))
        check = name == "terminal" and bool(re.search(
            r"pytest|unittest|\btest\b|python(?:3)?|ruff|mypy",
            command,
            re.IGNORECASE,
        ))
        if output:
            if inspected:
                evidence.append({
                    "kind": "change_inspected",
                    "tool": name,
                    "command": command,
                    "output": output,
                    "exit_code": result.get("exit_code"),
                })
            if check:
                evidence.append({
                    "kind": "check_observed",
                    "tool": name,
                    "command": command,
                    "output": output,
                    "exit_code": result.get("exit_code"),
                })
        if name in {"patch", "write_file", "edit_file"}:
            paths = result.get("files_modified", []) if name == "patch" else [args.get("path", "")]
            for raw_path in paths:
                if not raw_path:
                    continue
                path = Path(str(raw_path))
                if not path.is_absolute():
                    path = fixture / path
                mutations.append({"path": str(path.resolve()), "verification_file": _is_verification_file(str(raw_path))})
    return evidence, mutations


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
        elif name in {"read_file", "file_read"}:
            record["read_only_file_read"] = True
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
            continue
        first_change = min(
            [rec["index"] for rec in verification_changes]
            + [rec["index"] for rec in records if any(
                not change["verification_file"] for change in rec.get("file_changes", [])
            )],
            default=None,
        )
        covered = _contract_covers_probe(fixture, probe)
        pre_change_pass = next((rec for rec in records if rec.get("check_result") == "passed"
                                and (first_change is None or rec["index"] < first_change)), None)
        if covered and pre_change_pass:
            facts.append({"kind": "current_behavior_observed", "index": pre_change_pass["index"],
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
            if rec["check_result"] == "failed":
                facts.append({"kind": "verification_failed", "index": rec["index"]})
        if any(change["verification_file"] for change in rec.get("file_changes", [])):
            facts.append({"kind": "verification_changed", "index": rec["index"]})
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
            continue
        if _contract_covers_probe(fixture, probe):
            post_change_pass = next((rec for rec in records if rec.get("check_result") == "passed"
                                     and first_source_change is not None
                                     and rec["index"] > first_source_change), None)
            if post_change_pass:
                facts.append({"kind": "preserved_behavior_observed", "index": post_change_pass["index"],
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


def fixture_fingerprint_payload(cfg: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "fixture_files": cfg["fixture_files"],
        "equivalent_implementation_files": cfg.get("equivalent_implementation_files", {}),
    }
    for key in ("base_fixture_files", "preexisting_changes"):
        if key in cfg:
            payload[key] = cfg[key]
    return payload


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
        base_files = cfg.get("base_fixture_files", cfg["fixture_files"])
        for relative, content in base_files.items():
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
        for relative, content in cfg.get("preexisting_changes", {}).items():
            path = destination / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
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
        stdout: str | list[dict[str, Any]],
        cfg: dict[str, Any] | None = None,
        fixture: Path | None = None,
    ) -> dict[str, Any]:
        if isinstance(stdout, str):
            events: list[dict[str, Any]] = []
            for line in stdout.splitlines():
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict) and value.get("type"):
                    events.append(value)
        else:
            events = [event for event in stdout if isinstance(event, dict) and event.get("type")]

        result = next(
            (event for event in reversed(events) if event.get("type") == "result"),
            {},
        )
        commands: list[str] = []
        tool_names: list[str] = []
        skill_views: list[Any] = []
        skill_reads: list[dict[str, Any]] = []
        pending: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
        for event_index, event in enumerate(events):
            name = str(event.get("name", ""))
            if event.get("type") == "tool_use":
                raw_args = event.get("input") or {}
                args = raw_args if isinstance(raw_args, dict) else {}
                pending[name].append(args)
                if name:
                    tool_names.append(name)
                if name == "terminal" and args.get("command"):
                    command = str(args["command"])
                    commands.append(command)
                if name == "skill_view":
                    skill_views.append(raw_args)
                continue

            if event.get("type") != "tool_result" or not pending[name]:
                continue
            args = pending[name].popleft()
            tool_result = _decode_tool_output(event.get("output"))
            if name == "skill_view" and _tool_result_has_content(tool_result):
                skill = str(args.get("name", "")).strip()
                if skill:
                    skill_reads.append({"skill": skill, "via": "skill_view", "index": event_index})
            elif name in {"read_file", "file_read"} and _tool_result_has_content(tool_result):
                skill = _skill_id_from_path(str(args.get("path", "")))
                if skill:
                    skill_reads.append({"skill": skill, "via": name, "index": event_index})
            elif name == "terminal" and tool_result.get("exit_code") == 0:
                if _tool_result_has_content(tool_result):
                    skill_reads.extend(
                        {"skill": skill, "via": "terminal", "index": event_index}
                        for skill in _terminal_skill_reads(str(args.get("command", "")))
                    )

        workflow_facts = _workflow_events(events, cfg or {}, fixture) if fixture else []
        if cfg and cfg.get("review_only") and fixture:
            review_evidence, mutation_events = _review_trace(events, fixture)
        else:
            review_evidence, mutation_events = [], []
        return {
            "event_count": len(events),
            "tool_calls": commands,
            "tool_names": tool_names,
            "skill_views": skill_views,
            "skill_reads": skill_reads,
            "terminal_result": result,
            "workflow_events": workflow_facts,
            "review_evidence": review_evidence,
            "mutation_events": mutation_events,
        }

    @staticmethod
    def _session_events(session: dict[str, Any] | None) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        if not session:
            return events
        names_by_call_id: dict[str, str] = {}
        for message in session.get("messages", []):
            role = message.get("role")
            if role == "assistant":
                calls = message.get("tool_calls") or []
                for call in calls:
                    function = call.get("function") or {}
                    name = str(function.get("name") or call.get("name") or "")
                    raw_args = function.get("arguments", call.get("input", {}))
                    if isinstance(raw_args, str):
                        try:
                            raw_args = json.loads(raw_args)
                        except json.JSONDecodeError:
                            raw_args = {}
                    args = raw_args if isinstance(raw_args, dict) else {}
                    call_id = str(call.get("id") or "")
                    if call_id:
                        names_by_call_id[call_id] = name
                    events.append({"type": "tool_use", "name": name, "input": args})
                if not calls and message.get("content") is not None:
                    events.append({"type": "result", "text": message.get("content")})
            elif role == "tool":
                name = str(message.get("tool_name") or message.get("name") or "")
                name = name or names_by_call_id.get(str(message.get("tool_call_id") or ""), "")
                events.append({
                    "type": "tool_result",
                    "name": name,
                    "output": message.get("content"),
                })
        return events

    @staticmethod
    def _session_completed(session: dict[str, Any] | None, prompt_text: str) -> bool:
        if not session:
            return False
        messages = session.get("messages") or []
        last_user = next((message for message in reversed(messages) if message.get("role") == "user"), None)
        last = next((message for message in reversed(messages) if message.get("role") != "system"), None)
        return bool(
            last_user
            and last_user.get("content") == prompt_text
            and last
            and last.get("role") == "assistant"
            and not last.get("tool_calls")
        )

    @staticmethod
    def _session_for_prompt(db, prompt_text: str) -> dict[str, Any] | None:
        for row in db.search_sessions(source="eval", limit=50):
            session_id = str(row.get("id") or "")
            if not session_id:
                continue
            session = db.export_session_lineage(session_id) or db.export_session(session_id)
            if session and any(
                message.get("role") == "user" and message.get("content") == prompt_text
                for message in session.get("messages", [])
            ):
                return session
        return None

    @staticmethod
    def _run_ordinary_interactive(
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: float,
        prompt_text: str,
    ) -> dict[str, Any]:
        if os.name != "posix":
            raise RuntimeError("ordinary interactive capture requires a POSIX pseudo-terminal")
        import select
        import signal

        from hermes_state import SessionDB
        from ptyprocess import PtyProcess

        process = None
        session_db = None
        session_export = None
        session_id = None
        session_capture_error = None
        orphan_process_group_found = False
        terminal_output = bytearray()
        timed_out = False
        shutdown_failed = False
        completion_observed = False
        completion_status = "turn_incomplete"
        stable_signature = None
        stable_reads = 0
        deadline = time.monotonic() + timeout_seconds
        shutdown_deadline = None

        try:
            process = PtyProcess.spawn(
                command, cwd=str(cwd), env=dict(env), echo=False, dimensions=(40, 120)
            )
            db_path = Path(env["HERMES_HOME"]) / "state.db"

            def observe_session():
                nonlocal session_db
                if session_db is None:
                    if not db_path.is_file():
                        return None, None
                    session_db = SessionDB(db_path=db_path, read_only=True)
                found = DevelopmentWorkflowConsumer._session_for_prompt(session_db, prompt_text)
                if not found:
                    return None, None
                ids = found.get("lineage_session_ids") or [found.get("id")]
                return found, str(ids[0] or "") or None

            def drain_output(wait: float) -> None:
                if process.flag_eof:
                    if wait:
                        time.sleep(wait)
                    return
                if not select.select([process.fd], [], [], wait)[0]:
                    return
                try:
                    terminal_output.extend(process.read(65536))
                except EOFError:
                    pass

            while process.isalive():
                now = time.monotonic()
                if not completion_observed and now >= deadline:
                    try:
                        current_session, current_id = observe_session()
                        session_capture_error = None
                        if current_session:
                            session_export, session_id = current_session, current_id
                        if DevelopmentWorkflowConsumer._session_completed(current_session, prompt_text):
                            completion_observed = True
                            completion_status = "turn_completed"
                            shutdown_deadline = time.monotonic() + 5.0
                            try:
                                process.write(b"\x04")
                            except OSError:
                                pass
                            continue
                    except Exception as exc:
                        session_capture_error = f"{type(exc).__name__}: {exc}"
                    timed_out = True
                    completion_status = "eval_timeout_before_turn_completion"
                    break
                if completion_observed and shutdown_deadline is not None and now >= shutdown_deadline:
                    shutdown_failed = True
                    completion_status = "turn_completed_but_cli_did_not_exit"
                    break

                drain_output(0.1)
                if not completion_observed:
                    try:
                        current_session, current_id = observe_session()
                        session_capture_error = None
                    except Exception as exc:
                        session_capture_error = f"{type(exc).__name__}: {exc}"
                        current_session, current_id = None, None
                    if current_session:
                        session_export, session_id = current_session, current_id
                        if DevelopmentWorkflowConsumer._session_completed(current_session, prompt_text):
                            messages = current_session.get("messages") or []
                            signature = canonical_sha256({"count": len(messages), "last": messages[-1]})
                            stable_reads = stable_reads + 1 if signature == stable_signature else 1
                            stable_signature = signature
                            if stable_reads >= 3:
                                completion_observed = True
                                completion_status = "turn_completed"
                                shutdown_deadline = time.monotonic() + 5.0
                                try:
                                    process.write(b"\x04")
                                except OSError:
                                    pass
                        else:
                            stable_signature, stable_reads = None, 0

            if not completion_observed:
                try:
                    current_session, current_id = observe_session()
                    if current_session:
                        session_export, session_id = current_session, current_id
                except Exception as exc:
                    session_capture_error = f"{type(exc).__name__}: {exc}"

            if process.isalive():
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                grace = time.monotonic() + 0.25
                while process.isalive() and time.monotonic() < grace:
                    drain_output(0.02)
                if process.isalive():
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    while process.isalive():
                        time.sleep(0.01)

            while not process.flag_eof and select.select([process.fd], [], [], 0)[0]:
                drain_output(0)
            try:
                os.killpg(process.pid, 0)
                orphan_process_group_found = True
                os.killpg(process.pid, signal.SIGTERM)
                time.sleep(0.25)
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            except ProcessLookupError:
                orphan_process_group_found = False
            try:
                current_session, current_id = observe_session()
                session_capture_error = None
                if current_session:
                    session_export, session_id = current_session, current_id
                    if not timed_out and DevelopmentWorkflowConsumer._session_completed(current_session, prompt_text):
                        completion_observed = True
                        if not shutdown_failed:
                            completion_status = "turn_completed"
            except Exception as exc:
                session_capture_error = f"{type(exc).__name__}: {exc}"

            return_code = process.exitstatus if process.exitstatus is not None else -(process.signalstatus or signal.SIGKILL)
            if completion_observed and return_code != 0 and not shutdown_failed:
                completion_status = "turn_completed_but_cli_failed"
            process.close(force=False)
        finally:
            if process is not None:
                if process.isalive():
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    while process.isalive():
                        time.sleep(0.01)
                if not process.closed:
                    process.close(force=False)
            if session_db is not None:
                session_db.close()

        completed = subprocess.CompletedProcess(
            command,
            return_code,
            terminal_output.decode("utf-8", errors="replace"),
            "",
        )
        return {
            "process": completed,
            "timed_out": timed_out,
            "shutdown_failed": shutdown_failed,
            "completion_observed": completion_observed,
            "completion_status": completion_status,
            "session_id": session_id,
            "session": session_export,
            "session_capture_error": session_capture_error,
            "orphan_process_group_found": orphan_process_group_found,
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

        fixture_version = canonical_sha256(fixture_fingerprint_payload(cfg))
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
            mode = spec.mode.split(":", 1)[0]
            command = [
                *self.hermes_command,
                "chat",
                "--query-file",
                str(prompt),
            ]
            if mode == "natural-routing":
                command.extend([
                    "--cli",
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
                ])
            else:
                command.extend([
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
                ])
            if mode == "skill-behavior" and execution["skill_behavior"].get("force_owner_skill"):
                command.extend([
                    "--skills",
                    str(cfg.get("owner_skill", execution["skill_behavior"]["owner_skill"])),
                ])
            if execution.get("yolo"):
                command.append("--yolo")
            if execution.get("source"):
                command.extend(["--source", str(execution["source"])])

            started = datetime.now(timezone.utc)
            started_mono = time.monotonic()
            normal_capture = None
            if mode == "natural-routing":
                normal_capture = self._run_ordinary_interactive(
                    command,
                    cwd=fixture,
                    env=env,
                    timeout_seconds=float(execution["eval_timeout_seconds"]),
                    prompt_text=prompt.read_text(encoding="utf-8"),
                )
                proc = normal_capture["process"]
                timed_out = normal_capture["timed_out"]
                events = self._session_events(normal_capture["session"])
                summary = self.event_summary(events, cfg, fixture)
                completion_observed = normal_capture["completion_observed"]
                completion_status = normal_capture["completion_status"]
                raw_session = run_dir / "raw_session.json"
                if normal_capture["session"] is not None:
                    raw_session.write_text(
                        json.dumps(normal_capture["session"], indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                raw_terminal = run_dir / "raw_terminal_output.txt"
                raw_terminal.write_text(proc.stdout, encoding="utf-8")
                raw_stream = raw_stderr = None
                if timed_out or normal_capture["shutdown_failed"]:
                    execution_status = "RUNTIME_FAILURE"
                elif completion_observed and proc.returncode == 0:
                    execution_status = "COMPLETED"
                else:
                    execution_status = "AGENT_FAILURE"
            else:
                proc, timed_out = run_with_timeout(
                    command,
                    cwd=fixture,
                    env=env,
                    timeout_seconds=float(execution["eval_timeout_seconds"]),
                )
                summary = self.event_summary(proc.stdout, cfg, fixture)
                completion_observed = bool(summary["terminal_result"])
                completion_status = "result_observed" if completion_observed else "process_exited_without_result"
                raw_stream = run_dir / "raw_stream.jsonl"
                raw_stderr = run_dir / "raw_stderr.txt"
                raw_stream.write_text(proc.stdout, encoding="utf-8")
                raw_stderr.write_text(proc.stderr, encoding="utf-8")
                raw_session = raw_terminal = None
                if timed_out:
                    execution_status = "RUNTIME_FAILURE"
                elif proc.returncode == 0:
                    execution_status = "COMPLETED"
                else:
                    execution_status = "AGENT_FAILURE"

            ended = datetime.now(timezone.utc)
            elapsed = time.monotonic() - started_mono
            final_text = str(summary.get("terminal_result", {}).get("text", ""))
            raw_final = run_dir / "raw_final_answer.txt"
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
                "evaluation_mode": mode,
                "forced_owner_skill": (
                    str(cfg.get("owner_skill", execution["skill_behavior"]["owner_skill"]))
                    if mode == "skill-behavior"
                    and execution["skill_behavior"].get("force_owner_skill")
                    else None
                ),
                "skill_version": spec.skill_version,
                "skill_sources": source_identities,
                "fixture_baseline_head": prepared["baseline_head"],
                "fixture_sha256": prepared["actual_fixture_version"],
                "model": spec.model,
                "provider": spec.provider,
                "command": command,
                "execution_policy": "ordinary-interactive" if mode == "natural-routing" else "one-shot",
                "completion_observed": completion_observed,
                "completion_status": completion_status,
                "session_id": normal_capture["session_id"] if normal_capture else None,
                "session_capture_error": normal_capture["session_capture_error"] if normal_capture else None,
                "orphan_process_group_found": normal_capture["orphan_process_group_found"] if normal_capture else None,
                "raw_session_path": str(raw_session) if raw_session and raw_session.is_file() else None,
                "raw_terminal_output_path": str(raw_terminal) if raw_terminal else None,
                "raw_stream_path": str(raw_stream) if raw_stream else None,
                "raw_stderr_path": str(raw_stderr) if raw_stderr else None,
                "prompt_path": str(prompt),
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
                "skill_reads": summary["skill_reads"],
                "review_evidence": summary.get("review_evidence", []),
                "mutation_events": summary.get("mutation_events", []),
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
                "skill_reads": summary["skill_reads"],
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
            if rules.get("review_only"):
                failures: list[str] = []
                if evidence.get("execution_status") != "COMPLETED":
                    failures.append("review execution did not complete")
                review_evidence = evidence.get("review_evidence", [])
                if not _review_finding_supported(
                    str(evidence.get("final_answer", "")), review_evidence
                ):
                    failures.append("fixture review finding was not reported with supporting evidence")
                if not any(item.get("kind") == "check_observed" for item in review_evidence):
                    failures.append("no read-only verification evidence was observed")
                return {
                    "status": "FAIL" if failures else "PASS",
                    "reason": "; ".join(failures) if failures else None,
                }
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
            if rules.get("review_only"):
                pre = evidence.get("pre_snapshot") or {}
                post = evidence.get("post_snapshot") or {}
                review_evidence = evidence.get("review_evidence", [])
                reasons = []
                unsafe_patterns = (
                    r"\bgit\s+(?:add|commit|push|merge|checkout|switch|reset|clean|apply)\b",
                    r"\bgh\s+pr\s+(?:create|merge)\b",
                    r"\brm\s+-|\b(?:mv|tee)\s+",
                )
                if any(
                    re.search(pattern, str(command), re.IGNORECASE)
                    for pattern in unsafe_patterns
                    for command in evidence.get("tool_calls", [])
                ):
                    reasons.append("delivery or destructive action was observed")
                if pre != post or evidence.get("repository_changed"):
                    reasons.append("checkout state mutated during review")
                if evidence.get("mutation_events"):
                    reasons.append("implementation, test, or other mutation action was observed")
                if not any(item.get("kind") == "change_inspected" for item in review_evidence):
                    reasons.append("existing change inspection is UNCONFIRMED")
                if not any(
                    item.get("kind") == "check_observed"
                    and item.get("exit_code") == 0
                    and item.get("output")
                    for item in review_evidence
                ):
                    reasons.append("read-only evidence check is UNCONFIRMED")
                changed_protected = sorted(
                    path for path, unchanged in (evidence.get("protected_paths_unchanged") or {}).items()
                    if not unchanged
                )
                if changed_protected:
                    reasons.append("unrelated user content changed: " + ", ".join(changed_protected))
                return {"status": "FAIL" if reasons else "PASS", "reason": "; ".join(reasons) if reasons else None}
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
            if rules.get("mechanical"):
                if not current or (first_production is not None and min(current) >= first_production):
                    reasons.append("current observable behavior is UNCONFIRMED before mechanical change")
                if first_production is None:
                    reasons.append("mechanical production change is UNCONFIRMED")
                if positions.get("verification_changed"):
                    reasons.append("unnecessary regression/executable specification change")
                if positions.get("verification_failed"):
                    reasons.append("artificial RED or failing verification was observed")
                post_change_pass = [index for index in passed
                                    if first_production is not None and index > first_production]
                if not post_change_pass:
                    reasons.append("proportionate verification after mechanical change is UNCONFIRMED")
                required_preserved = int(rules.get("preserved_probe_count", 0))
                after_change = [event for event in preserved if first_production is not None
                                and int(event.get("index", -1)) > first_production]
                observed_ids = {event.get("probe_index") for event in after_change}
                preserved_count = len(observed_ids) if None not in observed_ids else len(after_change)
                if preserved_count < required_preserved:
                    reasons.append("observable behavior was not preserved after mechanical change")
                return {"status": "FAIL" if reasons else "PASS",
                        "reason": "; ".join(reasons) if reasons else None}
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

    @staticmethod
    def routing_diagnostics(evidence: dict[str, Any]) -> dict[str, Any]:
        """Record observed skill routing without turning it into an acceptance verdict."""
        reads = [
            dict(item)
            for item in evidence.get("skill_reads", [])
            if isinstance(item, dict)
        ]
        workflow_events = evidence.get("workflow_events")
        if workflow_events is None:
            workflow_events = (evidence.get("event_summary") or {}).get("workflow_events", [])
        first_production = min(
            (int(item["index"]) for item in workflow_events
             if item.get("kind") == "production_changed" and item.get("index") is not None),
            default=None,
        )
        before_production = []
        if first_production is not None:
            before_production = [
                item for item in reads
                if item.get("index") is not None and int(item["index"]) < first_production
            ]
        return {
            "first_production_index": first_production,
            "skill_reads": reads,
            "skill_reads_before_production": before_production,
        }
