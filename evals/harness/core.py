from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


ORCHESTRATOR_CONTRACT_VERSION = "1"
DIMENSIONS = ("outcome", "trajectory", "privacy")


@dataclass(frozen=True)
class RunSpec:
    scenario: str
    model: str
    provider: str
    skill_version: str
    repeat: int
    fixture_version: str
    prompt_version: str
    runtime_version: str
    mode: str

    @property
    def run_id(self) -> str:
        safe = [
            self.scenario,
            self.model,
            self.provider,
            self.skill_version,
            f"r{self.repeat}",
        ]
        return "--".join(part.replace("/", "_").replace(" ", "_") for part in safe)


class Consumer(Protocol):
    name: str

    def prepare(self, spec: RunSpec, run_dir: Path, case: dict[str, Any]) -> dict[str, Any]: ...

    def execute(
        self,
        spec: RunSpec,
        run_dir: Path,
        prepared: dict[str, Any],
        case: dict[str, Any],
    ) -> dict[str, Any]: ...

    def evaluate_dimension(
        self,
        dimension: str,
        evidence: dict[str, Any],
        rules: dict[str, Any],
    ) -> str: ...


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_matrix(case: dict[str, Any]) -> list[RunSpec]:
    specs: list[RunSpec] = []
    scenario_metadata = case.get("scenario_metadata", {})
    for skill_version in case["skill_versions"]:
        for scenario in case["scenarios"]:
            scenario_meta = scenario_metadata.get(scenario, {})
            fixture_version = scenario_meta.get("fixture_version", case["fixture_version"])
            prompt_version = scenario_meta.get("prompt_version", case["prompt_version"])
            for model_entry in case["models"]:
                for repeat in range(1, int(case["repeats"]) + 1):
                    specs.append(
                        RunSpec(
                            scenario=scenario,
                            model=model_entry["model"],
                            provider=model_entry["provider"],
                            skill_version=skill_version,
                            repeat=repeat,
                            fixture_version=fixture_version,
                            prompt_version=prompt_version,
                            runtime_version=case["runtime_version"],
                            mode=case["mode"],
                        )
                    )
    return specs


def evaluate_dimensions(
    consumer: Consumer,
    evidence: dict[str, Any],
    rules: dict[str, Any],
) -> dict[str, str]:
    score: dict[str, str] = {}
    for dimension in DIMENSIONS:
        try:
            value = consumer.evaluate_dimension(dimension, evidence, rules.get(dimension, {}))
        except Exception:
            value = "ERROR"
        if value not in {"PASS", "FAIL", "ERROR", "UNDEFINED"}:
            value = "ERROR"
        score[dimension] = value
    return score


def _comparison(runs: list[dict[str, Any]]) -> dict[str, Any]:
    versions = sorted({run["skill_version"] for run in runs})
    retained = {
        version: [run["evidence_path"] for run in runs if run["skill_version"] == version]
        for version in versions
    }
    if len(versions) < 2:
        return {
            "controlled": True,
            "changed_material_conditions": [],
            "retained_evidence_by_version": retained,
        }

    keys = (
        "scenario",
        "model",
        "provider",
        "repeat",
        "fixture_version",
        "prompt_version",
        "runtime_version",
        "mode",
    )
    groups: dict[tuple[Any, ...], set[str]] = {}
    for run in runs:
        signature = tuple(run[key] for key in keys)
        groups.setdefault(signature, set()).add(run["skill_version"])
    controlled = (
        bool(groups)
        and all(run.get("comparable", False) for run in runs)
        and all(values == set(versions) for values in groups.values())
    )
    return {
        "controlled": controlled,
        "changed_material_conditions": ["skill_version"] if controlled else ["multiple_or_unknown"],
        "retained_evidence_by_version": retained,
    }


class Harness:
    def __init__(self, consumer: Consumer) -> None:
        self.consumer = consumer
        self.agent_execution_count = 0

    def run(self, case: dict[str, Any], output_dir: Path) -> dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)
        specs = build_matrix(case)
        expected_ids = [spec.run_id for spec in specs]
        runs: list[dict[str, Any]] = []

        for spec in specs:
            run_dir = output_dir / spec.run_id
            run_dir.mkdir(parents=True, exist_ok=False)
            run_record = self._run_one(spec, case, run_dir)
            runs.append(run_record)

        batch = {
            "consumer": self.consumer.name,
            "orchestrator_contract_version": ORCHESTRATOR_CONTRACT_VERSION,
            "expected_run_ids": expected_ids,
            "executed_run_ids": [run["run_id"] for run in runs],
            "agent_execution_count": self.agent_execution_count,
            "runs": runs,
        }
        batch["comparison"] = _comparison(runs)
        _write_json(output_dir / "batch_manifest.json", batch)
        return batch

    def _run_one(
        self,
        spec: RunSpec,
        case: dict[str, Any],
        run_dir: Path,
    ) -> dict[str, Any]:
        base_record = {
            "run_id": spec.run_id,
            "scenario": spec.scenario,
            "model": spec.model,
            "provider": spec.provider,
            "skill_version": spec.skill_version,
            "repeat": spec.repeat,
            "fixture_version": spec.fixture_version,
            "prompt_version": spec.prompt_version,
            "runtime_version": spec.runtime_version,
            "mode": spec.mode,
            "comparable": True,
            "agent_started": False,
        }

        try:
            prepared = self.consumer.prepare(spec, run_dir, case)
        except Exception as exc:
            evidence = {
                **base_record,
                "execution_status": "SETUP_FAILURE",
                "comparable": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
            return self._persist(run_dir, evidence, {d: "UNDEFINED" for d in DIMENSIONS})

        actual_fixture_version = prepared.get("actual_fixture_version", spec.fixture_version)
        if actual_fixture_version != spec.fixture_version:
            evidence = {
                **base_record,
                "actual_fixture_version": actual_fixture_version,
                "execution_status": "FIXTURE_FAILURE",
                "comparable": False,
            }
            return self._persist(run_dir, evidence, {d: "UNDEFINED" for d in DIMENSIONS})

        try:
            self.agent_execution_count += 1
            evidence = self.consumer.execute(spec, run_dir, prepared, case)
            evidence = {**base_record, **evidence, "agent_started": True}
        except Exception as exc:
            evidence = {
                **base_record,
                "execution_status": "RUNTIME_FAILURE",
                "agent_started": True,
                "error": f"{type(exc).__name__}: {exc}",
            }

        rules = case.get("rules", {}).get(spec.scenario, {})
        if evidence.get("execution_status") == "COMPLETED":
            score = evaluate_dimensions(self.consumer, evidence, rules)
        else:
            score = {d: "UNDEFINED" for d in DIMENSIONS}
        evidence["agent_execution_count"] = self.agent_execution_count
        return self._persist(run_dir, evidence, score)

    def _persist(
        self,
        run_dir: Path,
        evidence: dict[str, Any],
        score: dict[str, str],
    ) -> dict[str, Any]:
        evidence_path = run_dir / "evidence.json"
        score_path = run_dir / "score.json"
        _write_json(evidence_path, evidence)
        _write_json(score_path, {"score": score})
        return {
            **evidence,
            "evidence_id": evidence["run_id"],
            "evidence_path": str(evidence_path),
            "score_path": str(score_path),
            "score": score,
        }

    def reevaluate(self, evidence_path: Path, rules: dict[str, Any]) -> dict[str, Any]:
        evidence = _read_json(evidence_path)
        score = evaluate_dimensions(self.consumer, evidence, rules)
        return {
            "score": score,
            "agent_execution_count": evidence.get("agent_execution_count", self.agent_execution_count),
        }
