# Skill Audit Workflow

## Purpose

Use this workflow to audit or change a Hermes skill without confusing source state, runtime state, scope, and report evidence. The default posture is read-only until the target, branch, dirty files, and requested mutation scope are clear.

## Standard flow

1. **Scope the task.** Name the target skill, the requested outcome, and whether the task is audit-only, source edit, runtime-only repair, CLI/schema review, shrink, or new-skill authoring.
2. **Verify source state.** Capture branch, HEAD, status, target path, and relevant diff before edits. If the checkout has unrelated dirty files, treat them as protected context.
3. **Read before changing.** Read the target `SKILL.md`, linked support files, and nearby peer skills. Do not infer the current contract from memory.
4. **Run deterministic audit when available.** Use `scripts/audit_skill.py` from the source tree and save the JSON result when the report affects the implementation.
5. **Choose the smallest durable layer.** Keep operational guidance in `SKILL.md`; move long method/cases to `references/`; reusable forms to `templates/`; deterministic checks to `scripts/`; machine contracts to `schemas/`.
6. **Edit within scope.** Fix the smallest file set that addresses the finding. Do not broaden into unrelated skills, runtime config, providers, cron, credentials, or production systems without explicit approval.
7. **Verify and clean up.** Re-run the focused audit/tests, validate report schemas when contract fields changed, and remove generated artifacts before commit.
8. **Report state, not intent.** Say what changed, why, how it was verified, what remains, and whether the change is committed/pushed.

## Source/runtime sync gate

When source and runtime may differ:

- Compare branch, HEAD, status, and target manifests first.
- Exclude only generated/cache artifacts from source-runtime comparison by default.
- Classify differences:
  - **Low risk:** generated/cache/runtime outputs only.
  - **Medium risk:** docs/templates/references differ but are readable and non-secret.
  - **High risk:** scripts, schemas, prompts, credentials, side-effect helpers, or unknown binary files differ.
- Inspect runtime-only source before any destructive sync.
- Preserve durable runtime-only rules in git first; then re-run the comparison.
- Do not use destructive delete/sync commands during planning or without explicit scope approval.

## Narrow cleanup protocol

For a bounded cleanup request:

1. Treat the allowed-file list as a hard contract.
2. Inspect each exact finding and classify it as real risk, detector literal, test fixture, documentation example, or stale path.
3. Prefer the smallest neutral rewrite that keeps the lesson while removing the risky literal.
4. Do not change detector semantics just to hide a warning unless detector behavior is the actual bug.
5. Stage only allowed paths.
6. Do not push, run deep executable checks, or mutate runtime state unless the user asked for that exact next step.

## Evidence requirements

Minimum evidence before saying done:

- Target path and branch/status were checked.
- Modified files were read or diffed after edit.
- Relevant tests or audit command were run; failures are reported as failures, not softened.
- Generated artifacts were removed or proven absent.
- Secrets and credential-like values were not printed in reports or logs.

## Report shape

Use `templates/audit-report.md` for the final user-facing report. Always separate:

- **Changed:** actual files/commits.
- **Why:** concrete cause and behavior delta.
- **Verified:** commands and outcomes.
- **Remaining:** baseline warnings, intentionally deferred work, or uncertainty.
- **Commit state:** not committed, committed SHA, pushed branch, or PR.

## Stop conditions

Stop and ask before mutation when:

- The target source tree is ambiguous.
- Unrelated dirty files would be touched.
- The change affects credentials, providers, external systems, production, cron, or service state.
- Runtime-only evidence conflicts with source and the user did not authorize reconciliation.
- The audit exposes secret-like values in generated output.
