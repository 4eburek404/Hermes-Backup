from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evals.harness.core import RunSpec
from evals.harness.report import write_report
from evals.harness.skill_source import materialize_skill_source


class EvaluatorPreflightError(RuntimeError):
    """The deterministic reference result failed the current evaluator."""


class FlightCalendarIcsConsumer:
    name = "flight-calendar-ics"

    def __init__(
        self,
        root: Path,
        repo_root: Path,
        manifest: dict[str, Any],
        hermes_command: list[str] | None = None,
    ) -> None:
        self.root = root.resolve()
        self.repo_root = repo_root.resolve()
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
    def _decode_tool_result(event: dict[str, Any]) -> dict[str, Any]:
        raw = event.get("output")
        if not isinstance(raw, str):
            return {}
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(envelope, dict):
            return {}
        payload = envelope.get("output")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                pass
        return {
            "exit_code": envelope.get("exit_code"),
            "payload": payload if isinstance(payload, dict) else {},
            "is_error": bool(envelope.get("error")) or bool(event.get("is_error")),
        }

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

        result_event = next(
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
        terminal_invocations: list[dict[str, Any]] = []
        for index, event in enumerate(events):
            if event.get("type") != "tool_use" or event.get("name") != "terminal":
                continue
            command = str((event.get("input") or {}).get("command", ""))
            result_event = next(
                (
                    candidate
                    for candidate in events[index + 1 :]
                    if candidate.get("type") == "tool_result"
                    and candidate.get("name") == "terminal"
                ),
                {},
            )
            decoded = FlightCalendarIcsConsumer._decode_tool_result(result_event)
            payload = decoded.get("payload") or {}
            terminal_invocations.append(
                {
                    "tool_index": index,
                    "command": command,
                    "exit_code": decoded.get("exit_code"),
                    "success": decoded.get("exit_code") == 0 and payload.get("ok") is True,
                    "is_cli": "flight_calendar_ics.py" in command and "build" in command,
                }
            )
        cli_attempts = [item for item in terminal_invocations if item["is_cli"]]
        successful_cli_index = next(
            (item["tool_index"] for item in cli_attempts if item["success"]),
            None,
        )
        return {
            "event_count": len(events),
            "tool_uses": tool_uses,
            "tool_names": [use["name"] for use in tool_uses],
            "terminal_commands": terminal_commands,
            "terminal_invocations": terminal_invocations,
            "cli_attempts": cli_attempts,
            "successful_cli_index": successful_cli_index,
            "has_result": bool(result_event),
            "final_answer": str(result_event.get("text", "")),
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
    def _intermediate_input_path(
        commands: list[str], workspace: Path
    ) -> Path | None:
        for command in commands:
            try:
                tokens = shlex.split(command)
            except ValueError:
                continue
            if "--input" not in tokens:
                continue
            index = tokens.index("--input")
            if index + 1 >= len(tokens):
                continue
            path = Path(tokens[index + 1])
            return path if path.is_absolute() else workspace / path
        return None

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

    @staticmethod
    def _reference_itinerary(scenario: str) -> dict[str, Any]:
        if scenario == "pdf-success":
            return {
                "passenger": "REFERENCE ONLY",
                "pnr": "REFPDF",
                "ticket_number": "5550000000000",
                "booking_url": "",
                "flights": [
                    {
                        "flight_number": "SU9011",
                        "departure": {"airport": "SVO", "local": "2037-10-03T09:15"},
                        "arrival": {"airport": "SVX", "local": "2037-10-03T13:45"},
                        "aircraft": "Boeing 737-800",
                    },
                    {
                        "flight_number": "SU9012",
                        "departure": {"airport": "SVX", "local": "2037-10-06T18:10"},
                        "arrival": {"airport": "SVO", "local": "2037-10-06T18:45"},
                        "aircraft": "Airbus A320",
                    },
                ],
            }
        raise ValueError(f"no canonical itinerary for {scenario}")

    def _run_reference_cli(self, scenario: str) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="flight-calendar-preflight-") as temp:
            temp_root = Path(temp)
            skill_temp = temp_root / "skill-source"
            cache_dir = temp_root / "cache"
            cache_dir.mkdir()
            home = temp_root / "home"
            skill_root, skill_source = self._build_skill_root("candidate", skill_temp)
            self._seed_timezone_cache(skill_root, cache_dir)
            self._make_home(home, skill_root)

            env = os.environ.copy()
            env.update(
                {
                    "HERMES_HOME": str(home),
                    "FLIGHT_CALENDAR_EVAL_SCENARIO": scenario,
                    "FLIGHT_CALENDAR_EVAL_HTTP_FIXTURE": str(
                        self.root
                        / ("fixtures/ural/reservation.json" if scenario == "ural-url-success" else "fixtures/aeroflot-pnr-view-v3.json")
                    ),
                    "FLIGHT_CALENDAR_CACHE_DIR": str(cache_dir),
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
            )
            script = skill_root / "travel" / "flight-calendar-ics" / "scripts" / "flight_calendar_ics.py"
            workspace = temp_root / "workspace"
            workspace.mkdir()
            if scenario in {"ural-url-success", "url-success"}:
                command = [
                    sys.executable,
                    str(script),
                    "--json",
                    "build",
                    "--url",
                    (
                        "https://service.uralairlines.ru/?pnr=ABC123&lastName=IVANOV"
                        if scenario == "ural-url-success"
                        else "https://www.aeroflot.ru/sb/pnr/app/ru-ru#/pnr?pnr_key=5da7002148b11050a6a14aaf19c109248a0dd95cb94d03a91a1fb124765b00d7&pnr_locator=ABC123"
                    ),
                ]
            else:
                input_path = workspace / "reference-itinerary.json"
                input_path.write_text(
                    json.dumps(self._reference_itinerary(scenario), ensure_ascii=False),
                    encoding="utf-8",
                )
                command = [sys.executable, str(script), "--json", "build", "--input", str(input_path)]
            proc = subprocess.run(command, cwd=workspace, env=env, text=True, capture_output=True, check=False)
            payload = {}
            for line in reversed(proc.stdout.splitlines()):
                try:
                    candidate = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(candidate, dict):
                    payload = candidate
                    break
            if proc.returncode != 0 or payload.get("ok") is not True:
                raise RuntimeError(f"reference CLI failed for {scenario}: {payload.get('error', 'unknown error')}")
            media = str(payload.get("media", ""))
            artifact_path = Path(media.removeprefix("MEDIA:"))
            if not artifact_path.is_file():
                raise RuntimeError(f"reference CLI returned missing artifact for {scenario}")
            return {
                "scenario": scenario,
                "skill_source": skill_source,
                "artifact_evidence_path": str(artifact_path),
                "artifact_observation": self._observe_ics(artifact_path),
                "final_answer": media,
                "intermediate_itinerary": self._reference_itinerary(scenario)
                if scenario == "pdf-success"
                else None,
                "intermediate_input_path": str(workspace / "reference-itinerary.json")
                if scenario == "pdf-success"
                else None,
            }

    def preflight(self, scenarios: list[str]) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for scenario in scenarios:
            evidence = self._run_reference_cli(scenario)
            detail = self.evaluate_dimension_diagnostic("outcome", evidence, {})
            results[scenario] = {"score": detail["status"], "diagnostic": detail}
            if detail["status"] != "PASS":
                raise EvaluatorPreflightError(
                    f"{scenario}: {detail.get('reason') or 'known-good reference rejected'}"
                )
        return results

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

    @staticmethod
    def _seed_timezone_cache(skill_root: Path, cache_dir: Path) -> None:
        bundled = skill_root / "travel" / "flight-calendar-ics" / "data" / "airport-timezones.json"
        shutil.copy2(bundled, cache_dir / "airport-timezones.json")
        (cache_dir / "refresh-state.json").write_text(
            json.dumps({"last_success": datetime.now(timezone.utc).isoformat()}) + "\n",
            encoding="utf-8",
        )

    def prepare(
        self,
        spec: RunSpec,
        run_dir: Path,
        case: dict[str, Any],
    ) -> dict[str, Any]:
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
        if spec.scenario == "pdf-success":
            shutil.copy2(fixture, workspace / "ticket.pdf")
        return {
            "prompt": prompt,
            "fixture": fixture,
            "workspace": workspace,
            "prompt_sha256": prompt_sha,
            "actual_fixture_version": fixture_sha,
            "pdf_input": workspace / "ticket.pdf" if spec.scenario == "pdf-success" else None,
        }

    def execute(
        self,
        spec: RunSpec,
        run_dir: Path,
        prepared: dict[str, Any],
        case: dict[str, Any],
    ) -> dict[str, Any]:
        home = Path(tempfile.mkdtemp(prefix="hermes-home-", dir="/tmp"))
        skill_temp = Path(tempfile.mkdtemp(prefix="hermes-skills-", dir="/tmp"))
        cache_dir = run_dir / "cache"
        cache_dir.mkdir()
        anydoc_log = run_dir / "anydoc-calls.log"
        try:
            skill_root, skill_source = self._build_skill_root(
                spec.skill_version,
                skill_temp,
            )
            self._seed_timezone_cache(skill_root, cache_dir)
            self._make_home(home, skill_root)

            env = os.environ.copy()
            env.update(
                {
                    "HERMES_HOME": str(home),
                    "HOME": str(Path.home()),
                    "TERMINAL_CWD": str(prepared["workspace"]),
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "FLIGHT_CALENDAR_EVAL_HTTP_FIXTURE": str(prepared["fixture"]),
                    "FLIGHT_CALENDAR_EVAL_SCENARIO": spec.scenario,
                    "FLIGHT_CALENDAR_CACHE_DIR": str(cache_dir),
                    "FLIGHT_CALENDAR_EVAL_ANYDOC_FIXTURE": str(
                        self.root / "fixtures" / "pdf" / "anydoc.md"
                    ),
                    "FLIGHT_CALENDAR_EVAL_ANYDOC_LOG": str(anydoc_log),
                }
            )
            if spec.scenario == "pdf-success":
                shim_dir = self.root / "replay" / "pdf"
                env["PATH"] = f"{shim_dir}{os.pathsep}{env.get('PATH', '')}"

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
            prompt_url = (
                self._booking_url(prepared["prompt"].read_text(encoding="utf-8"))
                if spec.scenario != "pdf-success"
                else None
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
            if spec.scenario == "pdf-success":
                url_integrity = "—"
            elif prompt_url and first_cli_url:
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

            anydoc_commands = [
                value for value in terminal_commands if "@firecrawl/anydoc" in value
            ]
            intermediate_input = self._intermediate_input_path(
                cli_commands, prepared["workspace"]
            )
            intermediate_evidence = None
            if intermediate_input is not None and intermediate_input.is_file():
                intermediate_evidence = run_dir / "intermediate-itinerary.json"
                shutil.copy2(intermediate_input, intermediate_evidence)

            if spec.scenario == "pdf-success" and len(anydoc_commands) != 1:
                report_notes.append(f"AnyDoc вызван {len(anydoc_commands)} раз")
            report_facts = {
                "CLI": cli_build_calls,
                "URL": url_integrity,
                "CLI success": sum(1 for attempt in summary["cli_attempts"] if attempt["success"]),
            }
            if spec.scenario == "pdf-success":
                report_facts.update(
                    {"Source": "PDF", "AnyDoc": len(anydoc_commands)}
                )
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
                "execution_status": classify_execution_status(proc.returncode, summary),
                "event_summary": summary,
                "artifact_source_path": str(artifact_source) if artifact_source else None,
                "artifact_evidence_path": str(artifact_path) if artifact_path else None,
                "artifact_observation": artifact_observation,
                "metrics": metrics,
                "report_facts": report_facts,
                "report_note": report_note,
                "cache_dir": str(cache_dir),
                "anydoc_calls": anydoc_commands,
                "intermediate_input_path": str(intermediate_evidence)
                if intermediate_evidence
                else None,
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
                "terminal_invocations": summary["terminal_invocations"],
                "cli_attempts": summary["cli_attempts"],
                "successful_cli_index": summary["successful_cli_index"],
                "raw_stream_path": str(raw_stream),
                "raw_stderr_path": str(raw_stderr),
                "raw_final_answer_path": str(raw_final),
            }
        finally:
            shutil.rmtree(home, ignore_errors=True)
            shutil.rmtree(skill_temp, ignore_errors=True)

    def evaluate_dimension_diagnostic(
        self,
        dimension: str,
        evidence: dict[str, Any],
        rules: dict[str, Any],
    ) -> dict[str, Any]:
        oracle = self._oracle(str(evidence.get("scenario") or "url-success"))

        def fail(reason: str) -> dict[str, Any]:
            return {"status": "FAIL", "reason": reason}

        if dimension == "outcome":
            artifact_path = evidence.get("artifact_evidence_path")
            observation = evidence.get("artifact_observation")
            if not artifact_path or not Path(str(artifact_path)).is_file():
                return fail("artifact missing")
            if not isinstance(observation, dict):
                return fail("artifact observation missing")
            expected_count = oracle["expected_event_count"]
            actual_count = observation.get("event_count")
            if actual_count != expected_count:
                return fail(f"expected {expected_count} VEVENT, got {actual_count}")

            actual_events = list(observation.get("events", []))
            for expected in oracle["events"]:
                matching = [
                    event
                    for event in actual_events
                    if event.get("dtstart") == expected["dtstart"]
                    and event.get("dtend") == expected["dtend"]
                ]
                if len(matching) != 1:
                    return fail(
                        f"DTSTART/DTEND mismatch: expected {expected['dtstart']}–{expected['dtend']}"
                    )
                description = str(matching[0].get("description", ""))
                for fragment in expected.get("description_fragments", []):
                    if fragment not in description:
                        return fail(f"missing expected description fragment: {fragment}")
                for alternatives in expected.get("description_any_fragments", []):
                    if not any(fragment in description for fragment in alternatives):
                        return fail("missing expected description alternative")

            intermediate_numbers = oracle.get("intermediate_flight_numbers", [])
            if intermediate_numbers:
                path = evidence.get("intermediate_input_path")
                try:
                    if path and Path(str(path)).is_file():
                        itinerary = json.loads(Path(str(path)).read_text(encoding="utf-8"))
                    else:
                        itinerary = evidence.get("intermediate_itinerary")
                    if not isinstance(itinerary, dict):
                        return fail("intermediate itinerary evidence missing")
                    actual_numbers = [str(item.get("flight_number")) for item in itinerary.get("flights", [])]
                except (OSError, json.JSONDecodeError, AttributeError):
                    return fail("intermediate itinerary evidence unreadable")
                for number in intermediate_numbers:
                    if number not in actual_numbers:
                        return fail(f"missing flight number in intermediate itinerary: {number}")

            final_answer = str(evidence.get("final_answer", ""))
            if "MEDIA:" not in final_answer or ".ics" not in final_answer:
                return fail("exact MEDIA response missing")
            if oracle.get("final_answer_exact_media") and not re.fullmatch(
                r"MEDIA:[^\s]+\.ics", final_answer.strip()
            ):
                return fail("final answer is not exact MEDIA response")
            return {"status": "PASS", "reason": None}

        if dimension == "trajectory":
            terminal_commands = list(evidence.get("terminal_commands", []))
            cli_commands = [
                command
                for command in terminal_commands
                if "flight_calendar_ics.py" in command and "build" in command
            ]
            if rules.get("require_single_terminal_call") and len(terminal_commands) != 1:
                return fail(f"expected one terminal call, got {len(terminal_commands)}")
            if not cli_commands:
                return fail("CLI build call missing")

            if not all(
                any(fragment in command for command in cli_commands)
                for fragment in rules.get("required_cli_fragments", [])
            ):
                return fail("required CLI fragment missing")
            if any(
                re.search(pattern, value, flags=re.IGNORECASE)
                for pattern in rules.get("forbidden_command_patterns", [])
                for value in terminal_commands
            ):
                return fail("forbidden command pattern used")

            forbidden_names = set(rules.get("forbidden_tool_names", []))
            if any(name in forbidden_names for name in evidence.get("tool_names", [])):
                return fail("forbidden tool used")

            anydoc_calls = list(evidence.get("anydoc_calls", []))
            if rules.get("require_single_anydoc_call") and len(anydoc_calls) != 1:
                return fail(f"expected one AnyDoc call, got {len(anydoc_calls)}")
            if rules.get("require_anydoc_before_cli"):
                positions = [
                    index for index, value in enumerate(terminal_commands)
                    if "@firecrawl/anydoc" in value
                ]
                first_cli = next(
                    (index for index, value in enumerate(terminal_commands) if value in cli_commands),
                    None,
                )
                if not positions or first_cli is None or positions[0] >= first_cli:
                    return fail("AnyDoc was not called before CLI")
            if rules.get("require_intermediate_input"):
                input_path = evidence.get("intermediate_input_path")
                if not input_path or not Path(str(input_path)).is_file():
                    return fail("intermediate itinerary evidence missing")
                if Path(str(input_path)).suffix.lower() != ".json":
                    return fail("CLI input was not JSON itinerary")

            attempts = list(evidence.get("cli_attempts", []))
            successful = [attempt for attempt in attempts if attempt.get("success")]
            if rules.get("require_successful_cli") and not successful:
                return fail("CLI did not return ok:true")
            if rules.get("stop_after_successful_cli") and successful:
                success_index = successful[0].get("tool_index")
                if success_index is None:
                    success_index = evidence.get("successful_cli_index")
                if success_index is not None and any(
                    int(use.get("index", -1)) > int(success_index)
                    for use in evidence.get("tool_uses", [])
                ):
                    return fail("tool call after successful CLI")
            return {"status": "PASS", "reason": None}

        if dimension == "privacy":
            final_answer = str(evidence.get("final_answer", ""))
            forbidden = oracle.get("privacy_forbidden_final_answer", [])
            if any(marker in final_answer for marker in forbidden):
                return fail("synthetic private marker leaked in final answer")
            return {"status": "PASS", "reason": None}

        return {"status": "UNDEFINED", "reason": "unsupported evaluation dimension"}

    def evaluate_dimension(
        self,
        dimension: str,
        evidence: dict[str, Any],
        rules: dict[str, Any],
    ) -> str:
        return str(self.evaluate_dimension_diagnostic(dimension, evidence, rules)["status"])

    def classify_saved_evidence(self, evidence: dict[str, Any]) -> dict[str, Any]:
        stream_path = evidence.get("raw_stream_path")
        if not stream_path or not Path(str(stream_path)).is_file():
            return evidence
        summary = self._event_summary(Path(str(stream_path)).read_text(encoding="utf-8"))
        return {
            **evidence,
            "execution_status": classify_execution_status(int(evidence.get("exit_code", 0)), summary),
            "event_summary": summary,
            "final_answer": summary["final_answer"] or evidence.get("final_answer", ""),
            "tool_uses": summary["tool_uses"],
            "tool_names": summary["tool_names"],
            "terminal_commands": summary["terminal_commands"],
            "terminal_invocations": summary["terminal_invocations"],
            "cli_attempts": summary["cli_attempts"],
            "successful_cli_index": summary["successful_cli_index"],
        }

    def reevaluate_batch(
        self,
        batch_dir: Path,
        case: dict[str, Any],
        output_dir: Path,
    ) -> dict[str, Any]:
        source_manifest = json.loads((batch_dir / "batch_manifest.json").read_text(encoding="utf-8"))
        output_dir.mkdir(parents=True, exist_ok=False)
        runs: list[dict[str, Any]] = []
        for source_run in source_manifest.get("runs", []):
            evidence_path = Path(str(source_run["evidence_path"]))
            evidence = self.classify_saved_evidence(
                json.loads(evidence_path.read_text(encoding="utf-8"))
            )
            rules = case.get("rules", {}).get(str(evidence.get("scenario")), {})
            from evals.harness.core import evaluate_dimension_details

            diagnostics = evaluate_dimension_details(self, evidence, rules)
            score = {name: detail["status"] for name, detail in diagnostics.items()}
            run = {
                **source_run,
                **evidence,
                "score": score,
                "diagnostics": diagnostics,
                "report_note": None,
            }
            run_dir = output_dir / "runs" / str(run["run_id"])
            run_dir.mkdir(parents=True, exist_ok=False)
            (run_dir / "evaluation.json").write_text(
                json.dumps(
                    {
                        "source_evidence": str(evidence_path),
                        "execution_status": run.get("execution_status"),
                        "score": score,
                        "diagnostics": diagnostics,
                    },
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            run["evidence_path"] = str(evidence_path)
            runs.append(run)

        batch = {
            "consumer": source_manifest.get("consumer", self.name),
            "reevaluation": True,
            "source_batch": str(batch_dir),
            "agent_execution_count": 0,
            "expected_run_ids": source_manifest.get("expected_run_ids", []),
            "executed_run_ids": [run["run_id"] for run in runs],
            "runs": runs,
        }
        (output_dir / "batch_manifest.json").write_text(
            json.dumps(batch, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        report_path = write_report(batch, case, output_dir)
        batch["report_path"] = str(report_path)
        (output_dir / "batch_manifest.json").write_text(
            json.dumps(batch, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (output_dir / "metadata.json").write_text(
            json.dumps(
                {
                    "source_batch": str(batch_dir),
                    "agent_execution_count": 0,
                    "evaluator": "flight-calendar-ics-consumer",
                    "oracle_files": {
                        scenario: self.manifest["scenarios"][scenario]["oracle"]
                        for scenario in case.get("scenarios", [])
                    },
                },
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        return batch


def classify_execution_status(returncode: int, summary: dict[str, Any]) -> str:
    if returncode == 0 and summary.get("has_result"):
        return "COMPLETED"
    if summary.get("has_result") or summary.get("final_answer"):
        return "AGENT_FAILURE"
    return "RUNTIME_FAILURE"
