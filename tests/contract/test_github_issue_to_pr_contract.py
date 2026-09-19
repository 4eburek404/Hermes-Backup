#!/usr/bin/env python3
"""Small executable target contract for the github-issue-to-pr orchestrator.

The checker deliberately stays source-level because the target is a declarative
skill.  It uses bounded Markdown paragraphs as evidence groups, owner relations,
and explicit transition relations; it is not a Markdown parser or workflow
framework.
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


def blocks(text: str) -> list[str]:
    """Return bounded prose/list blocks without depending on heading names."""
    return [normalized(part) for part in re.split(r"\n\s*\n", text) if part.strip()]


def matches(block: str, pattern: str) -> bool:
    return re.search(pattern, block, flags=re.IGNORECASE) is not None


def negated_before(block: str, patterns: tuple[str, ...]) -> bool:
    subject = "(?:" + "|".join(patterns) + ")"
    subject_matches = list(re.finditer(subject, block, flags=re.IGNORECASE))
    if not subject_matches:
        return False
    negation = r"\b(?:do not|don't|never|must not|not required|without)\b"
    return all(
        re.search(negation + r"[^.]{0,80}$", block[max(0, match.start() - 80):match.start()],
                  flags=re.IGNORECASE)
        is not None
        for match in subject_matches
    )


def has_block(text: str, *groups: tuple[str, ...]) -> bool:
    """True when one bounded block contains one match from every group."""
    return any(
        all(any(matches(block, pattern) for pattern in group) for group in groups)
        for block in blocks(text)
    )


def owner_relation(text: str, owner: str, role: tuple[str, ...], action: tuple[str, ...]) -> bool:
    return has_block(text, (owner,), role, action)


def ordered_transition(text: str, sequence: list[tuple[str, ...]]) -> bool:
    """Require an explicit owner chain in one block, not global token order."""
    transition = re.compile(r"(?:->|→|\bthen\b|\bbefore\b|\bafter\b|\bthrough\b|\breturn)")
    for block in blocks(text):
        if not transition.search(block):
            continue
        cursor = 0
        found = True
        for alternatives in sequence:
            positions: list[int] = []
            for pattern in alternatives:
                match = re.search(pattern, block[cursor:], flags=re.IGNORECASE)
                if match:
                    positions.append(cursor + match.start())
            if not positions:
                found = False
                break
            cursor = min(positions) + 1
        if found:
            return True
    return False


def has_unconditional_tests_first(text: str) -> bool:
    for block in blocks(text):
        test_first = (r"\bregression\s+(?:test|check)\b", r"\btests?\s+first\b",
                      r"\btests?\s+before\b", r"\btests?\s+prior\b")
        if all(any(matches(block, pattern) for pattern in group) for group in (
            test_first,
            (r"\badd\b", r"\bwrite\b", r"\bcreate\b", r"\bbegin\b", r"\bstart\b",
             r"\brequire\b", r"\bmust\b", r"\bensure\b"),
            (r"\bimplement\b", r"\bimplementation\b", r"\bfix\b"),
        )) and not negated_before(block, test_first):
            return True
    return False


def has_unconditional_sabotage(text: str) -> bool:
    for block in blocks(text):
        prior_behavior = (r"\b(?:restore|revert|reinstate|old behavior|prior implementation|pre[- ]fix)\b",)
        if all(any(matches(block, pattern) for pattern in group) for group in (
            prior_behavior,
            (r"\b(?:run|rerun|execute|replay)\b",),
            (r"\b(?:test|check|regression)\b",),
            (r"\b(?:fail|fails|failed|red)\b",),
        )) and not negated_before(block, prior_behavior):
            return True
    return False


def has_local_acceptance_procedure(text: str) -> bool:
    for block in blocks(text):
        acceptance = (r"acceptance criteria|acceptance contract|finite contract",)
        if has_block(block,
                     acceptance,
                     (r"list|define|map|enumerate|rollout|rollback|compatibility",),
                     (r"done when|procedure|step|must",)) \
                and not negated_before(block, acceptance):
            return True
    return False


def has_local_delivery_lifecycle(text: str) -> bool:
    for block in blocks(text):
        delivery_action = (r"push", r"open|create|exists")
        if has_block(block, delivery_action, (r"pr",),
                     (r"ci|done when|verify|immediately",)) \
                and not negated_before(block, delivery_action):
            return True
    return False


def has_local_diagnostic_procedure(text: str, subject: tuple[str, ...], action: tuple[str, ...]) -> bool:
    for block in blocks(text):
        if all(any(matches(block, pattern) for pattern in group) for group in (subject, action)) \
                and not negated_before(block, subject):
            return True
    return False


def has_unqualified_class_fix(text: str) -> bool:
    for block in blocks(text):
        if not matches(block, r"\bfix(?:es|ing)?\b.{0,60}\b(?:whole|entire|the)?\s*class\b"):
            continue
        if matches(block, r"\b(?:do not|don't|never|not)\b.{0,50}\bfix(?:es|ing)?\b"):
            continue
        if matches(block, r"\b(?:only when|when debugging|when scope|based on)\b"):
            continue
        return True
    return False


def facade_workflow_evidence(text: str) -> set[str]:
    concepts = {
        "live issue": (r"gh issue view", r"full thread", r"comments"),
        "duplicate sweep": (r"gh pr list", r"duplicate", r"search"),
        "premise": (r"default branch", r"reproduce", r"current code"),
        "acceptance": (r"acceptance criteria", r"finite contract", r"rollout"),
        "implementation": (r"implement", r"fix the", r"sibling"),
        "test procedure": (r"regression test", r"tests? first", r"red", r"sabotage"),
        "delivery": (r"push", r"open the pr", r"pr exists", r"ci"),
    }
    result: set[str] = set()
    for name, patterns in concepts.items():
        if any(any(matches(block, pattern) for pattern in patterns) for block in blocks(text)):
            result.add(name)
    return result


def check(contract: str, name: str, passed: bool, evidence: str, target: str) -> Check:
    return Check(contract, name, passed, evidence, target)


def build_checks(repo: Path) -> list[Check]:
    canonical_path = repo / "hermes/skills/github/github-issue-to-pr/SKILL.md"
    facade_path = repo / "hermes/skills/software-development/github/references/issue-to-pr.md"
    canonical = canonical_path.read_text(encoding="utf-8")
    facade = facade_path.read_text(encoding="utf-8")
    text = canonical

    checks: list[Check] = []

    # A. Live-state ownership: the orchestrator gathers state, but does not
    # silently decide stale/resolved/duplicate disposition itself.
    checks += [
        check("A", "issue body and full thread",
              has_block(text, (r"issue|ticket",), (r"body|description|filed issue",),
                        (r"comment|thread|comments",),
                        (r"read|inspect|view|fetch|full|complete",)),
              "requires issue identity, body/thread state, and read evidence in one block",
              "retain issue body and complete thread"),
        check("A", "repository instructions",
              has_block(text, (r"repository instructions|agents\.md|contribution docs",),
                        (r"read|inspect|follow|load|instructions",)),
              "requires repository-instruction source evidence",
              "retain repository instructions"),
        check("A", "current default branch",
              has_block(text, (r"default branch",), (r"reproduce|current code|current state",)),
              "requires default-branch premise evidence",
              "retain current default branch"),
        check("A", "existing and duplicate PR work",
              has_block(text, (r"duplicate|existing",), (r"search|sweep|check|list",), (r"pr",)),
              "requires PR search/sweep evidence, not a standalone duplicate word",
              "retain existing and duplicate PR state"),
        check("A", "recent commits",
              has_block(text, (r"recent commit|commit history|git history|already fixed",),
                        (r"check|inspect|read|log|history",)),
              "requires recent-history evidence",
              "retain recent commits"),
        check("A", "stale/resolved/duplicate disposition boundary",
              has_block(text, (r"stale",), (r"resolved",), (r"duplicate",),
                        (r"disposition|status|classif|scope|hand[- ]?off|pass",)),
              "requires all disposition states plus downstream handling in one evidence block",
              "preserve stale/resolved/duplicate disposition for downstream scope"),
    ]

    # B. SDD owns the target specification; issue-to-PR only hands off.
    checks += [
        check("B", "SDD owns target specification",
              owner_relation(text, r"spec[- ]driven[- ]development",
                             (r"target", r"acceptance", r"specification", r"contract"),
                             (r"own", r"owner", r"delegat", r"hand[- ]?off", r"route", r"belong", r"define", r"determin")),
              "requires SDD and target-spec role/action in one bounded evidence block",
              "handoff target specification to SDD"),
        check("B", "no alternative acceptance procedure",
              not has_local_acceptance_procedure(text),
              "rejects local acceptance-definition procedure unless explicitly assigned to SDD",
              "route acceptance contract to SDD"),
    ]

    # C. Debugging may receive an observed mismatch, but owns diagnosis.
    checks += [
        check("C", "systematic-debugging handoff",
              owner_relation(text, r"systematic[- ]debugging",
                             (r"bug", r"symptom", r"diagnos", r"root cause", r"mismatch"),
                             (r"load", r"use", r"when", r"hand[- ]?off", r"delegat", r"route")),
              "requires debugging owner relation rather than a bare related-skill token",
              "handoff bug diagnosis to systematic-debugging"),
        check("C", "no root-cause completion ownership",
              not has_local_diagnostic_procedure(
                  text, (r"root cause",),
                  (r"demonstrat", r"confirm", r"complete", r"done when", r"understand", r"identify"),
              ),
              "rejects unowned root-cause completion evidence",
              "pass mismatch observed / cause unknown"),
        check("C", "no local data-flow tracing procedure",
              not has_local_diagnostic_procedure(
                  text, (r"trace",), (r"reported path|data flow|call path|boundary",)
              ),
              "rejects unowned diagnostic tracing evidence",
              "leave data-flow tracing to debugging"),
        check("C", "no local hypothesis/instrumentation procedure",
              not has_local_diagnostic_procedure(
                  text, (r"hypothes", r"instrument"),
                  (r"test", r"trace", r"gather", r"investigat", r"probe"),
              ),
              "rejects copied debugging procedure",
              "leave hypothesis testing and instrumentation to debugging"),
    ]

    # D. TDD owns right-size selection and RED/GREEN/regression mechanics.
    checks += [
        check("D", "test-driven-development handoff",
              owner_relation(text, r"test-driven-development",
                             (r"bug", r"test", r"implement", r"regression"),
                             (r"load", r"use", r"when", r"hand[- ]?off", r"delegat", r"route")),
              "requires TDD owner relation rather than a bare token",
              "handoff implementation verification to TDD"),
        check("D", "TDD right-size skip boundary",
              owner_relation(text, r"test-driven-development",
                             (r"right[- ]?size", r"skip", r"mechanical", r"trivial"),
                             (r"may", r"choose", r"decision", r"optional", r"contract", r"own")),
              "requires TDD to own proportional skip/decision evidence",
              "allow TDD skip without ceremony"),
        check("D", "no unconditional tests-first rule",
              not has_unconditional_tests_first(text),
              "rejects an unowned local tests-first implementation procedure",
              "let TDD choose regression representation"),
        check("D", "no unconditional sabotage procedure",
              not has_unconditional_sabotage(text),
              "rejects an unowned prior-behavior replay/regression procedure",
              "let TDD own regression proof"),
        check("D", "RED/GREEN/regression ownership is delegated",
              owner_relation(text, r"test-driven-development",
                             (r"red", r"green", r"regression"),
                             (r"own", r"owner", r"delegat", r"hand[- ]?off", r"responsib", r"choose"))
              and not has_unconditional_tests_first(text)
              and not has_unconditional_sabotage(text),
              "requires explicit TDD ownership and no competing local procedure",
              "delegate RED/GREEN/regression to TDD"),
    ]

    # E. Ponytail is an implementation-shape constraint between TDD phases.
    checks += [
        check("E", "Ponytail implementation constraints",
              has_block(text, (r"ponytail",),
                        (r"implementation shape|implementation",),
                        (r"constraint|minimal scope|shape",)),
              "requires Ponytail role as implementation-shape constraint",
              "apply Ponytail constraints to implementation shape"),
        check("E", "engaged-TDD composition order",
              ordered_transition(text, [
                  (r"spec[- ]driven[- ]development",),
                  (r"systematic[- ]debugging",),
                  (r"test[- ]driven[- ]development",),
                  (r"ponytail",),
                  (r"test[- ]driven[- ]development",),
              ]),
              "requires explicit SDD -> debugging -> TDD -> Ponytail -> TDD chain",
              "preserve existing owner boundaries"),
        check("E", "TDD skip still applies Ponytail constraints",
              has_block(text, (r"skip",), (r"ponytail",),
                        (r"without|no|not",), (r"ceremony|implementation|constraint|minimal",)),
              "requires skip/no-ceremony and retained Ponytail implementation constraint",
              "keep Ponytail constraints on TDD-skip implementations"),
    ]

    # F. Scope is derived from debugging and target/implementation owners, not
    # a blanket class-fix rule in the orchestrator.
    checks += [
        check("F", "no unconditional whole-class fix",
              not has_unqualified_class_fix(text),
              "rejects unqualified imperative class-level scope",
              "derive sibling/class scope from debugging and SDD/Ponytail"),
        check("F", "sibling findings feed scoped completion",
              has_block(text, (r"sibling",), (r"systematic[- ]debugging",),
                        (r"\bscope\b|scope of|complete scope|scope decision|bounded scope",)),
              "requires sibling findings plus debugging and scope evidence",
              "allow SDD/Ponytail to define complete scope"),
    ]

    # G. Review is owned by the existing runtime review skill.
    checks += [
        check("G", "github-code-review owner",
              owner_relation(text, r"github-code-review",
                             (r"review", r"diff"),
                             (r"own", r"owner", r"hand[- ]?off", r"delegat", r"use", r"route")),
              "requires review owner relation",
              "handoff review to github-code-review"),
        check("G", "no requesting-code-review handoff",
              not owner_relation(text, r"requesting-code-review",
                                 (r"review", r"diff"),
                                 (r"use", r"request", r"hand[- ]?off", r"load")),
              "rejects obsolete review-owner handoff, not unrelated mention",
              "remove mandatory requesting-code-review handoff"),
    ]

    # H. Delivery mechanics belong to github-pr-workflow.
    checks += [
        check("H", "github-pr-workflow owner",
              owner_relation(text, r"github-pr-workflow",
                             (r"pr", r"delivery", r"branch|commit|ci"),
                             (r"mechanic", r"own", r"load", r"use", r"hand[- ]?off", r"delegat", r"route")),
              "requires delivery owner relation",
              "initiate and receive delivery state"),
        check("H", "no alternative PR lifecycle",
              not has_local_delivery_lifecycle(text),
              "rejects local push/open/PR/CI completion procedure unless assigned to delivery owner",
              "delegate branch/commit/push/PR/CI mechanics"),
    ]

    # I. CI failures have an explicit return path; infrastructure remains a
    # delivery-state problem.
    checks += [
        check("I", "code-caused CI return path",
              ordered_transition(text, [
                  (r"delivery state", r"delivery"),
                  (r"development pipeline", r"implementation", r"development"),
                  (r"review",),
                  (r"delivery", r"delivery state"),
              ]),
              "requires delivery -> development -> review -> delivery transition",
              "return code-caused CI failures through owners"),
        check("I", "infrastructure remains delivery-state problem",
              has_block(text, (r"infrastructure|baseline",),
                        (r"delivery state|delivery problem",),
                        (r"failure|problem|remain|stay",)),
              "requires infrastructure/baseline failure at delivery-state boundary",
              "keep infrastructure/baseline failures in delivery state"),
    ]

    # J. Mechanical/trivial issues use proportional SDD and may skip TDD.
    checks += [
        check("J", "proportional SDD for mechanical/trivial work",
              owner_relation(text, r"spec[- ]driven[- ]development",
                             (r"proportional", r"mechanical", r"trivial"),
                             (r"route", r"choose", r"use", r"contract", r"may", r"own")),
              "requires proportional mechanical/trivial branch assigned to SDD",
              "use proportional SDD for mechanical/trivial issues"),
        check("J", "debugging optional for mechanical/trivial work",
              has_block(text, (r"debugging|systematic[- ]debugging",),
                        (r"mechanical|trivial",), (r"optional|not required|may skip|unnecessary",)),
              "requires explicit debugging boundary for non-bugs",
              "do not force debugging on non-bugs"),
        check("J", "TDD may skip or adopt existing check",
              owner_relation(text, r"test-driven-development",
                             (r"skip", r"existing check", r"existing test"),
                             (r"may", r"choose", r"adopt", r"optional", r"contract", r"own")),
              "requires TDD skip/adopt-existing-check relation",
              "let TDD choose right-size verification"),
        check("J", "mechanical work does not require sabotage",
              has_block(text, (r"mechanical|trivial",),
                        (r"sabotage|revert-to-red|prior-behavior replay",),
                        (r"not required|optional|may skip|without",)),
              "requires explicit non-requirement for mechanical sabotage",
              "no artificial RED/GREEN ceremony"),
        check("J", "Ponytail keeps minimal implementation scope",
              has_block(text, (r"ponytail",), (r"mechanical|trivial|skip",),
                        (r"minimal",), (r"scope|implementation",)),
              "requires Ponytail minimal-scope relation for the skip branch",
              "apply Ponytail constraints even when TDD skips"),
    ]

    # K. The facade is routing/handoff-only, not a second procedure.
    facade_evidence = facade_workflow_evidence(facade)
    checks += [
        check("K", "facade has no independent procedure",
              len(facade_evidence) < 4,
              f"independent workflow evidence groups={sorted(facade_evidence)}",
              "make facade routing/handoff-only"),
        check("K", "facade routes to canonical skill",
              has_block(facade,
                        (r"github-issue-to-pr",),
                        (r"canonical|route|routing|hand[- ]?off|source of truth|refer",)),
              "requires canonical path and routing/handoff relation in one block",
              "point facade at canonical github-issue-to-pr"),
        check("K", "facade is not a duplicated implementation",
              len(facade_evidence) < 3,
              f"duplicated implementation evidence groups={sorted(facade_evidence)}",
              "remove duplicated lifecycle/procedure from facade"),
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
