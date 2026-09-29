from __future__ import annotations

import hashlib
import importlib.util
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
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from evals.harness.core import RunSpec
from evals.harness.process import run_with_timeout
from evals.harness.report import write_report
from evals.harness.skill_source import materialize_skill_source

_REPLAY_DIRECTORY = Path(__file__).resolve().parent / "replay"
_EGRESS_SPEC = importlib.util.spec_from_file_location(
    "tutu_search_flights_egress_proxy", _REPLAY_DIRECTORY / "egress_proxy.py"
)
if _EGRESS_SPEC is None or _EGRESS_SPEC.loader is None:
    raise RuntimeError("cannot load recorded Tutu egress guard")
_EGRESS_MODULE = importlib.util.module_from_spec(_EGRESS_SPEC)
_EGRESS_SPEC.loader.exec_module(_EGRESS_MODULE)
TutuEgressGuard = _EGRESS_MODULE.TutuEgressGuard


class TutuSearchFlightsConsumer:
    name = "tutu-search-flights"

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
    def sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

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
    def _result_text(fixture: dict[str, Any]) -> str:
        return str(fixture["response"]["envelope"]["result"]["content"][0]["text"])

    @classmethod
    def _result_payload(cls, fixture: dict[str, Any]) -> dict[str, Any]:
        value = json.loads(cls._result_text(fixture))
        if not isinstance(value, dict) or not isinstance(value.get("offers"), list):
            raise ValueError("recorded Tutu result has no offers list")
        return value

    @staticmethod
    def _decode_event_output(event: dict[str, Any]) -> dict[str, Any]:
        raw = event.get("output")
        if not isinstance(raw, str):
            return {}
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError:
            if (
                event.get("is_error") is False
                and all(marker in raw for marker in ("pricing_basis", "offers", "flight_number"))
            ):
                return {
                    "exit_code": None,
                    "payload": {"offers": [{}]},
                    "is_error": False,
                    "structured_cli_output": True,
                }
            return {}
        if not isinstance(envelope, dict):
            return {}
        output = envelope.get("output")
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except json.JSONDecodeError:
                pass
        return {
            "exit_code": envelope.get("exit_code"),
            "payload": output if isinstance(output, dict) else {},
            "is_error": bool(envelope.get("error")) or bool(event.get("is_error")),
        }

    @classmethod
    def _event_summary(cls, stdout: str) -> dict[str, Any]:
        events: list[dict[str, Any]] = []
        for line in stdout.splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and value.get("type"):
                events.append(value)

        tool_uses: list[dict[str, Any]] = []
        terminal_invocations: list[dict[str, Any]] = []
        for index, event in enumerate(events):
            if event.get("type") != "tool_use":
                continue
            name = str(event.get("name", ""))
            tool_input = event.get("input")
            tool_input = tool_input if isinstance(tool_input, dict) else {}
            tool_uses.append({"index": index, "name": name, "input": tool_input})
            if name != "terminal":
                continue
            command = str(tool_input.get("command", ""))
            result_event = next(
                (
                    candidate
                    for candidate in events[index + 1 :]
                    if candidate.get("type") == "tool_result"
                    and candidate.get("name") == "terminal"
                ),
                {},
            )
            result = cls._decode_event_output(result_event)
            payload = result.get("payload") or {}
            terminal_invocations.append(
                {
                    "tool_index": index,
                    "result_index": events.index(result_event) if result_event else None,
                    "command": command,
                    "exit_code": result.get("exit_code"),
                    "success": (
                        not result.get("is_error")
                        and isinstance(payload.get("offers"), list)
                        and (
                            result.get("exit_code") == 0
                            or result.get("structured_cli_output") is True
                        )
                    ),
                }
            )

        result_event = next(
            (event for event in reversed(events) if event.get("type") == "result"),
            {},
        )
        return {
            "event_count": len(events),
            "tool_uses": tool_uses,
            "tool_names": [use["name"] for use in tool_uses],
            "terminal_invocations": terminal_invocations,
            "terminal_commands": [
                item["command"] for item in terminal_invocations if item["command"]
            ],
            "final_answer": str(result_event.get("text", "")),
            "final_event_index": events.index(result_event) if result_event else None,
            "has_result": bool(result_event),
        }

    def prepare(
        self,
        spec: RunSpec,
        run_dir: Path,
        case: dict[str, Any],
    ) -> dict[str, Any]:
        scenario = self.manifest["scenarios"][spec.scenario]
        prompt = self.root / scenario["prompt"]
        fixture = self.root / scenario["fixture"]
        prompt_sha = self.sha256(prompt)
        fixture_sha = self.sha256(fixture)
        if prompt_sha != spec.prompt_version:
            raise RuntimeError(f"prompt drift: {prompt_sha} != {spec.prompt_version}")

        source_config = self.manifest["skill_versions"][spec.skill_version]
        skill_relative = Path(self.manifest["skill"]["path"]).parent
        materialized_owner = tempfile.TemporaryDirectory(prefix="tutu-skill-source-")
        materialized = (
            Path(materialized_owner.name)
            / "skills"
            / skill_relative.relative_to(Path("hermes") / "skills")
        )
        try:
            skill_identity = materialize_skill_source(
                self.repo_root,
                skill_relative,
                source_config,
                materialized,
            )
            reference_commit = source_config.get("reference_commit")
            if reference_commit and skill_identity["resolved_commit"] != reference_commit:
                raise RuntimeError(
                    "candidate source ref resolved to an unexpected commit: "
                    f"{skill_identity['resolved_commit']} != {reference_commit}"
                )
            candidate_fixture = materialized / scenario.get(
                "candidate_fixture", "fixtures/avia/baseline.json"
            )
            candidate_fixture_sha = self.sha256(candidate_fixture)
            if candidate_fixture_sha != scenario["fixture_sha256"]:
                raise RuntimeError(
                    "candidate skill's recorded result differs from eval fixture: "
                    f"{candidate_fixture_sha} != {scenario['fixture_sha256']}"
                )
        except Exception:
            materialized_owner.cleanup()
            raise

        workspace = run_dir / "workspace"
        workspace.mkdir(parents=True)
        prompt_copy = run_dir / "prompt.txt"
        shutil.copy2(prompt, prompt_copy)
        agent_query_path = run_dir / "agent-query.txt"
        user_prompt = prompt_copy.read_text(encoding="utf-8")
        agent_query_path.write_text(
            "Use the existing PYTHON environment variable for the skill CLI; it is the ready interpreter configured for this recorded evaluation. Do not replace it.\n\n"
            "User request:\n"
            + user_prompt,
            encoding="utf-8",
        )
        recorded = json.loads(fixture.read_text(encoding="utf-8"))
        return {
            "prompt": prompt_copy,
            "agent_query": agent_query_path,
            "prompt_sha256": prompt_sha,
            "fixture": fixture,
            "fixture_sha256": fixture_sha,
            "recorded_tutu_result": recorded,
            "workspace": workspace,
            "skill_root": materialized.parents[1],
            "skill_source": skill_identity,
            "materialized_owner": materialized_owner,
            "actual_fixture_version": fixture_sha,
        }

    @staticmethod
    def _parse_judge_response(stdout: str) -> dict[str, Any]:
        candidates = [stdout.strip()]
        match = re.search(r"\{.*\}", stdout, re.DOTALL)
        if match:
            candidates.append(match.group(0))
        for candidate in candidates:
            try:
                value = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and value.get("verdict") in {"PASS", "FAIL"}:
                claims = value.get("claims")
                if not isinstance(claims, list) or not all(
                    isinstance(item, dict) and isinstance(item.get("supported"), bool)
                    for item in claims
                ):
                    continue
                if not claims and value["verdict"] == "PASS":
                    continue
                return value
        raise ValueError("semantic judge did not return the required JSON contract")

    @staticmethod
    def _semantic_judge_status(value: dict[str, Any]) -> str:
        claims = value.get("claims")
        if not isinstance(claims, list) or not claims:
            return "ERROR"
        any_unsupported = any(claim.get("supported") is False for claim in claims)
        all_supported = all(claim.get("supported") is True for claim in claims)
        if value.get("verdict") == "PASS" and all_supported:
            return "PASS"
        if value.get("verdict") == "FAIL" and any_unsupported:
            return "FAIL"
        return "ERROR"

    def _run_semantic_judge(
        self,
        spec: RunSpec,
        prepared: dict[str, Any],
        run_dir: Path,
        env: dict[str, str],
        proxy_url: str,
        final_answer: str,
    ) -> dict[str, Any]:
        scenario = self.manifest["scenarios"][spec.scenario]
        outcome_config = scenario["evaluation"]["outcome"]
        judge_template_path = self.root / outcome_config["judge_prompt"]
        if self.sha256(judge_template_path) != outcome_config["judge_prompt_sha256"]:
            return {"status": "ERROR", "reason": "semantic-judge prompt hash mismatch"}
        template = judge_template_path.read_text(encoding="utf-8")
        fixture_result = self._result_payload(prepared["recorded_tutu_result"])
        judge_query = (
            template.replace("{user_prompt}", prepared["prompt"].read_text(encoding="utf-8"))
            .replace("{tutu_result}", json.dumps(fixture_result, ensure_ascii=False, indent=2))
            .replace("{final_answer}", _redact(final_answer))
        )
        query_path = run_dir / "semantic-judge-prompt.txt"
        response_path = run_dir / "semantic-judge-response.txt"
        query_path.write_text(_redact(judge_query), encoding="utf-8")
        judge_home_owner = tempfile.TemporaryDirectory(prefix="tutu-judge-home-")
        judge_home = Path(judge_home_owner.name)
        judge_home.mkdir(parents=True, exist_ok=True)
        source_home = Path.home() / ".hermes"
        for name in (".env", "auth.json"):
            source = source_home / name
            if source.exists():
                (judge_home / name).symlink_to(source)
        judge_env = env.copy()
        judge_env["HERMES_HOME"] = str(judge_home)
        judge_env["HTTPS_PROXY"] = proxy_url
        judge_env["HTTP_PROXY"] = proxy_url
        judge_env["ALL_PROXY"] = proxy_url
        judge_command = [
            *self.hermes_command,
            "chat",
            "--query-file",
            str(query_path),
            "--oneshot",
            "--quiet",
            "--format",
            "text",
            "--model",
            spec.model,
            "--provider",
            spec.provider,
            "--toolsets",
            "file",
            "--max-turns",
            "1",
            "--run-budget",
            "90",
            "--source",
            "eval",
        ]
        start = time.monotonic()
        try:
            proc, timed_out = run_with_timeout(
                judge_command,
                cwd=prepared["workspace"],
                env=judge_env,
                timeout_seconds=float(self.manifest["execution"]["judge_timeout_seconds"]),
            )
            response_path.write_text(_redact(proc.stdout), encoding="utf-8")
            if timed_out:
                return {
                    "status": "ERROR",
                    "reason": "semantic judge timed out",
                    "duration_seconds": time.monotonic() - start,
                    "model": spec.model,
                    "provider": spec.provider,
                    "prompt_path": str(query_path),
                    "response_path": str(response_path),
                }
            if proc.returncode != 0:
                return {
                    "status": "ERROR",
                    "reason": f"semantic judge exited {proc.returncode}: {_redact(proc.stderr)[:1000]}",
                    "duration_seconds": time.monotonic() - start,
                    "model": spec.model,
                    "provider": spec.provider,
                    "prompt_path": str(query_path),
                    "response_path": str(response_path),
                }
            value = self._parse_judge_response(proc.stdout)
            status = self._semantic_judge_status(value)
            return {
                "status": status,
                "verdict": value["verdict"],
                "claims": value["claims"],
                "reason": (
                    "semantic judge contract inconsistent: verdict conflicts with claim-level support"
                    if status == "ERROR"
                    else value.get("reason")
                ),
                "duration_seconds": time.monotonic() - start,
                "model": spec.model,
                "provider": spec.provider,
                "prompt_path": str(query_path),
                "response_path": str(response_path),
            }
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return {
                "status": "ERROR",
                "reason": f"semantic judge failure: {type(exc).__name__}: {exc}",
                "duration_seconds": time.monotonic() - start,
                "model": spec.model,
                "provider": spec.provider,
                "prompt_path": str(query_path),
                "response_path": str(response_path),
            }
        finally:
            judge_home_owner.cleanup()

    def execute(
        self,
        spec: RunSpec,
        run_dir: Path,
        prepared: dict[str, Any],
        case: dict[str, Any],
    ) -> dict[str, Any]:
        proxy = TutuEgressGuard(run_dir / "blocked-tutu-egress.jsonl")
        home_owner = tempfile.TemporaryDirectory(prefix="tutu-hermes-home-")
        home = Path(home_owner.name)
        replay_log = run_dir / "mcp-boundary.jsonl"
        fixture_config = self.manifest["scenarios"][spec.scenario]
        execution = self.manifest["execution"]
        self._make_home(home, prepared["skill_root"])

        env = os.environ.copy()
        replay_path = str(self.root / "replay")
        python_wrapper = run_dir / "recorded-python"
        python_wrapper.write_text(
            "#!/bin/sh\n"
            f"export PYTHONPATH={shlex.quote(replay_path)}${{PYTHONPATH:+:$PYTHONPATH}}\n"
            f"exec {shlex.quote(sys.executable)} \"$@\"\n",
            encoding="utf-8",
        )
        python_wrapper.chmod(0o700)
        old_pythonpath = env.get("PYTHONPATH", "")
        env.update(
            {
                "HERMES_HOME": str(home),
                "HOME": str(Path.home()),
                "TERMINAL_CWD": str(prepared["workspace"]),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHON": str(python_wrapper),
                "PYTHONPATH": os.pathsep.join(
                    value for value in (replay_path, old_pythonpath) if value
                ),
                "TUTU_EVAL_FIXTURE": str(prepared["fixture"].resolve()),
                "TUTU_EVAL_FIXTURE_ID": self.manifest["scenarios"][spec.scenario]["evaluation"]["outcome"]["fixture_id"],
                "TUTU_EVAL_BOUNDARY_LOG": str(replay_log),
            }
        )

        command = [
            *self.hermes_command,
            "chat",
            "--query-file",
            str(prepared["agent_query"]),
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
            str(execution["run_budget_seconds"]),
            "--yolo",
            "--source",
            str(execution["source"]),
        ]

        started_at = datetime.now(timezone.utc)
        started = time.monotonic()
        try:
            proxy.start()
            env["HTTPS_PROXY"] = proxy.url
            env["HTTP_PROXY"] = proxy.url
            env["ALL_PROXY"] = proxy.url
            env["NO_PROXY"] = "localhost,127.0.0.1,::1"
            proc, timed_out = run_with_timeout(
                command,
                cwd=prepared["workspace"],
                env=env,
                timeout_seconds=float(execution["eval_timeout_seconds"]),
            )
            elapsed = time.monotonic() - started
            ended_at = datetime.now(timezone.utc)
            summary = self._event_summary(proc.stdout)
            final_answer = summary["final_answer"]
            boundary_records = []
            if replay_log.is_file():
                boundary_records = [
                    json.loads(line)
                    for line in replay_log.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            blocked = proxy.records()
            semantic_judge = self._run_semantic_judge(
                spec,
                prepared,
                run_dir,
                env,
                proxy.url,
                final_answer,
            )

            raw_stream_path = run_dir / "raw_stream.jsonl"
            raw_stderr_path = run_dir / "raw_stderr.txt"
            final_answer_path = run_dir / "raw_final_answer.txt"
            raw_stream_path.write_text(_redact(proc.stdout), encoding="utf-8")
            raw_stderr_path.write_text(_redact(proc.stderr), encoding="utf-8")
            final_answer_path.write_text(_redact(final_answer), encoding="utf-8")

            execution_status = (
                "RUNTIME_FAILURE"
                if timed_out or not summary["has_result"]
                else ("COMPLETED" if proc.returncode == 0 else "AGENT_FAILURE")
            )
            actual_calls = [
                item for item in boundary_records if item.get("jsonrpc_method") == "tools/call"
            ]
            served_calls = [item for item in actual_calls if item.get("replay_status") == "fixture-served"]
            fixture = prepared["recorded_tutu_result"]
            return {
                "execution_status": execution_status,
                "exit_code": proc.returncode,
                "runtime_failure_reason": (
                    f"eval-owned timeout after {execution['eval_timeout_seconds']}s"
                    if timed_out
                    else None
                ),
                "started_at": started_at.isoformat(),
                "ended_at": ended_at.isoformat(),
                "elapsed_seconds": elapsed,
                "duration_seconds": elapsed,
                "model": spec.model,
                "provider": spec.provider,
                "scenario": spec.scenario,
                "skill_source": prepared["skill_source"],
                "resolved_skill_commit": prepared["skill_source"]["resolved_commit"],
                "prompt": prepared["prompt"].read_text(encoding="utf-8"),
                "agent_query": prepared["agent_query"].read_text(encoding="utf-8"),
                "prompt_sha256": prepared["prompt_sha256"],
                "recorded_tutu_result_id": fixture_config["evaluation"]["outcome"]["fixture_id"],
                "recorded_tutu_result_sha256": prepared["fixture_sha256"],
                "recorded_tutu_result_ref": fixture_config["fixture"],
                "recorded_tutu_result": fixture,
                "requested_search_arguments": fixture.get("arguments", {}),
                "actual_search_arguments": served_calls[0].get("arguments") if len(served_calls) == 1 else None,
                "mcp_boundary_requests": boundary_records,
                "blocked_tutu_egress_attempts": blocked,
                "tool_uses": summary["tool_uses"],
                "tool_names": summary["tool_names"],
                "terminal_commands": summary["terminal_commands"],
                "terminal_invocations": summary["terminal_invocations"],
                "final_event_index": summary["final_event_index"],
                "final_answer": _redact(final_answer),
                "semantic_judge": semantic_judge,
                "raw_stream_path": str(raw_stream_path),
                "raw_stderr_path": str(raw_stderr_path),
                "raw_final_answer_path": str(final_answer_path),
                "metrics": {
                    "tool_calls": len(summary["tool_uses"]),
                    "mcp_tools_calls": len(actual_calls),
                    "duration_seconds": elapsed,
                },
            }
        finally:
            proxy.close()
            home_owner.cleanup()
            prepared["materialized_owner"].cleanup()

    @staticmethod
    def _outcome_issues(answer: str, fixture: dict[str, Any]) -> list[str]:
        result = TutuSearchFlightsConsumer._result_payload(fixture)
        offers = result["offers"]
        source_flights_by_offer = [
            {
                str(segment.get("voyage_no", "")).replace(" ", "").upper()
                for leg in offer.get("legs", [])
                for segment in leg.get("segments", [])
                if segment.get("voyage_no")
            }
            for offer in offers
        ]
        source_flights = set().union(*source_flights_by_offer) if source_flights_by_offer else set()
        source_carriers = {
            str(carrier).casefold().strip()
            for offer in offers
            for carrier in offer.get("carriers", [])
        }
        for offer in offers:
            for leg in offer.get("legs", []):
                for segment in leg.get("segments", []):
                    if segment.get("carrier"):
                        source_carriers.add(str(segment["carrier"]).casefold().strip())
        issues: list[str] = []

        def offer_for_position(position: int) -> dict[str, Any] | None:
            before = answer[:position]
            matches = list(re.finditer(r"\b[A-Z][A-Z0-9]{0,2}\s*[-–]\s*\d{2,5}\b", before, re.I))
            if not matches:
                return None
            candidate = re.sub(r"\s+", "", matches[-1].group(0)).replace("–", "-").upper()
            return next((offer for offer in offers if candidate in {
                str(segment.get("voyage_no", "")).replace(" ", "").upper()
                for leg in offer.get("legs", [])
                for segment in leg.get("segments", [])
            }), None)

        flight_pattern = re.compile(r"\b[A-Z][A-Z0-9]{0,2}\s*[-–]\s*\d{2,5}\b", re.I)
        for match in flight_pattern.finditer(answer):
            value = re.sub(r"\s+", "", match.group(0)).replace("–", "-").upper()
            if value not in source_flights:
                issues.append(f"unsupported flight identifier: {match.group(0)}")

        alias_relation = re.compile(
            r"\b(?:это|является|обозначен(?:а|о)?\s+как|известен\s+как|то\s+же\s+самое\s+что|aka|also\s+known\s+as|same\s+as)\b",
            re.I,
        )
        for sentence in re.finditer(r"[^.!?\n]+", answer):
            identifiers = list(flight_pattern.finditer(sentence.group(0)))
            for left, right in zip(identifiers, identifiers[1:]):
                relation = sentence.group(0)[left.end():right.start()]
                if not alias_relation.search(relation):
                    continue
                left_id = re.sub(r"\s+", "", left.group(0)).replace("–", "-").upper()
                right_id = re.sub(r"\s+", "", right.group(0)).replace("–", "-").upper()
                if not any(left_id in flight_ids and right_id in flight_ids for flight_ids in source_flights_by_offer):
                    issues.append(
                        f"unsupported flight association: {left.group(0)} {relation.strip()} {right.group(0)}"
                    )

        carrier_pattern = re.compile(
            r"(?:авиакомпани\w*|перевозчик\w*)\s+(?:[«\"“])?([^,;.!?\n»”\"]+)",
            re.IGNORECASE,
        )
        for match in carrier_pattern.finditer(answer):
            candidate = re.sub(r"\s+(?:за|по|на|с|вылет|выполняет)\b.*$", "", match.group(1), flags=re.I)
            candidate = candidate.strip(" \t:—–-«»\"“”")
            selected_offer = offer_for_position(match.start())
            if selected_offer is None:
                allowed_carriers = source_carriers
            else:
                allowed_carriers = {
                    str(carrier).casefold().strip()
                    for carrier in selected_offer.get("carriers", [])
                }
                allowed_carriers.update(
                    str(segment.get("carrier", "")).casefold().strip()
                    for leg in selected_offer.get("legs", [])
                    for segment in leg.get("segments", [])
                    if segment.get("carrier")
                )
            if candidate and candidate.casefold() not in allowed_carriers:
                issues.append(f"unsupported carrier claim: {candidate}")

        def allowed_offers(position: int) -> list[dict[str, Any]]:
            selected = offer_for_position(position)
            return [selected] if selected is not None else offers

        def variants_for_position(position: int) -> list[dict[str, Any]]:
            selected_offers = allowed_offers(position)
            sentence_start = max(
                (answer.rfind(marker, 0, position) for marker in ".!?;\n"),
                default=-1,
            ) + 1
            preceding = answer[sentence_start:position].casefold()
            fare_hits: list[tuple[int, int, str, dict[str, Any]]] = []
            for offer in selected_offers:
                for variant in offer.get("variants", []):
                    fare = str((variant.get("conditions") or {}).get("fare_family", "")).casefold()
                    if fare and (index := preceding.rfind(fare)) >= 0:
                        fare_hits.append((index, len(fare), fare, variant))
            if not fare_hits:
                return [variant for offer in selected_offers for variant in offer.get("variants", [])]
            last_index = max(hit[0] for hit in fare_hits)
            selected_hits = [hit for hit in fare_hits if hit[0] == last_index]
            longest = max(hit[1] for hit in selected_hits)
            selected_fares = {hit[2] for hit in selected_hits if hit[1] == longest}
            return [
                variant
                for offer in selected_offers
                for variant in offer.get("variants", [])
                if str((variant.get("conditions") or {}).get("fare_family", "")).casefold() in selected_fares
            ]

        money_pattern = re.compile(
            r"(?P<amount>\d[\d\u00a0\u202f ]*(?:[.,]\d{1,2})?)\s*(?P<currency>₽|руб(?:лей|ля|ль)?\.?|RUB|€|EUR|\$|USD)",
            re.IGNORECASE,
        )
        for match in money_pattern.finditer(answer):
            amount_text = re.sub(r"[\u00a0\u202f ]", "", match.group("amount")).replace(",", ".")
            try:
                claimed = Decimal(amount_text)
            except InvalidOperation:
                issues.append(f"unreadable price claim: {match.group(0)}")
                continue
            currency = match.group("currency").casefold()
            currency = "rub" if currency in {"₽", "rub", "руб", "рублей", "рубля", "рубль", "руб."} else currency
            supported = False
            selected_offers = allowed_offers(match.start())
            selected_variants = variants_for_position(match.start())
            for offer in selected_offers:
                offer_variants = offer.get("variants", [])
                offer_selected_variants = [variant for variant in selected_variants if variant in offer_variants]
                prices = []
                if not offer_variants or len(offer_selected_variants) == len(offer_variants):
                    prices.append(offer.get("price", {}))
                prices.extend(variant.get("price", {}) for variant in offer_selected_variants)
                for price in prices:
                    source_currency = str(price.get("currency", "")).casefold()
                    if currency == "rub" and source_currency != "rub":
                        continue
                    if currency != "rub" and currency not in source_currency:
                        continue
                    try:
                        original = Decimal(str(price.get("amount")))
                    except (InvalidOperation, TypeError):
                        continue
                    if claimed == original or (claimed == original.quantize(Decimal("1")) and abs(claimed - original) < Decimal("0.5")):
                        supported = True
                        break
                if supported:
                    break
            if not supported:
                issues.append(f"price not present for the stated offer: {match.group(0)}")

        for match in re.finditer(r"(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d(?!\d)", answer):
            selected_offers = allowed_offers(match.start())
            source_times = {
                value[11:16]
                for offer in selected_offers
                for value in [offer.get("departure_at"), offer.get("arrival_at"), offer.get("return_departure_at"), offer.get("return_arrival_at")]
                if isinstance(value, str) and len(value) >= 16
            }
            source_times.update(
                segment[key][11:16]
                for offer in selected_offers
                for leg in offer.get("legs", [])
                for segment in leg.get("segments", [])
                for key in ("departure_at", "arrival_at")
                if isinstance(segment.get(key), str) and len(segment[key]) >= 16
            )
            if match.group(0) not in source_times:
                issues.append(f"time not present in Tutu result: {match.group(0)}")

        for match in re.finditer(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}[.]\d{1,2}[.]\d{4})\b", answer):
            value = match.group(0)
            iso = value if len(value) == 10 and value[4] == "-" else None
            if iso is None:
                day, month, year = value.split(".")
                iso = f"{year}-{int(month):02d}-{int(day):02d}"
            source_dates = {
                value[:10]
                for offer in allowed_offers(match.start())
                for value in [offer.get("departure_at"), offer.get("arrival_at"), offer.get("return_departure_at"), offer.get("return_arrival_at")]
                if isinstance(value, str) and len(value) >= 10
            }
            if iso not in source_dates:
                issues.append(f"date not present in Tutu result: {value}")

        for match in re.finditer(r"\b(\d+(?:[.,]\d+)?)\s*(?:кг|kg)\b", answer, re.I):
            try:
                value = int(Decimal(match.group(1).replace(",", ".")))
            except (InvalidOperation, ValueError):
                issues.append(f"unreadable baggage quantity: {match.group(0)}")
                continue
            allowed: set[int] = set()
            for variant in variants_for_position(match.start()):
                conditions = variant.get("conditions") or {}
                for key in ("baggage", "cabin_baggage"):
                    quantity = (conditions.get(key) or {}).get("kg")
                    if isinstance(quantity, (int, float)):
                        allowed.add(int(quantity))
            if value not in allowed:
                issues.append(f"baggage quantity is not confirmed for the stated offer: {match.group(0)}")

        cabin_baggage_pattern = re.compile(
            r"(?:ручн\w*\s+клад\w*|cabin\s+baggage)"
            r"[^.!?\n]{0,100}?\b(?P<quantity>\d+(?:[.,]\d+)?)\s*(?:кг|kg)\b",
            re.IGNORECASE,
        )
        for match in cabin_baggage_pattern.finditer(answer):
            sentence_start = max(
                (answer.rfind(marker, 0, match.start()) for marker in ".!?\n"),
                default=-1,
            ) + 1
            sentence_end = min(
                (index for marker in ".!?\n" if (index := answer.find(marker, match.start())) >= 0),
                default=len(answer),
            )
            sentence = answer[sentence_start:sentence_end].casefold()
            if re.search(r"\b(?:не\s+(?:указан|сообщ[её]н|подтвержд[её]н)|нет\s+данных)\b", sentence):
                continue
            try:
                claimed = int(Decimal(match.group("quantity").replace(",", ".")))
            except (InvalidOperation, ValueError):
                issues.append(f"unreadable cabin baggage weight: {match.group('quantity')}")
                continue
            confirmed = {
                int(quantity)
                for variant in variants_for_position(match.start())
                for quantity in [(variant.get("conditions") or {}).get("cabin_baggage", {}).get("kg")]
                if isinstance(quantity, (int, float))
            }
            if claimed not in confirmed:
                issues.append(
                    f"cabin baggage weight is not confirmed for the stated offer: {match.group('quantity')} kg"
                )

        for match in re.finditer(r"\b(\d+)\s*(?:минут\w*|мин\.?|час\w*|ч\.?)\b", answer, re.I):
            number = int(match.group(1))
            unit = match.group(0)[len(match.group(1)):].strip().casefold()
            minutes = number * 60 if unit.startswith(("час", "ч")) else number
            sentence_start = max(
                (answer.rfind(marker, 0, match.start()) for marker in ".!?;\n"),
                default=-1,
            ) + 1
            context = answer[max(sentence_start, match.start() - 100):match.start()].casefold()
            if not re.search(
                r"\b(?:в пути|длится|длительность|продолжительность|перел[её]т|пол[её]т|рейс занимает|время пол[её]та|duration|flight(?: time)?|takes)\b",
                context,
            ):
                continue
            source_durations = {
                int(value)
                for offer in allowed_offers(match.start())
                for value in [offer.get("duration_min", 0)]
                if value
            }
            source_durations.update(
                int(value)
                for offer in allowed_offers(match.start())
                for leg in offer.get("legs", [])
                for value in [leg.get("duration_min", 0)]
                if value
            )
            source_durations.update(
                int(value)
                for offer in allowed_offers(match.start())
                for leg in offer.get("legs", [])
                for segment in leg.get("segments", [])
                for value in [segment.get("duration_min", 0)]
                if value
            )
            if minutes not in source_durations and number not in source_durations:
                issues.append(f"duration not present in Tutu result: {match.group(0)}")

        fare_pattern = re.compile(
            r"(?i:\bтариф(?:ы|а|ом|е)?)\s+(?:[«\"“](?P<quoted>[^»\"”]+)[»\"”]|(?P<plain>[A-ZА-ЯЁ][\w]*(?:\s+[A-ZА-ЯЁ][\w]*){0,2})(?!-класс(?:а)?))"
        )
        for match in fare_pattern.finditer(answer):
            candidate = match.group("quoted") or match.group("plain") or ""
            candidate = re.sub(r"\s+(?:за|от|стоимостью)\b.*$", "", candidate, flags=re.I)
            candidate = candidate.strip(" \t—–- ").casefold()
            allowed_fares = {
                str((variant.get("conditions") or {}).get("fare_family", "")).casefold()
                for offer in allowed_offers(match.start())
                for variant in offer.get("variants", [])
                if (variant.get("conditions") or {}).get("fare_family")
            }
            if candidate and not any(candidate == fare or fare in candidate for fare in allowed_fares):
                issues.append(f"fare name not present in Tutu result: {candidate}")

        for match in re.finditer(r"\(([A-Z]{3})\)", answer):
            airport_codes = {
                code
                for offer in allowed_offers(match.start())
                for leg in offer.get("legs", [])
                for place in (str(leg.get("from", "")), str(leg.get("to", "")))
                for code in re.findall(r"\b[A-Z]{3}\b", place)
            }
            if match.group(1) not in airport_codes:
                issues.append(f"airport code not present in Tutu result: {match.group(1)}")

        return issues

    def evaluate_dimension(self, dimension: str, evidence: dict[str, Any], rules: dict[str, Any]) -> str:
        return str(self.evaluate_dimension_diagnostic(dimension, evidence, rules)["status"])

    def evaluate_dimension_diagnostic(
        self,
        dimension: str,
        evidence: dict[str, Any],
        rules: dict[str, Any],
    ) -> dict[str, Any]:
        if dimension == "outcome":
            fixture = evidence.get("recorded_tutu_result")
            answer = evidence.get("final_answer")
            if not isinstance(fixture, dict) or not isinstance(answer, str) or not answer.strip():
                return {"status": "ERROR", "reason": "recorded Tutu result or final answer missing"}
            try:
                issues = self._outcome_issues(answer, fixture)
            except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
                return {"status": "ERROR", "reason": f"recorded-result evaluation error: {type(exc).__name__}: {exc}"}
            if issues:
                return {"status": "FAIL", "reason": "; ".join(issues[:5])}
            judge = evidence.get("semantic_judge")
            if not isinstance(judge, dict):
                return {"status": "ERROR", "reason": "semantic claim-level judge evidence missing"}
            if judge.get("status") != "PASS":
                return {
                    "status": "FAIL" if judge.get("status") == "FAIL" else "ERROR",
                    "reason": str(judge.get("reason") or "semantic claim-level judge did not pass"),
                }
            return {"status": "PASS", "reason": None}

        if dimension == "trajectory":
            forbidden_tools = set(rules.get("forbidden_tool_names", []))
            tool_names = set(evidence.get("tool_names", []))
            if forbidden_tools.intersection(tool_names):
                return {"status": "FAIL", "reason": "forbidden alternate search tool used"}
            commands = [str(value) for value in evidence.get("terminal_commands", [])]
            for pattern in rules.get("forbidden_command_patterns", []):
                if any(re.search(pattern, command, re.IGNORECASE) for command in commands):
                    return {"status": "FAIL", "reason": f"forbidden alternate transport command matched: {pattern}"}
            if not any(rules.get("required_skill_cli", "tutu_search_flights.py") in command for command in commands):
                return {"status": "FAIL", "reason": "production tutu-search-flights CLI was not invoked"}
            expected_tool = str(rules.get("required_mcp_tool", "search_avia"))
            calls = [
                item for item in evidence.get("mcp_boundary_requests", [])
                if item.get("jsonrpc_method") == "tools/call"
                and item.get("replay_status") == "fixture-served"
            ]
            if len(calls) != 1:
                return {"status": "FAIL", "reason": f"expected one successful recorded SDK search, got {len(calls)}"}
            call = calls[0]
            if call.get("host") != "mcp.tutu.ru" or call.get("path") != "/mcp" or call.get("http_method") != "POST":
                return {"status": "FAIL", "reason": "recorded boundary was not the production Tutu MCP endpoint"}
            if call.get("tool_name") != expected_tool:
                return {"status": "FAIL", "reason": "recorded SDK call used the wrong MCP tool"}
            expected_arguments = evidence.get("requested_search_arguments")
            if call.get("arguments") != expected_arguments or evidence.get("actual_search_arguments") != expected_arguments:
                return {"status": "FAIL", "reason": "recorded MCP search arguments do not match the requested search"}
            successful_cli = [
                item for item in evidence.get("terminal_invocations", [])
                if "tutu_search_flights.py" in item.get("command", "") and item.get("success")
            ]
            if not successful_cli:
                return {"status": "FAIL", "reason": "production skill CLI did not return a successful result"}
            final_index = evidence.get("final_event_index")
            if final_index is not None and not any(
                item.get("result_index") is not None and item["result_index"] < final_index
                for item in successful_cli
            ):
                return {"status": "FAIL", "reason": "final answer was not delivered after the successful Tutu search"}
            if evidence.get("blocked_tutu_egress_attempts"):
                return {"status": "FAIL", "reason": "attempted non-recorded access to live Tutu"}
            return {"status": "PASS", "reason": None}

        if dimension == "privacy":
            return {"status": "UNDEFINED", "reason": "privacy is outside this scenario's evaluation scope"}
        return {"status": "UNDEFINED", "reason": "unsupported evaluation dimension"}

    def evaluation_provenance(
        self,
        evidence: dict[str, Any],
        rules: dict[str, Any],
    ) -> dict[str, Any]:
        source = Path(__file__).read_bytes()
        fixture_sha = str(evidence.get("recorded_tutu_result_sha256", ""))
        identity = hashlib.sha256(source + fixture_sha.encode("utf-8")).hexdigest()
        return {
            "evaluator": self.name,
            "identity_sha256": identity,
            "recorded_fixture_sha256": fixture_sha,
            "rules": rules,
        }

    def write_final_report(self, batch: dict[str, Any], case: dict[str, Any], output_dir: Path) -> Path:
        return write_report(batch, case, output_dir)


def _redact(value: str) -> str:
    patterns = (
        (r"(?i)(authorization\s*[:=]\s*bearer\s+)[A-Za-z0-9._~+/-]+=*", r"\1[REDACTED]"),
        (r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|password)(\s*[:=]\s*)[^\s,;]+", r"\1\2[REDACTED]"),
        (r"\bsk-[A-Za-z0-9_-]{12,}\b", "[REDACTED]"),
    )
    result = value
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result)
    return result
