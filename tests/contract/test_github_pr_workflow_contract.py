#!/usr/bin/env python3
"""Executable repository contract for the github-pr-workflow delivery owner.

The target is a declarative SKILL.md.  This checker therefore audits bounded
semantic prose blocks and operational examples, not headings, line numbers, or
literal implementation text.  It intentionally leaves real Git/GitHub behavior
to a future controlled integration/agent evaluation.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


TARGET = Path("hermes/skills/github/github-pr-workflow/SKILL.md")
ROUTER = Path("hermes/skills/github/github-issue-to-pr/SKILL.md")


@dataclass(frozen=True)
class Source:
    path: Path
    text: str
    prose_blocks: tuple[str, ...]
    code_blocks: tuple[str, ...]
    frontmatter: str


@dataclass(frozen=True)
class Check:
    requirement: str
    name: str
    status: str  # PASS, FAIL, or DEFERRED
    evidence: str
    target: str = ""


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold())


def prose_blocks(text: str) -> tuple[str, ...]:
    prose = re.sub(r"```[^\n]*\n.*?```", "", text, flags=re.DOTALL)
    return tuple(normalized(part) for part in re.split(r"\n\s*\n", prose) if part.strip())


def fenced_blocks(text: str) -> tuple[str, ...]:
    return tuple(
        normalized(match.group(1))
        for match in re.finditer(r"```[^\n]*\n(.*?)```", text, flags=re.DOTALL)
    )


def load_source(repo: Path, relative: Path) -> Source | None:
    path = repo / relative
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    frontmatter = ""
    if text.startswith("---\n"):
        parts = text.split("\n---\n", 1)
        if len(parts) == 2:
            frontmatter = normalized(parts[0])
    return Source(path, text, prose_blocks(text), fenced_blocks(text), frontmatter)


def has_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def block_with_groups(source: Source, *groups: tuple[str, ...]) -> bool:
    return any(all(has_any(block, group) for group in groups) for block in source.prose_blocks)


def block_matching(source: Source, groups: tuple[tuple[str, ...], ...]) -> str | None:
    for block in source.prose_blocks:
        if all(has_any(block, group) for group in groups):
            return block
    return None


def concept_present(source: Source, patterns: tuple[str, ...]) -> bool:
    return any(has_any(block, patterns) for block in source.prose_blocks)


def negated_before(block: str, patterns: tuple[str, ...]) -> bool:
    subject = "(?:" + "|".join(patterns) + ")"
    occurrences = list(re.finditer(subject, block, flags=re.IGNORECASE))
    if not occurrences:
        return False
    negation = r"\b(?:do not|don't|does not|never|must not|not required|without)\b"
    return all(
        re.search(
            negation + r"[^.]{0,100}$",
            block[max(0, occurrence.start() - 100) : occurrence.start()],
            flags=re.IGNORECASE,
        )
        is not None
        for occurrence in occurrences
    )


def local_ci_fix_loop(source: Source) -> bool:
    """Reject the legacy delivery-owned implementation/fix loop."""
    for block in source.prose_blocks:
        if not has_any(block, (r"ci", r"check", r"workflow")):
            continue
        if not has_any(block, (r"fail", r"failure", r"failed", r"error")):
            continue
        if not has_any(block, (r"patch", r"write_file", r"implement", r"fix the code")):
            continue
        if not has_any(block, (r"commit", r"push")):
            continue
        if has_any(block, (r"hand[- ]?off", r"delegate", r"route", r"development", r"debugging", r"review")):
            continue
        if not negated_before(block, (r"patch", r"write_file", r"implement", r"fix the code")):
            return True
    return False


def unsafe_destructive_example(source: Source) -> bool:
    code = "\n".join(source.code_blocks)
    dangerous = re.compile(r"git\s+(?:reset\s+--hard|clean\s+-[a-z]*f|branch\s+-D)\b", re.IGNORECASE)
    if not dangerous.search(code):
        return False
    safety = re.compile(r"authorized|explicit|preserve|safe|isolat|confirmed|only after|abort|never", re.IGNORECASE)
    return not safety.search(source.text)


def generic_stage_default(source: Source) -> bool:
    code = "\n".join(source.code_blocks)
    return bool(re.search(r"git\s+add\s+(?:\.|-A|--all)\b", code, flags=re.IGNORECASE))


def hardcoded_merge_method(source: Source) -> bool:
    code = "\n".join(source.code_blocks)
    return bool(re.search(r"(?:gh\s+pr\s+merge|merge_method)[^\n]{0,100}(?:--squash|['\"]squash['\"])", code, flags=re.IGNORECASE))


def hardcoded_repository_fact(source: Source, fact: str) -> bool:
    code = "\n".join(source.code_blocks)
    if fact == "main":
        return bool(re.search(r"(?:checkout|diff|--base)\s+main\b", code, flags=re.IGNORECASE))
    return bool(re.search(r"git\s+(?:push|fetch|remote\s+get-url)\s+origin\b", code, flags=re.IGNORECASE)) and not concept_present(
        source, (r"selected|discovered|resolved|target remote|when .*origin|if .*origin",)
    )


def build_checks(repo: Path) -> list[Check]:
    target = load_source(repo, TARGET)
    router = load_source(repo, ROUTER)
    router_text = router.text if router else ""
    route_ok = bool(
        re.search(r"github[- ]pr[- ]workflow", router_text, flags=re.IGNORECASE)
        and re.search(r"(?:delivery|pull request|pr|branch|commit|ci)", router_text, flags=re.IGNORECASE)
        and re.search(r"(?:owns|owner|route|hand[- ]?off|delegate|canonical)", router_text, flags=re.IGNORECASE)
    )
    target_ok = bool(
        target
        and re.search(r"name:\s*github[- ]pr[- ]workflow", target.frontmatter, flags=re.IGNORECASE)
        and block_with_groups(target, (r"delivery|pull request|pr",), (r"branch|commit|push|merge|ci",))
    )

    checks: list[Check] = [
        Check(
            "A",
            "usable delivery owner exists",
            "PASS" if route_ok and target_ok else "FAIL",
            f"route={'present' if route_ok else 'missing'}, target={'usable' if target_ok else 'missing or not delivery-capable'}",
            "resolve issue-to-pr delivery routing to a usable github-pr-workflow owner",
        )
    ]

    if target is None:
        for requirement, name in (
            ("B", "ownership boundaries"),
            ("C", "repository preflight"),
            ("D", "safe branch behavior"),
            ("E", "scoped staging and commit"),
            ("F", "push and remote verification"),
            ("G", "PR lookup/create/update"),
            ("H", "CI/check state model"),
            ("I", "CI failure handoff"),
            ("J", "merge boundary"),
            ("K", "merge confirmation and cleanup"),
            ("L", "delivery state reporting"),
        ):
            checks.append(Check(requirement, name, "DEFERRED", "target SKILL.md is absent"))
        return checks

    # B: the owner may orchestrate delivery, but specialist procedures remain
    # with their established owners.  Mentioning an owner is not duplication;
    # each boundary must express non-ownership or handoff semantics.
    boundary_domains = {
        "SDD": (r"spec[- ]driven[- ]development|requirements|target specification|target contract",),
        "debugging": (r"systematic[- ]debugging|root[- ]cause|diagnos",),
        "TDD": (r"test[- ]driven[- ]development|red|green|refactor",),
        "Ponytail": (r"ponytail|implementation shape|refactor",),
        "review": (r"github[- ]code[- ]review|code review|reviewed change",),
        "auth": (r"authentication|credential|token|github-auth|auth setup",),
        "release": (r"release|deployment|deploy",),
    }
    boundary_terms = (r"does not own|not own|outside scope|out of scope|belongs to|owned by|hand[- ]?off|delegate|separate owner|not implement",)
    missing_boundaries = [
        owner for owner, domain in boundary_domains.items()
        if not any(has_any(block, domain) and has_any(block, boundary_terms) for block in target.prose_blocks)
    ]
    checks.append(Check(
        "B", "delivery ownership boundaries",
        "PASS" if not missing_boundaries and not local_ci_fix_loop(target) else "FAIL",
        f"missing_boundaries={missing_boundaries or 'none'}; legacy_ci_fix_loop={local_ci_fix_loop(target)}",
        "delivery mechanics only; hand off SDD, debugging, implementation, review, auth, and release",
    ))

    # C: discovery and state inspection precede any mutation.
    preflight = block_matching(target, (
        (r"preflight|before mutat|before branch|before staging|before commit",),
        (r"repository|repo",),
        (r"current branch|branch",),
        (r"worktree|dirty|untracked",),
        (r"remote",),
        (r"base|default branch",),
        (r"existing change|delivery context|pr context|change context",),
    ))
    checks.append(Check(
        "C", "repository/delivery preflight",
        "PASS" if preflight and not hardcoded_repository_fact(target, "main") and not hardcoded_repository_fact(target, "origin") else "FAIL",
        f"preflight={'present' if preflight else 'missing'}; hardcoded_main={hardcoded_repository_fact(target, 'main')}; unselected_origin={hardcoded_repository_fact(target, 'origin')}",
        "inspect repository, branch, worktree, selected remote, base, and delivery context before mutation",
    ))

    # D: preserve current work; a temporary worktree is an option, not a gate.
    safe_branch = block_matching(target, (
        (r"current checkout|current worktree|worktree",),
        (r"safe|preserve|do not lose|unrelated|dirty|untracked",),
        (r"existing branch|explicit base|discovered base|selected base",),
    ))
    checkout_option = concept_present(target, (r"current checkout", r"existing checkout", r"temporary worktree", r"isolated checkout"))
    checks.append(Check(
        "D", "safe branch preparation",
        "PASS" if safe_branch and checkout_option and not unsafe_destructive_example(target) else "FAIL",
        f"safety_block={'present' if safe_branch else 'missing'}; checkout_options={'present' if checkout_option else 'missing'}; unsafe_destructive_example={unsafe_destructive_example(target)}",
        "use explicit/discovered base and preserve dirty, untracked, unrelated, and user branch state",
    ))

    # E: staging and commit are scoped and inspected, not a blanket add.
    staging = block_matching(target, (
        (r"stage|staging",),
        (r"intended|approved|scoped|specific|delivery scope|relevant path",),
        (r"inspect|review|diff --cached|staged content",),
        (r"unrelated|accidental",),
        (r"whitespace|basic validation|check",),
        (r"commit",),
    ))
    checks.append(Check(
        "E", "scoped staging and commit",
        "PASS" if staging and not generic_stage_default(target) else "FAIL",
        f"staging_contract={'present' if staging else 'missing'}; generic_git_add_default={generic_stage_default(target)}",
        "stage only delivery-approved paths, inspect staged content, validate, then commit the intended scope",
    ))

    # F: push result and authoritative remote head are separate states.
    push = block_matching(target, (
        (r"push",),
        (r"attempted|succeeded|success|rejected|failed|failure",),
        (r"remote branch|remote state|remote head",),
        (r"verify|confirmed|authoritative|observed",),
        (r"sha|commit id|head",),
    ))
    checks.append(Check(
        "F", "push and remote SHA verification",
        "PASS" if push and concept_present(target, (r"non[- ]fast[- ]forward|rejected push",)) and not concept_present(target, (r"force push.*normal|normal.*force push",)) else "FAIL",
        f"push_state_contract={'present' if push else 'missing'}; rejected_push_boundary={'present' if concept_present(target, (r'non[- ]fast[- ]forward|rejected push',)) else 'missing'}",
        "distinguish push outcome and verify local intended SHA against observed remote head without destructive force recovery",
    ))

    # G: identify an existing PR before create, and read back authoritative data.
    pr = block_matching(target, (
        (r"existing|relevant",),
        (r"pull request|\bpr\b",),
        (r"search|lookup|find",),
        (r"create",),
        (r"update|edit",),
    ))
    authoritative = block_matching(target, (
        (r"pull request|\bpr\b",),
        (r"repository",), (r"base",), (r"head",),
        (r"authoritative|explicit|provided",),
    ))
    checks.append(Check(
        "G", "PR lookup/create/update and read-back",
        "PASS" if pr and authoritative and concept_present(target, (r"issue linkage|closes #|fixes #|preserve.*issue",)) and concept_present(target, (r"read[- ]back|read back|confirm|response|metadata",)) else "FAIL",
        f"existing_vs_create_update={'present' if pr else 'missing'}; explicit_pr_context={'present' if authoritative else 'missing'}",
        "search existing relevant PR, operate on explicit repository/base/head, preserve linkage, and read back metadata",
    ))

    # H: status model is semantic, not a single green/non-green shortcut.
    check_states = all(concept_present(target, patterns) for patterns in (
        (r"pending|in[- ]progress",),
        (r"passed|satisfied|success",),
        (r"failed|failure",),
        (r"cancelled|canceled",),
        (r"skipped|neutral",),
        (r"unavailable|unknown",),
    ))
    check_context = block_matching(target, (
        (r"check|ci|status",),
        (r"current|actual|authoritative|relevant",),
        (r"head|sha|pull request|pr",),
    ))
    honest_pending = concept_present(target, (r"pending.*not failed|timeout.*not failed|not terminal.*failure|absence.*not.*success",))
    checks.append(Check(
        "H", "CI/check state model",
        "PASS" if check_states and check_context and honest_pending else "FAIL",
        f"states={check_states}; current_head_context={'present' if check_context else 'missing'}; pending_unknown_guard={honest_pending}",
        "observe current PR/head checks and distinguish pending, pass, fail, cancelled, skipped/neutral, and unavailable/unknown",
    ))

    # I: report evidence and hand off; do not own implementation repair.
    failure_evidence = block_matching(target, (
        (r"failed|failure",),
        (r"identity|name|conclusion|status",),
        (r"url|log|evidence|head sha|commit sha",),
    ))
    handoff = block_matching(target, (
        (r"failed|failure",),
        (r"development|debugging|implementation",),
        (r"hand[- ]?off|delegate|route|owner",),
        (r"review",),
    ))
    checks.append(Check(
        "I", "CI failure evidence and development handoff",
        "PASS" if failure_evidence and handoff and not local_ci_fix_loop(target) else "FAIL",
        f"failure_evidence={'present' if failure_evidence else 'missing'}; handoff={'present' if handoff else 'missing'}; self_fix_loop={local_ci_fix_loop(target)}",
        "preserve check evidence and return code-caused failures through development/debugging and fresh review",
    ))

    # J: merge is a capability gated by explicit intent and current-head checks.
    merge_boundary = block_matching(target, (
        (r"merge",),
        (r"explicit|requested|intent|caller",),
        (r"only|unless|without",),
    ))
    premerge = block_matching(target, (
        (r"before merge|pre[- ]merge",),
        (r"current|fresh|revalidate|recheck",),
        (r"pr|pull request",),
        (r"head|sha",),
        (r"target|base",),
        (r"gate|check",),
        (r"stale|guard|match",),
    ))
    strategy = concept_present(target, (r"merge method.*caller|caller.*merge method|repository policy|policy.*capability|do not.*invent.*merge method",))
    checks.append(Check(
        "J", "explicit-intent merge boundary",
        "PASS" if merge_boundary and premerge and strategy and not hardcoded_merge_method(target) else "FAIL",
        f"explicit_intent={'present' if merge_boundary else 'missing'}; premerge_freshness={'present' if premerge else 'missing'}; method_policy={'present' if strategy else 'missing'}; hardcoded_squash={hardcoded_merge_method(target)}",
        "merge only on explicit intent after fresh PR/head/target/gate validation, using caller or policy-selected method",
    ))

    # K: merge confirmation precedes cleanup, and remote merge is separate from
    # local branch cleanup.
    confirmation = block_matching(target, (
        (r"after merge|merge result",),
        (r"authoritative|confirmed|read[- ]back|verify",),
        (r"merged",),
        (r"expected.*pr|pr.*head|head.*sha",),
    ))
    cleanup = block_matching(target, (
        (r"cleanup|delete",),
        (r"only after|after confirmed|authorized|policy",),
        (r"evidence|local",),
        (r"remote|branch",),
    ))
    separate_cleanup = concept_present(target, (r"local cleanup.*separate|separate.*local cleanup|remote merge.*local|not.*indivisible|independent operation",))
    checks.append(Check(
        "K", "merge confirmation and authorized cleanup",
        "PASS" if confirmation and cleanup and separate_cleanup else "FAIL",
        f"merge_readback={'present' if confirmation else 'missing'}; cleanup_gate={'present' if cleanup else 'missing'}; cleanup_separation={separate_cleanup}",
        "verify the expected PR/head was merged before authorized cleanup; keep cleanup separate from merge result",
    ))

    # L: the result is a requested-target state report, not a universal DONE.
    reporting = block_matching(target, (
        (r"requested|target state|desired state",),
        (r"attempted",),
        (r"succeeded|success",),
        (r"failed|failure|not attempted|not performed",),
        (r"pr|pull request",),
        (r"check|ci",),
        (r"merge",),
        (r"blocker|remaining",),
    ))
    state_separation = all(concept_present(target, patterns) for patterns in (
        (r"committed",), (r"pushed",), (r"pr exists|pull request exists|created|updated",),
        (r"checks pending|pending",), (r"checks failed|failed",), (r"checks satisfied|passed",),
        (r"review state",), (r"merge requested|explicit merge",), (r"merged",), (r"cleanup",),
    ))
    checks.append(Check(
        "L", "honest delivery state reporting",
        "PASS" if reporting and state_separation and concept_present(target, (r"pr.*not.*ci|ci.*not.*review|merged.*not.*released|not.*claim|do not.*claim",)) else "FAIL",
        f"requested_outcome_report={'present' if reporting else 'missing'}; state_separation={state_separation}",
        "report requested, attempted, succeeded, failed/not attempted, current PR/check/merge state, and blockers without collapsing states",
    ))

    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Behavioral contract for github-pr-workflow")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()

    try:
        checks = build_checks(args.repo)
    except Exception as exc:  # pragma: no cover - make malformed repo state explicit
        print(f"SPEC ERROR: {exc}")
        return 2

    for requirement in sorted({item.requirement for item in checks}):
        items = [item for item in checks if item.requirement == requirement]
        if any(item.status == "FAIL" for item in items):
            status = "FAIL"
        elif any(item.status == "DEFERRED" for item in items):
            status = "DEFERRED"
        else:
            status = "PASS"
        print(f"{requirement}: {status}")
        for item in items:
            print(f"  [{item.status}] {item.name}: {item.evidence}")
            if item.status == "FAIL" and item.target:
                print(f"         target: {item.target}")

    passed = sum(item.status == "PASS" for item in checks)
    failed = sum(item.status == "FAIL" for item in checks)
    deferred = sum(item.status == "DEFERRED" for item in checks)
    print(f"SUMMARY passed={passed} failed={failed} deferred={deferred} total={len(checks)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
