#!/usr/bin/env python3
"""Executable behavioral contract for the normalized github-code-review skill.

The target is a declarative SKILL.md, so this contract audits semantic policy
blocks and operational examples rather than asserting headings or exact prose.
It deliberately has only a small number of requirement-level checks. Agent
quality claims (for example, whether a finding is substantively correct) remain
agent/eval requirements and are not reduced to source-text matching here.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


TARGET = Path("hermes/skills/github/github-code-review/SKILL.md")
ISSUE_TO_PR = Path("hermes/skills/github/github-issue-to-pr/SKILL.md")


@dataclass(frozen=True)
class Check:
    requirement: str
    name: str
    status: str  # PASS, FAIL, or DEFERRED
    evidence: str


@dataclass(frozen=True)
class Source:
    path: Path
    text: str
    prose_blocks: tuple[str, ...]
    code_blocks: tuple[str, ...]
    frontmatter: str


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold())


def blocks(text: str) -> tuple[str, ...]:
    return tuple(normalized(part) for part in re.split(r"\n\s*\n", text) if part.strip())


def fenced_blocks(text: str) -> tuple[str, ...]:
    return tuple(
        normalized(match.group(1))
        for match in re.finditer(r"```[^\n]*\n(.*?)```", text, flags=re.DOTALL)
    )


def prose_without_fences(text: str) -> str:
    return re.sub(r"```[^\n]*\n.*?```", "", text, flags=re.DOTALL)


def load_source(repo: Path, path: Path) -> Source | None:
    resolved = repo / path
    if not resolved.is_file():
        return None
    text = resolved.read_text(encoding="utf-8")
    frontmatter = ""
    if text.startswith("---\n"):
        parts = text.split("\n---\n", 1)
        if len(parts) == 2:
            frontmatter = normalized(parts[0])
    prose = prose_without_fences(text)
    return Source(
        path=resolved,
        text=text,
        prose_blocks=blocks(prose),
        code_blocks=fenced_blocks(text),
        frontmatter=frontmatter,
    )


def has_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def block_with_groups(source: Source, *groups: tuple[str, ...]) -> bool:
    return any(
        all(has_any(block, group) for group in groups)
        for block in source.prose_blocks
    )


def concept_present(source: Source, patterns: tuple[str, ...]) -> bool:
    return any(has_any(block, patterns) for block in source.prose_blocks)


def section(text: str, heading: str) -> str:
    """Return one broad Markdown section without requiring exact section names."""
    match = re.search(
        rf"^##\s+[^\n]*{heading}[^\n]*\n(.*?)(?=^##\s+|\Z)",
        text,
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    return match.group(1) if match else ""


def unsafe_local_commands(source: Source) -> bool:
    local = section(source.text, r"local|pre[- ]push")
    if not local:
        return False
    return bool(
        re.search(
            r"git\s+(?:checkout|reset|clean)\b|git\s+branch\s+-D\b",
            local,
            flags=re.IGNORECASE,
        )
    ) and not bool(re.search(r"worktree|detached|temporary|isolat", local, flags=re.IGNORECASE))


def unqualified_main_base(source: Source) -> bool:
    code = "\n".join(source.code_blocks)
    return bool(
        re.search(
            r"git\s+diff\s+main\.\.\.|git\s+checkout\s+main\b|--base\s+main\b",
            code,
            flags=re.IGNORECASE,
        )
    )


def lossy_check_pipeline(source: Source) -> bool:
    code = "\n".join(source.code_blocks)
    verification = re.compile(r"pytest|npm\s+test|cargo\s+test|go\s+test|ruff|eslint|clippy|mypy")
    truncation = re.compile(r"\|\s*(?:tail|head)\b")
    return bool(verification.search(code) and truncation.search(code)) and not bool(
        re.search(r"pipefail|pipestatus|pipe status|capture(?:d)?\s+(?:the\s+)?exit", source.text, flags=re.IGNORECASE)
    )


def evaluate(repo: Path) -> list[Check]:
    target_path = repo / TARGET
    issue_path = repo / ISSUE_TO_PR
    target = load_source(repo, TARGET)
    issue_text = normalized(issue_path.read_text(encoding="utf-8")) if issue_path.is_file() else ""

    checks: list[Check] = []

    # A: the orchestrator's owner reference must resolve to a usable skill.
    route_ok = bool(
        re.search(r"github[- ]code[- ]review", issue_text)
        and re.search(r"(?:owns|owner|route|hand[- ]?off).{0,100}review", issue_text)
    )
    target_ok = bool(
        target
        and re.search(r"name:\s*github[- ]code[- ]review", target.frontmatter)
        and block_with_groups(target, (r"review",), (r"change|diff|pull request|pr",))
    )
    checks.append(
        Check(
            "A",
            "owner reference resolves to usable skill",
            "PASS" if route_ok and target_ok else "FAIL",
            f"route={'present' if route_ok else 'missing'}, target={'usable' if target_ok else 'missing or not review-capable'}",
        )
    )

    # Remaining checks require the target artifact. They are deliberately
    # deferred, not reported as synthetic failures, when the owner is absent.
    if target is None:
        for requirement, name in (
            ("B", "ownership boundaries"),
            ("C", "read-only local review"),
            ("D", "PR context and authoritative base"),
            ("E", "finding information contract"),
            ("F", "verification evidence states"),
            ("G", "review returns findings instead of fixing"),
            ("H", "publication intent and outcome"),
            ("I", "stale review context"),
        ):
            checks.append(Check(requirement, name, "DEFERRED", "target SKILL.md is absent"))
        return checks

    # B: review owns review; the neighboring workflows remain explicit owners
    # of specification, diagnosis, implementation/testing, and delivery.
    owners = {
        "SDD": (r"specification|requirements|target behavior|contract",),
        "debugging": (r"debugging|root cause|diagnos|hypothes|data flow",),
        "TDD": (r"test[- ]driven|red|green|regression test|refactor",),
        "Ponytail": (r"ponytail|implementation shape|minimal implementation",),
        "delivery": (r"branch|commit|push|pull request|merge|ci delivery",),
        "auth": (r"authentication|credential|token|gh auth",),
    }
    missing_boundaries = []
    for owner, domain in owners.items():
        boundary = any(
            has_any(block, domain)
            and has_any(block, (r"does not own|not own|outside scope|out of scope|belongs to|owned by|hand off|delegate",))
            for block in target.prose_blocks
        )
        if not boundary:
            missing_boundaries.append(owner)
    active_auth_setup = any(
        has_any(code, (r"gh\s+auth\s+login", r"gh\s+auth\s+setup-git", r"GITHUB_TOKEN\s*=", r"git-credentials", r"credential\.helper"))
        for code in target.code_blocks
    )
    review_scope = block_with_groups(target, (r"review",), (r"diff|change|pull request|pr",), (r"findings|verdict|report",))
    checks.append(
        Check(
            "B",
            "review ownership and non-ownership boundaries",
            "PASS" if review_scope and not missing_boundaries and not active_auth_setup else "FAIL",
            f"review_scope={review_scope}; missing_boundaries={missing_boundaries or 'none'}; auth_setup={'present' if active_auth_setup else 'absent'}",
        )
    )

    # C: local review is a read-only capability and must not replace the user's
    # checkout or delete/reset their state.
    local_capability = block_with_groups(target, (r"local|pre[- ]push",), (r"review",), (r"diff|change",))
    local_safety = block_with_groups(target, (r"local|pre[- ]push",), (r"read[- ]only|unchanged|preserve|do not.*checkout|temporary|detached|worktree|isolat",))
    checks.append(
        Check(
            "C",
            "read-only local review",
            "PASS" if local_capability and local_safety and not unsafe_local_commands(target) else "FAIL",
            f"capability={local_capability}; safety={local_safety}; unsafe_local_commands={unsafe_local_commands(target)}",
        )
    )

    # D: PR review consumes authoritative PR context and never silently turns
    # the repository's conventional 'main' into the base branch.
    pr_context = block_with_groups(
        target,
        (r"pull request|pr",),
        (r"metadata|base|head|commit|sha",),
        (r"diff|changed files|files",),
        (r"finding|verdict|report|review",),
    )
    authoritative_base = block_with_groups(
        target,
        (r"base|default branch",),
        (r"pr metadata|caller|repository context|authoritative|provided",),
    )
    checks.append(
        Check(
            "D",
            "PR context and authoritative base",
            "PASS" if pr_context and authoritative_base and not unqualified_main_base(target) else "FAIL",
            f"pr_context={pr_context}; authoritative_base={authoritative_base}; hardcoded_main={unqualified_main_base(target)}",
        )
    )

    # E: a finding is actionable without prescribing a particular Markdown
    # template.
    finding_contract = block_with_groups(
        target,
        (r"finding|issue|problem",),
        (r"file|path|line|location",),
        (r"why|impact|risk|important",),
        (r"blocking|non[- ]blocking|severity|critical|warning|suggestion",),
        (r"expected|suggest|recommend|change",),
    )
    checks.append(Check("E", "finding information contract", "PASS" if finding_contract else "FAIL", f"actionable_finding_contract={finding_contract}"))

    # F: review evidence distinguishes outcomes and preserves command status.
    evidence_states = all(
        concept_present(target, patterns)
        for patterns in (
            (r"passed|success|green",),
            (r"failed|failure|red|error",),
            (r"not run|not executed|skipped|not attempted",),
            (r"provided by caller|caller-provided|supplied evidence",),
            (r"exit status|exit code|status code|return code",),
        )
    )
    checks.append(
        Check(
            "F",
            "verification evidence states and exit status",
            "PASS" if evidence_states and not lossy_check_pipeline(target) else "FAIL",
            f"states={evidence_states}; lossy_pipeline={lossy_check_pipeline(target)}",
        )
    )

    # G: findings end the review; implementation remains a different owner.
    review_return = block_with_groups(
        target,
        (r"review|finding",),
        (r"return|report|handoff|complete|end",),
        (r"do not|does not|not responsible|without",),
        (r"fix|patch|implement|write_file|commit",),
    )
    implementation_commands = any(
        has_any(code, (r"write_file", r"apply_patch", r"git\s+commit", r"git\s+push"))
        for code in target.code_blocks
    )
    checks.append(
        Check(
            "G",
            "review returns findings instead of fixing",
            "PASS" if review_return and not implementation_commands else "FAIL",
            f"boundary={review_return}; implementation_commands={implementation_commands}",
        )
    )

    # H: analysis and external mutation are separate outcomes, and publication
    # requires explicit caller/workflow intent plus confirmation.
    publication_states = all(
        concept_present(target, patterns)
        for patterns in (
            (r"prepared|analysis|report ready|not published|not attempted",),
            (r"published|publication",),
            (r"failed|failure|not confirmed|unconfirmed",),
            (r"confirmed|read back|response|operation result",),
        )
    )
    publication_intent = block_with_groups(
        target,
        (r"publish|post|submit",),
        (r"review|comment",),
        (r"explicit|requested|intent|flag|workflow",),
        (r"only|when|if",),
    )
    unconditional_post = any(
        has_any(block, (r"post|submit|publish",))
        and has_any(block, (r"review|comment",))
        and not has_any(block, (r"only when|if requested|explicitly requested|publication intent|workflow flag",))
        and not has_any(block, (r"not proof|does not prove|do not|does not|without",))
        for block in target.prose_blocks
    )
    checks.append(
        Check(
            "H",
            "publication intent and outcome",
            "PASS" if publication_states and publication_intent and not unconditional_post else "FAIL",
            f"states={publication_states}; intent={publication_intent}; unconditional_publication={unconditional_post}",
        )
    )

    # I: a review is tied to the context it examined and must detect a changed
    # head/diff before reporting the old result as current.
    stale_contract = block_with_groups(
        target,
        (r"stale|changed|current|relevant|fresh",),
        (r"head|sha|diff|review context",),
        (r"compare|re-fetch|refresh|verify|revalidate|check",),
    )
    checks.append(Check("I", "stale review context", "PASS" if stale_contract else "FAIL", f"stale_context_contract={stale_contract}"))

    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Behavioral contract for github-code-review")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()

    checks = evaluate(args.repo)
    for requirement in sorted({item.requirement for item in checks}):
        items = [item for item in checks if item.requirement == requirement]
        status = "PASS" if all(item.status == "PASS" for item in items) else "FAIL" if any(item.status == "FAIL" for item in items) else "DEFERRED"
        print(f"{requirement}: {status}")
        for item in items:
            print(f"  [{item.status}] {item.name}: {item.evidence}")

    passed = sum(item.status == "PASS" for item in checks)
    failed = sum(item.status == "FAIL" for item in checks)
    deferred = sum(item.status == "DEFERRED" for item in checks)
    print(f"SUMMARY passed={passed} failed={failed} deferred={deferred} total={len(checks)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
