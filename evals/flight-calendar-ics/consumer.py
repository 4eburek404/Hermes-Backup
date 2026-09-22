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
from evals.harness.skill_source import materialize_skill_source


class FlightCalendarIcsConsumer:
    name = "flight-calendar-ics"

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

    @staticmethod
    def _make_home(home: Path, skill_root: Path) -> None:
        home.mkdir(parents=True, exist_ok=True)
        (home / "skills").symlink_to(skill_root, target_is_directory=True)
        for name in (".env", "auth.json", "config.yaml"):
            source = Path.home() / ".hermes" / name
            if source.exists():
                (home / name).symlink_to(source)

    @staticmethod
    def _event_summary(stdout: str) -> dict[str, Any]:
        events: list[dict[str, Any]] = []
        for line in stdout.splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and value.get("type"):
                events.append(value)

        tool_uses: list[dict[str, Any]] = []
        for index, event in enumerate(events):
            if event.get("type") != "tool_use":
                continue
            tool_uses.append(
                {
                    "index": index,
                    "name": str(event.get("name", "")),
                    "input": event.get("input") if isinstance(event.get("input"), dict) else {},
                }
            )

        result = next(
            (event for event in reversed(events) if event.get("type") == "result"),
            {},
        )
        usage = next(
            (
                event.get("usage")
                for event in reversed(events)
                if isinstance(event.get("usage"), dict)
            ),
            None,
        )
        terminal_commands = [
            str(use["input"].get("command", ""))
            for use in tool_uses
            if use["name"] == "terminal" and use["input"].get("command")
        ]
        return {
            "event_count": len(events),
            "tool_uses": tool_uses,
            "tool_names": [use["name"] for use in tool_uses],
            "terminal_commands": terminal_commands,
            "final_answer": str(result.get("text", "")),
            "usage": usage,
        }

    @staticmethod
    def _media_paths(text: str) -> list[Path]:
        found: list[Path] = []
        for match in re.finditer(r"MEDIA:([^\s\"'\\]+\.ics)", text):
            candidate = Path(match.group(1))
            if candidate not in found:
                found.append(candidate)
        return found

    @staticmethod
    def _booking_url(text: str) -> str | None:
        match = re.search(r"https?://[^\s\"']+", text)
        return match.group(0) if match else None

    @staticmethod
    def _cli_url_argument(command: str) -> tuple[str | None, bool]:
        marker = "--url"
        index = command.find(marker)
        if index < 0:
            return None, False
        rest = command[index + len(marker):].lstrip()
        if not rest:
            return None, False
        quoted = rest[0] in {"'", '"'}
        if quoted:
            quote = rest[0]
            end = rest.find(quote, 1)
            return (rest[1:end] if end >= 0 else rest[1:]), True
        return rest.split(None, 1)[0], False

    @staticmethod
    def _unfold_ics(text: str) -> str:
        return text.replace("\r\n ", "").replace("\n ", "")

    @classmethod
    def _observe_ics(cls, path: Path) -> dict[str, Any]:
        text = cls._unfold_ics(path.read_text(encoding="utf-8"))
        blocks = re.findall(
            r"BEGIN:VEVENT\r?\n(.*?)END:VEVENT",
            text,
            flags=re.DOTALL,
        )
        events: list[dict[str, Any]] = []
        for block in blocks:
            def property_value(name: str) -> str:
                match = re.search(
                    rf"^{re.escape(name)}(?:;[^:]*)?:(.*)$",
                    block,
                    flags=re.MULTILINE,
                )
                return match.group(1).strip() if match else ""

            description = property_value("DESCRIPTION").replace(r"\n", "\n")
            events.append(
                {
                    "dtstart": property_value("DTSTART"),
                    "dtend": property_value("DTEND"),
                    "description": description,
                }
            )
        return {
            "sha256": cls.sha256(path),
            "event_count": len(events),
            "events": events,
        }

    def _oracle(self, scenario: str) -> dict[str, Any]:
        path = self.root / self.manifest["scenarios"][scenario]["oracle"]
        return json.loads(path.read_text(encoding="utf-8"))

    def _build_skill_root(
        self,
        version: str,
        root: Path,
    ) -> tuple[Path, dict[str, Any]]:
        skill_root = root / "skills"
        skill_file = Path(self.manifest["skill"]["path"])
        skill_dir = skill_file.parent
        relative_dir = skill_dir.relative_to(Path("hermes") / "skills")
        target_dir = skill_root / relative_dir
        identity = materialize_skill_source(
            self.repo_root,
            skill_dir,
            self.manifest["skill_versions"][version],
            target_dir,
        )
        replay_transport = self.root / "replay" / "carrier_http.py"
        target_transport = (
            target_dir / "scripts" / "flight_calendar" / "carrier_http.py"
        )
        target_transport.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(replay_transport, target_transport)
        identity = {
            **identity,
            "transport_replay_sha256": self.sha256(replay_transport),
        }
        return skill_root, identity

    def prepare(
        self,
        spec: RunSpec,
        run_dir: Path,
        case: dict[str, Any],
    ) -> dict[str, Any]:
        del case
        cfg = self.manifest["scenarios"][spec.scenario]
        prompt = self.root / cfg["prompt"]
        fixture = self.root / cfg["fixture"]
        prompt_sha = self.sha256(prompt)
        fixture_sha = self.sha256(fixture)
        if prompt_sha != spec.prompt_version:
            raise RuntimeError(
                f"prompt drift for {spec.scenario}: {prompt_sha} != {spec.prompt_version}"
            )
        (run_dir / "prompt.txt").write_text(
            prompt.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        workspace = run_dir / "workspace"
        workspace.mkdir()
        return {
            "prompt": prompt,
            "fixture": fixture,
            "workspace": workspace,
            "prompt_sha256": prompt_sha,
            "actual_fixture_version": fixture_sha,
        }

    def execute(
        self,
        spec: RunSpec,
        run_dir: Path,
        prepared: dict[str, Any],
        case: dict[str, Any],
    ) -> dict[str, Any]:
        del case
        home = Path(tempfile.mkdtemp(prefix="hermes-home-", dir="/tmp"))
        skill_temp = Path(tempfile.mkdtemp(prefix="hermes-skills-", dir="/tmp"))
        try:
            skill_root, skill_source = self._build_skill_root(
                spec.skill_version,
                skill_temp,
            )
            self._make_home(home, skill_root)

            env = os.environ.copy()
            env.update(
                {
                    "HERMES_HOME": str(home),
                    "HOME": str(Path.home()),
                    "TERMINAL_CWD": str(prepared["workspace"]),
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "FLIGHT_CALENDAR_EVAL_HTTP_FIXTURE": str(prepared["fixture"]),
                }
            )

            execution = self.manifest["execution"]
            command = [
                *self.hermes_command,
                "chat",
                "--query-file",
                str(prepared["prompt"]),
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
                cwd=prepared["workspace"],
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

            summary = self._event_summary(proc.stdout)
            final_answer = summary["final_answer"]
            raw_final.write_text(final_answer, encoding="utf-8")

            artifact_source: Path | None = None
            for candidate in self._media_paths(proc.stdout):
                if candidate.is_file():
                    artifact_source = candidate
                    break

            artifact_path: Path | None = None
            artifact_observation: dict[str, Any] | None = None
            if artifact_source is not None:
                artifact_path = run_dir / "artifact.ics"
                shutil.copy2(artifact_source, artifact_path)
                artifact_observation = self._observe_ics(artifact_path)

            terminal_commands = summary["terminal_commands"]
            cli_build_calls = sum(
                1
                for value in terminal_commands
                if "flight_calendar_ics.py" in value and "build" in value
            )
            prompt_url = self._booking_url(
                prepared["prompt"].read_text(encoding="utf-8")
            )
            cli_commands = [
                value
                for value in terminal_commands
                if "flight_calendar_ics.py" in value and "build" in value
            ]
            first_cli_url: str | None = None
            first_cli_quoted = False
            if cli_commands:
                first_cli_url, first_cli_quoted = self._cli_url_argument(
                    cli_commands[0]
                )
            if prompt_url and first_cli_url:
                url_integrity = "exact" if prompt_url == first_cli_url else "changed"
            else:
                url_integrity = "missing"

            report_notes: list[str] = []
            if url_integrity == "changed":
                report_notes.append("URL изменён перед CLI")
            if (
                first_cli_url
                and not first_cli_quoted
                and re.search(r"[&;|<>$()]", first_cli_url)
            ):
                report_notes.append("URL без shell quoting")
            if cli_build_calls != 1:
                report_notes.append(f"CLI вызван {cli_build_calls} раза")

            report_facts = {
                "CLI": cli_build_calls,
                "URL": url_integrity,
            }
            report_note = "; ".join(report_notes) if report_notes else None

            metrics = {
                "tool_calls": len(summary["tool_uses"]),
                "terminal_calls": len(terminal_commands),
                "cli_build_calls": cli_build_calls,
                "event_count": summary["event_count"],
                "duration_seconds": elapsed,
                "usage": summary["usage"],
            }

            metadata = {
                "scenario": spec.scenario,
                "skill_version": spec.skill_version,
                "skill_source": skill_source,
                "fixture_sha256": prepared["actual_fixture_version"],
                "prompt_sha256": prepared["prompt_sha256"],
                "hermes_executable": self.hermes_command[0],
                "model": spec.model,
                "provider": spec.provider,
                "toolsets": execution["toolsets"],
                "command": command,
                "started_at": started.isoformat(),
                "ended_at": ended.isoformat(),
                "elapsed_seconds": elapsed,
                "exit_code": proc.returncode,
                "event_summary": summary,
                "artifact_source_path": str(artifact_source) if artifact_source else None,
                "artifact_evidence_path": str(artifact_path) if artifact_path else None,
                "artifact_observation": artifact_observation,
                "metrics": metrics,
                "report_facts": report_facts,
                "report_note": report_note,
            }
            (run_dir / "metadata.json").write_text(
                json.dumps(metadata, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            return {
                **metadata,
                "execution_status": (
                    "COMPLETED" if proc.returncode == 0 else "RUNTIME_FAILURE"
                ),
                "final_answer": final_answer,
                "tool_uses": summary["tool_uses"],
                "tool_names": summary["tool_names"],
                "terminal_commands": terminal_commands,
                "raw_stream_path": str(raw_stream),
                "raw_stderr_path": str(raw_stderr),
                "raw_final_answer_path": str(raw_final),
            }
        finally:
            shutil.rmtree(home, ignore_errors=True)
            shutil.rmtree(skill_temp, ignore_errors=True)

    def evaluate_dimension(
        self,
        dimension: str,
        evidence: dict[str, Any],
        rules: dict[str, Any],
    ) -> str:
        oracle = self._oracle(str(evidence["scenario"]))

        if dimension == "outcome":
            artifact_path = evidence.get("artifact_evidence_path")
            observation = evidence.get("artifact_observation")
            if not artifact_path or not Path(str(artifact_path)).is_file():
                return "FAIL"
            if not isinstance(observation, dict):
                return "FAIL"
            if observation.get("event_count") != oracle["expected_event_count"]:
                return "FAIL"

            actual_events = list(observation.get("events", []))
            for expected in oracle["events"]:
                matching = [
                    event
                    for event in actual_events
                    if event.get("dtstart") == expected["dtstart"]
                    and event.get("dtend") == expected["dtend"]
                ]
                if len(matching) != 1:
                    return "FAIL"
                description = str(matching[0].get("description", ""))
                if not all(
                    fragment in description
                    for fragment in expected.get("description_fragments", [])
                ):
                    return "FAIL"

            final_answer = str(evidence.get("final_answer", ""))
            if "MEDIA:" not in final_answer or ".ics" not in final_answer:
                return "FAIL"
            return "PASS"

        if dimension == "trajectory":
            terminal_commands = list(evidence.get("terminal_commands", []))
            if rules.get("require_single_terminal_call") and len(terminal_commands) != 1:
                return "FAIL"
            if not terminal_commands:
                return "FAIL"

            command = terminal_commands[0]
            if not all(
                fragment in command
                for fragment in rules.get("required_cli_fragments", [])
            ):
                return "FAIL"
            if any(
                re.search(pattern, command, flags=re.IGNORECASE)
                for pattern in rules.get("forbidden_command_patterns", [])
            ):
                return "FAIL"

            forbidden_names = set(rules.get("forbidden_tool_names", []))
            if any(name in forbidden_names for name in evidence.get("tool_names", [])):
                return "FAIL"

            if rules.get("stop_after_cli"):
                uses = list(evidence.get("tool_uses", []))
                cli_indexes = [
                    int(use["index"])
                    for use in uses
                    if use.get("name") == "terminal"
                    and "flight_calendar_ics.py"
                    in str((use.get("input") or {}).get("command", ""))
                ]
                if len(cli_indexes) != 1:
                    return "FAIL"
                if any(int(use["index"]) > cli_indexes[0] for use in uses):
                    return "FAIL"
            return "PASS"

        if dimension == "privacy":
            final_answer = str(evidence.get("final_answer", ""))
            forbidden = oracle.get("privacy_forbidden_final_answer", [])
            return "FAIL" if any(marker in final_answer for marker in forbidden) else "PASS"

        return "UNDEFINED"
