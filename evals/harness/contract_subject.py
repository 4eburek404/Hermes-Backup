from __future__ import annotations

from pathlib import Path
from typing import Any

from .core import Harness, RunSpec


class _ContractConsumer:
    def __init__(self, name: str) -> None:
        self.name = name

    def prepare(self, spec: RunSpec, run_dir: Path, case: dict[str, Any]) -> dict[str, Any]:
        fixture = run_dir / "fixture"
        fixture.mkdir()
        for name, content in case.get("fixture_files", {}).items():
            target = fixture / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return {
            "fixture": fixture,
            "actual_fixture_version": case.get("actual_fixture_version", case["fixture_version"]),
        }

    def execute(
        self,
        spec: RunSpec,
        run_dir: Path,
        prepared: dict[str, Any],
        case: dict[str, Any],
    ) -> dict[str, Any]:
        fixture: Path = prepared["fixture"]
        before = self._snapshot(fixture)
        behavior = case["behaviors"][spec.scenario]
        execution = behavior.get("execution", "completed")
        if execution == "runtime_failure":
            raise RuntimeError("synthetic runtime failure")
        for name, content in behavior.get("mutate_fixture", {}).items():
            target = fixture / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        after = self._snapshot(fixture)
        return {
            "execution_status": "COMPLETED",
            "fixture_before": before,
            "fixture_after": after,
            "mutation_evidence": before != after,
            "artifact": behavior.get("artifact"),
            "tool_calls": list(behavior.get("tool_calls", [])),
            "final_answer": behavior.get("final_answer", ""),
            "metrics": behavior.get("metrics", {}),
        }

    def evaluate_dimension(
        self,
        dimension: str,
        evidence: dict[str, Any],
        rules: dict[str, Any],
    ) -> str:
        if rules.get("force_evaluator_error"):
            raise ValueError("synthetic evaluator failure")
        if dimension == "outcome":
            expected = rules.get("artifact_status")
            actual = (evidence.get("artifact") or {}).get("status")
            return "PASS" if expected is None or actual == expected else "FAIL"
        if dimension == "trajectory":
            calls = list(evidence.get("tool_calls", []))
            required = rules.get("required_tools", [])
            forbidden = rules.get("forbidden_tools", [])
            return (
                "PASS"
                if all(tool in calls for tool in required)
                and not any(tool in calls for tool in forbidden)
                else "FAIL"
            )
        if dimension == "privacy":
            text = evidence.get("final_answer", "")
            forbidden = rules.get("forbidden_markers", [])
            return "FAIL" if any(marker in text for marker in forbidden) else "PASS"
        return "UNDEFINED"

    @staticmethod
    def _snapshot(root: Path) -> dict[str, str]:
        return {
            str(path.relative_to(root)): path.read_text(encoding="utf-8")
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }


class ContractSubject:
    def __init__(self) -> None:
        self._last_harness: Harness | None = None

    def run_case(self, case: dict[str, Any], output_dir: Path) -> dict[str, Any]:
        consumer = _ContractConsumer(case.get("consumer", "contract-consumer"))
        harness = Harness(consumer)
        self._last_harness = harness
        return harness.run(case, output_dir)

    def reevaluate(self, evidence_path: str | Path, rules: dict[str, Any]) -> dict[str, Any]:
        if self._last_harness is None:
            self._last_harness = Harness(_ContractConsumer("contract-consumer"))
        return self._last_harness.reevaluate(Path(evidence_path), rules)
