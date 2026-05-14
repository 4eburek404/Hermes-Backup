---
name: subagent-driven-development
description: "Use when executing plans via delegate_task with strict parent-child contracts, progress artifacts, and review gates."
version: 1.2.0
author: Hermes Agent (adapted from obra/superpowers)
license: MIT
metadata:
  hermes:
    tags: [delegation, subagent, implementation, workflow, parallel]
    related_skills: [writing-plans, requesting-code-review, test-driven-development]
---

# Subagent-Driven Development

## Overview

Execute implementation plans by dispatching fresh subagents per task with systematic two-stage review.

**Core principle:** Fresh subagent per task + two-stage review (spec then quality) = high quality, fast iteration.

**Controller principle:** the parent/orchestrator routes and verifies. It must not launch a subagent, lose/ignore the result, then silently do the task itself. If delegation fails, record it, recover from evidence, retry, or label fallback.

## When to Use

Use this skill when:
- You have an implementation plan (from writing-plans skill or user requirements)
- Tasks are mostly independent
- Quality and spec compliance are important
- You want automated review between tasks

**vs. manual execution:**
- Fresh context per task (no confusion from accumulated state)
- Automated review process catches issues early
- Consistent quality checks across all tasks
- Subagents can return `BLOCKED` with questions; the parent answers by retrying with fuller context

Do **not** use `delegate_task` for:
- Simple one-shot lookups where the parent can use a direct tool faster.
- News/search-only tasks when the user expects direct source handling; use `web`, RSS, `curl`, browser, or the relevant research skill and keep artifacts.
- Mechanical multi-step transformations with no judgment; use `execute_code` or deterministic scripts.
- Durable long-running work; use `cronjob` or `terminal(background=True, notify_on_complete=True)`.

## Strict Parent ↔ Subagent Contract

Every `delegate_task` call must carry a strict contract. If the task is not worth this contract, do not delegate it.

### Parent pre-flight gate

Before dispatch, the parent must define:

1. **Task boundary:** exact goal, non-goals, allowed files/systems, and whether mutation is permitted.
2. **Current context:** first line of `context` is `CURRENT CONTEXT: <date/time/timezone>; language=<...>; task_scope=<...>; source freshness=<...>` from a live `date` call when time-sensitive/current facts matter.
3. **Inputs:** full task text, paths, commands, errors, URLs, config, and constraints. Subagents know nothing except `goal` + `context`.
4. **Toolsets:** minimal toolsets needed; do not give browser/web/terminal if the task does not require them.
5. **Evidence handles:** required file paths, artifact paths, test commands, URLs, HTTP statuses, commit hashes, or IDs that the parent can verify afterwards.
6. **Return schema:** the child must return the exact structured summary below.

### Required child return schema

Ask every subagent to end with this block, filled with concrete values:

```text
SUBAGENT_RESULT
status: PASS | FAIL | BLOCKED | PARTIAL
summary: <1-3 bullets of what was actually done/found>
evidence:
  - <verifiable handle: file path, test command+result, URL, API status, artifact path, commit hash>
files_touched:
  - <path or none>
tests_or_checks:
  - <command/check + observed result, or not_run:<reason>>
open_issues:
  - <issue or none>
handoff_contract:
  parent_must_verify:
    - <specific verification step>
  safe_to_continue: yes | no
```

Vague outputs like “done”, “looks good”, “fixed”, or “researched” are **not** acceptable. They count as `PARTIAL` until verified or re-run.

### Parent acceptance gate

After `delegate_task` returns, the parent must:

1. Check raw runtime result: `status`, `exit_reason`, `error`, `diagnostic_path`, `api_calls`, `duration_seconds`; `status=completed` with `exit_reason=max_iterations` is only `PARTIAL` until verified.
2. Check child contract: `SUBAGENT_RESULT status` and `safe_to_continue`.
3. Verify evidence handles when side effects/high-stakes claims matter: read files, inspect diff, run tests, fetch URLs/API artifacts, or check artifact existence.
4. Save the child result in `notes.md`/`report.md` for multi-step workflows; continue only if schema and evidence verify.

If result is empty, interrupted, timed out, max-iterations, truncated, missing schema, or unverifiable:

- Mark delegation `UNVERIFIED`; do **not** attribute conclusions to the child.
- Recover: artifacts/diff/tests → Hermes session/log diagnostics (`diagnostic_path` if present) → one bounded retry with missing contract → explicit parent fallback.
- If falling back, state it in the final report and explain why delegation was abandoned.

### Progress artifacts for multi-step/delegate work

For multi-step/delegated/high-stakes workflows, create lightweight artifacts:

```text
plan.md   # task split, contracts, gates, allowed side effects
notes.md  # subagent calls, raw result summaries, evidence handles, verification notes
report.md # final synthesis, verified facts, unresolved issues, rollback/artifacts
```

Skip this overhead only for simple one-shot lookups.

### High-stakes verifier escalation

Use two-round `researcher → verifier/critic/fact-checker` only when stakes justify latency/cost: money/purchase, production/security, dates, airports/visas/baggage, conflicting sources, incomplete API/cache, or explicit user request.

Round 2 is valid only if the verifier receives:

- `researcher_summary`
- `facts_to_verify`
- artifact paths / URLs / commands / file paths

### Dual-process model check

For high-stakes research/review, use **two separate Hermes/agent processes**, not one `delegate_task` batch:

- Process A: explicit `DeepSeek-v4-pro`; give it the longer runtime budget for slow reasoning/network tasks.
- Process B: explicit `gemma4-31b`; same task, independent wording.
- Launch both in parallel (`terminal(background=True, notify_on_complete=True)` or tmux), with explicit `--model`/provider args.
- Do **not** wrap long-running subagents in a hard shell timeout that can kill them. Use background process handles plus non-destructive `poll`/bounded `wait`; a wait timeout means “still running” unless the process status says exited/failed.
- Persist prompts and logs as artifacts, e.g. `/home/konstantin/docs/research/<task>/process-a-prompt.txt` and `process-a.log`, so empty/truncated UI output does not lose the child’s evidence.
- Cap output in both prompts: final `SUBAGENT_RESULT` only, max 20 bullets total, no raw logs unless artifact path is requested.
- Parent compares only verifiable evidence. Agreement is not proof; disagreement creates `facts_to_verify` for a final parent/verifier pass.
- Parent final report must explicitly separate child results, parent-verified facts, artifacts, and whether any mutation/update was actually applied.

Why separate processes: normal `delegate_task(tasks=[...])` uses one configured delegation model for all normal children, so it is not the right mechanism for heterogeneous model checks.

For a concrete launch/monitor/verification pattern, load `references/dual-process-hermes-check-pattern.md`.

## The Process

### 1. Read and Parse Plan

Read the plan file. Extract ALL tasks with their full text and context upfront. Create a todo list:

```python
# Read the plan
read_file("docs/plans/feature-plan.md")

# Create todo list with all tasks
todo([
    {"id": "task-1", "content": "Create User model with email field", "status": "pending"},
    {"id": "task-2", "content": "Add password hashing utility", "status": "pending"},
    {"id": "task-3", "content": "Create login endpoint", "status": "pending"},
])
```

**Key:** Read the plan ONCE. Extract everything. Don't make subagents read the plan file — provide the full task text directly in context.

### 2. Per-Task Workflow

For EACH task in the plan:

#### Step 1: Dispatch Implementer Subagent

Use `delegate_task` with complete context:

```python
delegate_task(
    goal="Implement Task 1: Create User model with email and password_hash fields",
    context="""
    CURRENT CONTEXT: 2026-05-07 21:00:00 Asia/Yekaterinburg; language=English; task_scope=Task 1 only; source freshness=local repo state only.

    TASK FROM PLAN:
    - Create: src/models/user.py
    - Add User class with email (str) and password_hash (str) fields
    - Use bcrypt for password hashing
    - Include __repr__ for debugging

    FOLLOW TDD:
    1. Write failing test in tests/models/test_user.py
    2. Run: pytest tests/models/test_user.py -v (verify FAIL)
    3. Write minimal implementation
    4. Run: pytest tests/models/test_user.py -v (verify PASS)
    5. Run: pytest tests/ -q (verify no regressions)
    6. Commit: git add -A && git commit -m "feat: add User model with password hashing"

    PROJECT CONTEXT:
    - Python 3.11, Flask app in src/app.py
    - Existing models in src/models/
    - Tests use pytest, run from project root
    - bcrypt already in requirements.txt

    RETURN CONTRACT:
    End with SUBAGENT_RESULT exactly as defined in this skill.
    Evidence must include files touched and test commands with observed pass/fail.
    """,
    toolsets=['terminal', 'file']
)
```

#### Step 2: Dispatch Spec Compliance Reviewer

After the implementer completes, verify against the original spec:

```python
delegate_task(
    goal="Review if implementation matches the spec from the plan",
    context="""
    CURRENT CONTEXT: 2026-05-07 21:00:00 Asia/Yekaterinburg; language=English; task_scope=spec review for Task 1 only; source freshness=local repo state only.

    ORIGINAL TASK SPEC:
    - Create src/models/user.py with User class
    - Fields: email (str), password_hash (str)
    - Use bcrypt for password hashing
    - Include __repr__

    CHECK:
    - [ ] All requirements from spec implemented?
    - [ ] File paths match spec?
    - [ ] Function signatures match spec?
    - [ ] Behavior matches expected?
    - [ ] Nothing extra added (no scope creep)?

    RETURN CONTRACT:
    End with SUBAGENT_RESULT exactly as defined in this skill.
    `status: PASS` means all requirements match; `status: FAIL` means list specific spec gaps in open_issues.
    Evidence must include files inspected.
    """,
    toolsets=['file']
)
```

**If spec issues found:** Fix gaps, then re-run spec review. Continue only when spec-compliant.

#### Step 3: Dispatch Code Quality Reviewer

After spec compliance passes:

```python
delegate_task(
    goal="Review code quality for Task 1 implementation",
    context="""
    CURRENT CONTEXT: 2026-05-07 21:00:00 Asia/Yekaterinburg; language=English; task_scope=quality review for Task 1 only; source freshness=local repo state only.

    FILES TO REVIEW:
    - src/models/user.py
    - tests/models/test_user.py

    CHECK:
    - [ ] Follows project conventions and style?
    - [ ] Proper error handling?
    - [ ] Clear variable/function names?
    - [ ] Adequate test coverage?
    - [ ] No obvious bugs or missed edge cases?
    - [ ] No security issues?

    RETURN CONTRACT:
    End with SUBAGENT_RESULT exactly as defined in this skill.
    Put Critical/Important/Minor issues in open_issues with severity labels.
    `status: PASS` means APPROVED; `status: FAIL` means REQUEST_CHANGES.
    Evidence must include files inspected.
    """,
    toolsets=['file']
)
```

**If quality issues found:** Fix issues, re-review. Continue only when approved.

#### Step 4: Mark Complete

```python
todo([{"id": "task-1", "content": "Create User model with email field", "status": "completed"}], merge=True)
```

### 3. Final Review

After ALL tasks are complete, dispatch a final integration reviewer:

```python
delegate_task(
    goal="Review the entire implementation for consistency and integration issues",
    context="""
    CURRENT CONTEXT: 2026-05-07 21:00:00 Asia/Yekaterinburg; language=English; task_scope=final integration review; source freshness=local repo state only.

    All tasks from the plan are complete. Review the full implementation:
    - Do all components work together?
    - Any inconsistencies between tasks?
    - All tests passing?
    - Ready for merge?

    RETURN CONTRACT:
    End with SUBAGENT_RESULT exactly as defined in this skill.
    Evidence must include commands run, test result, and files/areas inspected.
    `safe_to_continue: yes` only if integration looks ready and required checks passed.
    """,
    toolsets=['terminal', 'file']
)
```

### 4. Verify and Commit

```bash
# Run full test suite
pytest tests/ -q

# Review all changes
git diff --stat

# Final commit if needed
git add -A && git commit -m "feat: complete [feature name] implementation"
```

## Task Granularity

**Each task = 2-5 minutes of focused work.**

**Too big:**
- "Implement user authentication system"

**Right size:**
- "Create User model with email and password fields"
- "Add password hashing function"
- "Create login endpoint"
- "Add JWT token generation"
- "Create registration endpoint"

## Red Flags — Never Do These

- Start implementation without a plan
- Skip reviews (spec compliance OR code quality)
- Proceed with unfixed critical/important issues
- Dispatch multiple implementation subagents for tasks that touch the same files
- Make subagent read the plan file (provide full text in context instead)
- Skip scene-setting context (subagent needs to understand where the task fits)
- Treat `BLOCKED` questions as a stop signal; retry with fuller context before proceeding
- Accept "close enough" on spec compliance
- Skip review loops (reviewer found issues → implementer fixes → review again)
- Let implementer self-review replace actual review (both are needed)
- **Start code quality review before spec compliance is PASS** (wrong order)
- Move to next task while either review has open issues

## Handling Issues

### If Subagent Returns `BLOCKED` With Questions

Subagents cannot interactively clarify with the user or parent during `delegate_task`. If required information is missing, the child must return `SUBAGENT_RESULT status: BLOCKED` with concrete questions in `open_issues`.

Parent behavior:
- Do not continue as if the child completed the task.
- Answer the questions by dispatching a retry/fix subagent with the missing context included.
- If the question changes requirements materially, escalate to the user before retrying.
- Record the blocked result and retry in `notes.md` for multi-step workflows.

### If Reviewer Finds Issues

- Implementer subagent (or a new one) fixes them
- Reviewer reviews again
- Repeat until approved
- Don't skip the re-review

### If Subagent Fails a Task

- Dispatch a new fix subagent with specific instructions about what went wrong
- Don't try to fix manually in the controller session while pretending the delegation succeeded
- If a parent fallback is necessary, label the subagent result `UNVERIFIED`/`FAILED`, explain the fallback, and verify parent-created work independently before continuing

## Efficiency Notes

**Why fresh subagent per task:**
- Prevents context pollution from accumulated state
- Each subagent gets clean, focused context
- No confusion from prior tasks' code or reasoning

**Why two-stage review:**
- Spec review catches under/over-building early
- Quality review ensures the implementation is well-built
- Catches issues before they compound across tasks

**Cost trade-off:**
- More subagent invocations (implementer + 2 reviewers per task)
- But catches issues early (cheaper than debugging compounded problems later)

## Integration with Other Skills

### With writing-plans

This skill EXECUTES plans created by the writing-plans skill:
1. User requirements → writing-plans → implementation plan
2. Implementation plan → subagent-driven-development → working code

### With test-driven-development

Implementer subagents should follow TDD:
1. Write failing test first
2. Implement minimal code
3. Verify test passes
4. Commit

Include TDD instructions in every implementer context.

### With requesting-code-review

The two-stage review process IS the code review. For final integration review, use the requesting-code-review skill's review dimensions.

### With systematic-debugging

If a subagent encounters bugs during implementation:
1. Follow systematic-debugging process
2. Find root cause before fixing
3. Write regression test
4. Resume implementation

## Example Workflow

Examples abbreviate `SUBAGENT_RESULT`; literal prompts must require the full schema above.

```text
1. Dispatch implementer.
2. If `BLOCKED`, retry with missing context; do not continue.
3. If `PASS`, verify evidence, then dispatch spec reviewer.
4. If spec reviewer `FAIL`, send fix task, then re-review.
5. After spec `PASS`, dispatch quality reviewer; fix/re-review until `PASS`.
6. Mark task complete only after evidence verifies and `safe_to_continue=yes`.
7. After all tasks, run final integration review + full tests.
```

## Remember

```
Fresh subagent per task
Strict return contract every time
No silent parent fallback after lost/empty child result
Two-stage review every time
Spec compliance FIRST
Code quality SECOND
Never skip reviews
Catch issues early
```

**Quality is not an accident. It's the result of systematic process.**

## Common Pitfalls

1. **Delegating without complete context.** The child has no parent history; pass full task text, paths, constraints, and current-date/source freshness requirements.
2. **Accepting unverifiable summaries.** A subagent self-report is not proof. Require evidence handles and verify them before reporting success.
3. **Silent fallback.** If the parent does the work after a failed child, record the failure and fallback explicitly; do not imply the subagent contributed evidence it did not return.
4. **Wrong task class.** Do not delegate simple searches, news lookups, or deterministic transformations when direct tools are more reliable.
5. **No progress artifacts.** Multi-step delegated work without `plan.md → notes.md → report.md` is hard to recover after truncation, interrupts, or empty summaries.
6. **Blind verification.** A reviewer without `researcher_summary`, `facts_to_verify`, and artifact paths cannot verify the research.
7. **Skipping gates under context pressure.** If summaries become vague or protocol steps disappear, checkpoint and either reset context or use a fresh verifier.

## Verification Checklist

- [ ] Parent pre-flight contract includes current context, task boundary, toolsets, evidence handles, and return schema.
- [ ] Subagent returned `SUBAGENT_RESULT` with `status`, evidence, files touched, checks, open issues, and `safe_to_continue`.
- [ ] Parent directly verified every material evidence handle before claiming success.
- [ ] Multi-step/delegate/high-stakes work has `plan.md`, `notes.md`, and `report.md` or an explicit skip reason.
- [ ] Failed/empty/interrupted/truncated child results are labeled `UNVERIFIED` and handled via recovery/retry/fallback, not ignored.
- [ ] High-stakes verifier received `researcher_summary`, `facts_to_verify`, and artifacts.
- [ ] Final user report separates child-provided evidence, parent verification, fallback work, and unresolved issues.

## Further reading (load when relevant)

When the orchestration involves significant context usage, long review loops, or complex validation checkpoints, load these references for the specific discipline:

- **`references/context-budget-discipline.md`** — Four-tier context degradation model (PEAK / GOOD / DEGRADING / POOR), read-depth rules that scale with context window size, and early warning signs of silent degradation. Load when a run will clearly consume significant context (multi-phase plans, many subagents, large artifacts).
- **`references/gates-taxonomy.md`** — The four canonical gate types (Pre-flight, Revision, Escalation, Abort) with behavior, recovery, and examples. Load when designing or reviewing any workflow that has validation checkpoints — use the vocabulary explicitly so each gate has defined entry, failure behavior, and resumption rules.

- **`references/session-subagent-contract-2026-05-07.md`** — session note on strict `SUBAGENT_RESULT` retrofit, wrong-checkout verifier failure, and parent fallback labeling.
- **`references/delegate-runtime-contracts.md`** — Hermes `delegate_task` runtime acceptance gate, reliability-first config profile, and verification commands from the 2026-05-07 deep analysis.
- **`references/dual-process-hermes-check-pattern.md`** — concrete two-process Hermes launch/monitor pattern for independent model checks, including non-killing waits, prompt/log artifacts, and parent verification checklist.

Both gate/context references adapted from gsd-build/get-shit-done (MIT © 2025 Lex Christopherson).
