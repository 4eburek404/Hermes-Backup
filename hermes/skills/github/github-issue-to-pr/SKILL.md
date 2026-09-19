---
name: github-issue-to-pr
description: "Carry a GitHub issue to a verified PR with honest CI state."
version: 0.1.0
author: Ben Barclay (benbarclay), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [GitHub, Issues, Coding, Pull-Requests, CI]
    related_skills: [github-issues, github-pr-workflow, github-code-review, spec-driven-development, systematic-debugging, test-driven-development, ponytail]
---

# GitHub Issue to Pull Request

Turn a GitHub issue into a verified delivery while keeping ownership explicit.
This skill is the orchestrator: it gathers live state, classifies the issue,
selects the development route, coordinates specialist handoffs, and reports the
fresh delivery state. It does not reproduce the internal procedures owned by
SDD, debugging, TDD, Ponytail, review, or PR delivery skills.

## When to Use

- "Carry issue #123 through the route."
- "Implement an active GitHub feature request."
- "Take a bug to an honest delivery state."

Don't use for reviewing an existing PR or answering a code question with no
requested change.

## Procedure

### 1. Read live issue and repository state

Read the live issue identity, full body, and complete comment thread. Latest
comments are the current state: they may record a partial fix, a maintainer
decision, a new constraint, or a question that changes the task. Read
repository instructions such as `AGENTS.md` and contribution documentation
before routing work.

Determine the current default branch and inspect the current code state there.
Keep issue prose, thread state, repository instructions, and current-code
observations separate from assumptions.

### 2. Classify the issue before development

Classify the live issue result as `active`, `duplicate`, `stale`, or `resolved`.
Record the disposition and pass only `active` issues to the development
pipeline. For `duplicate`, `stale`, and `resolved` results, stop before tests,
branch creation, or a pull request; do not start unnecessary development.

### 3. Sweep for existing work

Search for existing work before implementation: issue-linked PRs, open and
closed duplicates using symptom synonyms, and recent commits touching the
relevant files. Include the full issue number search, bounded keyword variants,
and recent commit history. Preserve any existing PR, partial fix, or already
resolved state in the disposition.

### 4. Establish the current premise

On the current default branch, establish whether the reported mismatch is
observed and whether the premise is still current. Check current code and
history for design intent so that stale issue prose or deliberate behavior is
not treated as a defect. The orchestrator may state that a mismatch is
observed, the premise is current, and the cause is known or unknown; it does
not diagnose an unknown cause.

When a bug needs diagnosis, route the observed symptom and mismatch to
`systematic-debugging`; that owner handles diagnosis, root cause, data flow,
hypotheses, instrumentation, and the diagnostic handoff. The orchestrator
returns with the resulting constraints and sibling/class findings rather than
performing that work itself.

### 5. Route the target specification

For an active development issue, send a factual packet to
`spec-driven-development`: the live issue and thread, target behavior,
non-goals, current-state evidence, relevant constraints, design-intent findings,
and any debugging handoff. `spec-driven-development` owns the target
specification, public contract, edge cases, requirement/check mapping,
proportional mode, baseline, and safeguards. Issue-to-PR supplies facts and does
not set the target contract.

Engaged development follows this ownership chain:
`spec-driven-development` target -> when diagnosis is needed,
`systematic-debugging` -> `test-driven-development` preflight / regression
check / RED -> `ponytail` implementation-shape constraints ->
`test-driven-development` implementation / GREEN / REFACTOR / regression
proof.

### 6. Compose TDD and implementation constraints

`test-driven-development` owns the right-size decision: for trivial or
mechanical work it may skip full TDD or adopt an existing check under its
contract. TDD owns RED, GREEN, and regression proof for engaged work; the
orchestrator does not impose a universal ceremony. `systematic-debugging` is
optional for trivial or mechanical work and is not required unless there is a
diagnostic problem.

Mechanical or trivial work does not require sabotage or revert-to-red; without
a diagnostic problem, no artificial RED/GREEN ceremony is added.

`ponytail` supplies implementation shape constraints: reuse existing
mechanisms, choose the smallest sufficient change, decide shared mechanism
versus local patch, touch the fewest necessary files, and preserve safeguards.
When TDD skips full ceremony for trivial or mechanical work, apply Ponytail's
minimal implementation scope without artificial ceremony.

Sibling and class findings from `systematic-debugging` inform the scope
decision. SDD and Ponytail determine whether a sibling belongs in the current
change; a sibling is not automatically included merely because it was found.

### 7. Route review and delivery

Pass the current diff and development evidence to `github-code-review`, which
owns review. If the diff changes after findings, route the fresh diff and fresh
development evidence back for a new review of the actual change.

`github-pr-workflow` owns branch, commit, pull-request, and CI delivery
mechanics. Hand off the reviewed change, issue linkage, verification evidence,
and the required delivery intent to that owner.

The orchestrator delegates branch, commit, push, pull-request submission, body,
and CI command instructions to the delivery owner.

Require a fresh delivery-state report after handoff: the pull request is present,
head/base/title/files are correct, CI state is current, merge state is explicit,
and issue linkage is present. Do not collapse PR identity, CI, merge, and release
into one claim.

### 8. Return from CI failures

A code-caused CI failure follows this ownership transition:
delivery state -> development pipeline -> review -> delivery state. Return to
SDD/TDD/Ponytail as applicable, use `systematic-debugging` when the cause is
unknown, then pass the changed diff through `github-code-review` and back to
`github-pr-workflow` for fresh CI verification.

An infrastructure or baseline failure remains a delivery state problem. The
orchestrator does not execute a `fix -> patch -> commit -> push` loop; it routes
the failure to the owner that can establish the next delivery state.

### 9. Report honest final status

Report only fresh evidence: active or terminal issue disposition, development
verification, pull-request existence and identity, CI pending/pass/fail,
merge state, release state, remaining blockers, and issue linkage. A PR is not
proof of green CI; green CI is not proof of merge; merge is not proof of
release.

## Verification

- [ ] Full issue body and complete thread were read; latest state is reflected.
- [ ] Repository instructions and current default branch were inspected.
- [ ] Duplicate/existing-work sweep and recent-commit check were performed.
- [ ] The issue was classified as active, duplicate, stale, or resolved before development.
- [ ] The current premise and design intent were checked.
- [ ] Active work received an SDD factual packet; debugging was used only when diagnosis was needed.
- [ ] Specialist owners supplied implementation, review, and delivery evidence.
- [ ] Fresh PR, CI, merge, release, and issue-linkage state was reported separately.
