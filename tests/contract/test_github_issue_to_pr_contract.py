#!/usr/bin/env python3
"""Executable target contract for the github-issue-to-pr orchestrator.

This is intentionally a small checker, not a parser or workflow framework.  It
checks public orchestration boundaries in the canonical skill and its facade.
The current snapshot is expected to be RED: existing useful ownership signals
should pass while known ownership leakage and duplication should fail.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Check:
    contract: str
    name: str
    passed: bool
    evidence: str
    target: str


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold())


def contains(text: str, *terms: str) -> bool:
    value = normalized(text)
    return all(term.casefold() in value for term in terms)


def ordered(text: str, *terms: str) -> bool:
    value = normalized(text)
    positions = [value.find(term.casefold()) for term in terms]
    return all(pos >= 0 for pos in positions) and positions == sorted(positions)


def check(
    contract: str,
    name: str,
    passed: bool,
    evidence: str,
    target: str,
) -> Check:
    return Check(contract, name, passed, evidence, target)


def build_checks(repo: Path) -> list[Check]:
    canonical_path = repo / "hermes/skills/github/github-issue-to-pr/SKILL.md"
    facade_path = repo / "hermes/skills/software-development/github/references/issue-to-pr.md"
    canonical = canonical_path.read_text(encoding="utf-8")
    facade = facade_path.read_text(encoding="utf-8")
    text = normalized(canonical)
    facade_text = normalized(facade)

    checks: list[Check] = []

    # A. Live-state ownership: the orchestrator gathers state, but does not
    # silently decide stale/resolved/duplicate disposition itself.
    checks += [
        check("A", "issue body and full thread", contains(text, "body and full thread"),
              "requires body plus full-thread read", "retain issue body and complete thread"),
        check("A", "repository instructions", contains(text, "repository instructions"),
              "requires repository instruction read", "retain repository instructions"),
        check("A", "current default branch", contains(text, "current default branch"),
              "requires default-branch premise check", "retain current default branch"),
        check("A", "existing and duplicate PR work", contains(text, "existing and duplicate work"),
              "requires existing/duplicate work sweep", "retain existing and duplicate PR state"),
        check("A", "recent commits", contains(text, "recent commit"),
              "requires recent-commit check", "retain recent commits"),
        check("A", "stale/resolved/duplicate disposition boundary",
              contains(text, "stale", "disposition") and contains(text, "resolved", "disposition"),
              "requires explicit disposition state without making the orchestrator owner",
              "preserve stale/resolved/duplicate disposition for downstream scope"),
    ]

    # B. SDD owns the target specification; issue-to-PR only hands off.
    checks += [
        check("B", "SDD owns target specification",
              contains(text, "spec-driven-development", "target specification"),
              "requires explicit SDD target-spec owner", "handoff target specification to SDD"),
        check("B", "no alternative acceptance procedure",
              not contains(text, "define acceptance and risk")
              and not contains(text, "list acceptance criteria"),
              "rejects a second acceptance-definition procedure", "route acceptance contract to SDD"),
    ]

    # C. Debugging may receive an observed mismatch, but owns diagnosis.
    checks += [
        check("C", "systematic-debugging handoff",
              "systematic-debugging" in text,
              "requires debugging owner reference", "handoff bug diagnosis to systematic-debugging"),
        check("C", "no root-cause completion ownership",
              not re.search(r"root cause.{0,80}demonstrated", text),
              "rejects orchestrator completion criterion for root cause", "pass mismatch observed / cause unknown"),
        check("C", "no local data-flow tracing procedure",
              "trace the reported path" not in text,
              "rejects orchestrator-owned diagnostic tracing", "leave data-flow tracing to debugging"),
        check("C", "no local hypothesis/instrumentation procedure",
              "hypothesis" not in text and "instrumentation" not in text,
              "rejects copied debugging procedure", "leave hypothesis testing and instrumentation to debugging"),
    ]

    # D. TDD owns right-size selection and its RED/GREEN/regression mechanics.
    checks += [
        check("D", "test-driven-development handoff",
              "test-driven-development" in text,
              "requires TDD owner reference", "handoff implementation verification to TDD"),
        check("D", "TDD right-size skip boundary",
              contains(text, "right-size", "skip") and contains(text, "mechanical", "trivial"),
              "requires explicit proportional TDD skip contract", "allow TDD skip without ceremony"),
        check("D", "no unconditional tests-first rule",
              "add regression tests first" not in text,
              "rejects mandatory regression-test-first wording", "let TDD choose regression representation"),
        check("D", "no unconditional sabotage procedure",
              "sabotage run" not in text,
              "rejects orchestrator-owned revert-to-red procedure", "let TDD own regression proof"),
        check("D", "RED/GREEN/regression ownership is delegated",
              contains(text, "tdd", "red", "green", "regression")
              and "add regression tests first" not in text,
              "requires explicit TDD ownership rather than copied mechanics", "delegate RED/GREEN/regression to TDD"),
    ]

    # E. Ponytail is an implementation-shape constraint between TDD phases.
    checks += [
        check("E", "Ponytail implementation constraints",
              contains(text, "ponytail", "implementation", "constraints"),
              "requires Ponytail as an owner", "apply Ponytail constraints to implementation shape"),
        check("E", "engaged-TDD composition order",
              ordered(text, "spec-driven-development", "systematic-debugging",
                     "test-driven-development", "ponytail", "test-driven-development"),
              "requires SDD -> debugging -> TDD -> Ponytail -> TDD", "preserve existing owner boundaries"),
        check("E", "TDD skip still applies Ponytail constraints",
              contains(text, "skip", "ponytail") and contains(text, "without", "ceremony"),
              "requires no artificial ceremony while retaining implementation constraints",
              "keep Ponytail constraints on TDD-skip implementations"),
    ]

    # F. Scope is derived from debugging and target/implementation owners, not
    # a blanket class-fix rule in the orchestrator.
    checks += [
        check("F", "no unconditional whole-class fix",
              "fix the class" not in text and "whole class" not in text,
              "rejects blanket class-level scope", "derive sibling/class scope from debugging and SDD/Ponytail"),
        check("F", "sibling findings feed scoped completion",
              contains(text, "sibling", "systematic-debugging", "scope"),
              "requires sibling findings to be downstream scope input", "allow SDD/Ponytail to define complete scope"),
    ]

    # G. Review is owned by the existing runtime review skill.
    checks += [
        check("G", "github-code-review owner",
              "github-code-review" in text,
              "requires existing review owner", "handoff review to github-code-review"),
        check("G", "no requesting-code-review handoff",
              "requesting-code-review" not in text,
              "rejects unavailable/obsolete review owner", "remove mandatory requesting-code-review handoff"),
    ]

    # H. Delivery mechanics belong to github-pr-workflow.
    checks += [
        check("H", "github-pr-workflow owner",
              "github-pr-workflow" in text,
              "requires existing delivery owner", "initiate and receive delivery state"),
        check("H", "no alternative PR lifecycle",
              not contains(text, "push and open the pr")
              and "pr exists" not in text,
              "rejects local push/open/PR completion lifecycle", "delegate branch/commit/push/PR/CI mechanics"),
    ]

    # I. CI failures have an explicit return path; infrastructure remains a
    # delivery-state problem.
    checks += [
        check("I", "code-caused CI return path",
              ordered(text, "delivery state", "development pipeline", "review", "delivery"),
              "requires delivery -> development -> review -> delivery", "return code-caused CI failures through owners"),
        check("I", "infrastructure remains delivery-state problem",
              contains(text, "infrastructure", "delivery state"),
              "requires infrastructure/baseline distinction at delivery boundary",
              "keep infrastructure/baseline failures in delivery state"),
    ]

    # J. Mechanical/trivial issues use proportional SDD and may skip TDD.
    checks += [
        check("J", "proportional SDD for mechanical/trivial work",
              contains(text, "proportional", "spec-driven-development", "mechanical"),
              "requires proportional SDD branch", "use proportional SDD for mechanical/trivial issues"),
        check("J", "debugging optional for mechanical/trivial work",
              contains(text, "debugging", "not required") or contains(text, "debugging", "optional"),
              "requires debugging boundary to be optional here", "do not force debugging on non-bugs"),
        check("J", "TDD may skip or adopt existing check",
              contains(text, "skip", "existing check"),
              "requires TDD skip/adopt-existing-check option", "let TDD choose right-size verification"),
        check("J", "mechanical work does not require sabotage",
              not contains(text, "mechanical", "sabotage"),
              "rejects sabotage as a mechanical-work requirement", "no artificial RED/GREEN ceremony"),
        check("J", "Ponytail keeps minimal implementation scope",
              contains(text, "ponytail", "minimal", "scope"),
              "requires minimal implementation-shape constraint", "apply Ponytail constraints even when TDD skips"),
    ]

    # K. The facade is a routing/handoff reference, not a second procedure.
    checks += [
        check("K", "facade has no independent procedure",
              "## procedure" not in facade_text,
              "rejects a second full implementation procedure", "make facade routing/handoff-only"),
        check("K", "facade routes to canonical skill",
              contains(facade_text, "github-issue-to-pr", "canonical"),
              "requires explicit canonical source route", "point facade at canonical github-issue-to-pr"),
        check("K", "facade is not a duplicated implementation",
              not contains(facade_text, "add regression tests first")
              and not contains(facade_text, "sabotage run"),
              "rejects copied orchestration mechanics", "remove duplicated lifecycle/procedure from facade"),
    ]

    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()

    try:
        checks = build_checks(args.repo)
    except Exception as exc:  # pragma: no cover - makes missing baseline explicit
        print(f"SPEC ERROR: {exc}")
        return 2

    contracts: dict[str, list[Check]] = {}
    for item in checks:
        contracts.setdefault(item.contract, []).append(item)

    for contract, items in contracts.items():
        status = "PASS" if all(item.passed for item in items) else "FAIL"
        print(f"{contract}: {status}")
        for item in items:
            marker = "PASS" if item.passed else "FAIL"
            print(f"  [{marker}] {item.name}: {item.evidence}")
            if not item.passed:
                print(f"         target: {item.target}")

    passed = sum(item.passed for item in checks)
    failed = len(checks) - passed
    print(f"SUMMARY passed={passed} failed={failed} total={len(checks)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
