---
name: github-code-review
description: "Use when independently reviewing a local diff or GitHub pull request."
version: 0.2.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [GitHub, Code-Review, Pull-Requests, Quality]
---

# GitHub Code Review

## Goal

Independently review an existing change and return actionable findings and a
verdict. The review may cover a local diff or a GitHub pull request. Review,
findings, verdict, and report are this skill's output; implementation and
 delivery are not.

Use the target behavior, constraints, and verification evidence supplied by the
caller when available. Do not silently replace an authoritative target with an
assumption derived from the current implementation.

## When to Use

Use when the user or an owning workflow asks to review an existing local change,
review a GitHub pull request, check a change before delivery, or publish an
explicitly requested GitHub review.

Do not use this skill to define requirements, diagnose an unexplained failure,
implement a fix, or manage the pull-request delivery lifecycle.

## Input

### Local diff

The minimum review context is the repository, the existing diff/change, and an
explicit base or repository base context when one is needed. Target behavior,
constraints, and caller-provided verification evidence are optional inputs.
Review the supplied change even when some optional context is unavailable, and
report the missing context instead of inventing it.

Local review is read-only relative to the user's checkout. Do not switch,
checkout, reset, clean, or delete branches in the user's working tree. A
separate temporary worktree is allowed only when remote materialization is
necessary; it must be isolated, preserve the user's checkout and branches, and
be removed after review.

### GitHub pull request

Use the authoritative PR metadata: PR identifier, base ref, head ref and head
SHA, changed files, diff, and relevant PR description. The PR metadata supplies
the canonical base; do not substitute `main` or another conventional branch.
For local review, use the explicit base or repository context supplied by the
caller. If a trustworthy base cannot be determined, say so and do not guess.

## Steps

1. **Select the mode.** Identify whether the input is a local diff or a GitHub
   PR and record the context being reviewed.
2. **Collect context.** For a PR, read metadata and changed files before the
   full diff. For a local change, inspect the supplied diff and base context
   without mutating the checkout.
3. **Check freshness.** Record the head/diff context examined. Before the final
   report or any publication attempt, re-check PR metadata, head SHA, and the
   affected diff. If they changed, refresh the affected review or report the
   result as stale/incomplete rather than presenting the old analysis as current.
4. **Read enough surrounding context.** Inspect changed files and the relevant
   callers, configuration, tests, and public boundaries needed to judge the
   change. Do not expand into an unrelated repository audit.
5. **Review material risks.** Check correctness, security, error handling,
   compatibility, testing, maintainability, documentation, and performance
   when relevant to the change. Compare the implementation with the supplied
   target behavior and constraints.
6. **Run proportionate read-only verification when useful.** Existing caller
   evidence may be used, but it is not automatically trusted when independent
   confirmation is needed. Run applicable tests, linters, or static checks
   directly, or capture their output while preserving the real exit status.
   Never hide a check's result behind a truncating pipeline such as
   `pytest ... | tail` or `ruff ... | head` without a reliable status mechanism.
7. **Form findings and verdict.** Return findings first, then classify them and
   state the review result. A finding is a review result, not an instruction to
   start implementation.
8. **Publish only when requested.** Analysis is separate from GitHub mutation.
   Publish a comment or formal review only when the caller explicitly requests
   it or supplies publication intent. After attempting publication, verify the
   provider response and report the actual outcome.

## Findings

A material finding must identify its location, describe the problem, explain its
impact or rationale, classify it as blocking or non-blocking, and state the
expected change or remediation direction. Findings should be specific enough for
the owning development workflow to act on, but must not contain an unsolicited
implementation patch.

Represent verification evidence honestly:

- executed and passed;
- executed and failed;
- not run or not attempted;
- supplied by the caller;
- unavailable or impossible to confirm.

Do not convert an unconfirmed check into a passing claim.

## Verdict

Use the findings and evidence to distinguish at least these outcomes:

- blocking problems exist;
- only non-blocking observations exist;
- no material findings;
- review is incomplete because required context or evidence is unavailable.

For a GitHub formal review, map the result to `REQUEST_CHANGES`, `COMMENT`, or
`APPROVE` only when the findings and evidence support that decision. The labels
are not a substitute for reasoning or a scoring framework.

## Publication status

Keep these states separate in the result:

- review prepared;
- publication requested;
- publication attempted;
- publication succeeded;
- publication failed;
- publication not attempted.

A command being invoked is not proof that a comment or formal review was
published. If authentication or provider access is unavailable, use the
`github-auth` owner when appropriate or report publication as unavailable; the
local analysis may still be returned.

## Ownership boundaries

This skill does not own SDD requirements or target-contract definition,
`systematic-debugging` root-cause investigation, TDD RED/GREEN/REFACTOR,
Ponytail implementation or refactoring, or fixes to the reviewed code. It also
does not own GitHub authentication setup, branch creation, commit, push, PR
creation, merge, CI, or release delivery. Those procedures belong to their
respective owners; this skill only consumes their handoffs and returns review
results.

After a finding, stop at the review result. If the caller wants a fix, hand the
finding back to the development workflow; do not patch, implement, commit, or
push as part of review.

## Check

Before reporting completion, confirm that the reviewed context is identified,
the base is authoritative or explicitly unknown, changed files and relevant
surrounding code were read, findings and their evidence are recorded, and the
verdict follows those findings. For a PR, confirm that the final head/diff is
still the context reviewed. If publication was requested, report the attempted
operation and its confirmed result separately from the analysis.

## Stop

Stop or report an incomplete review when the diff, PR metadata, base/head
identity, target behavior, or required evidence cannot be trusted. Do not guess
the base branch, claim a stale review is current, or silently turn a review into
an implementation task.

## References

- `github-auth` — authentication setup, when publication requires it.
- `github-pr-workflow` — branch, commit, PR, CI, merge, and delivery mechanics.
- `spec-driven-development` — target behavior and requirement/check ownership.
- `systematic-debugging` — diagnosis and root-cause ownership.
- `test-driven-development` — regression and RED/GREEN/REFACTOR ownership.
- `ponytail` — implementation-shape and minimality constraints.
