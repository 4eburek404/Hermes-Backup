---
name: skill-audit-and-improvement
description: "Use when auditing, improving, shrinking, or creating Hermes skills and skill-owned checks. Verifies source state, runs deterministic audits, routes long knowledge to support files, and reports behavior delta."
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [skills, audit, improvement, verification, hermes-agent, skill-library]
    related_skills: [hermes-agent, hermes-agent-skill-authoring, requesting-code-review, knowledge-architecture]
---

# Skill Audit and Improvement

## Goal
Audit and improve Hermes skills safely and reproducibly. Keep `SKILL.md` compact, place long knowledge in support files, use scripts for deterministic checks, and report what future agent behavior will change.

## Steps
1. Identify the target skill, requested outcome, and mutation scope: audit only, rewrite, shrink, create, CLI/schema review, or post-session learning.
2. Verify source state before editing. Check branch, HEAD, status, and target diff; do not rely on memory or runtime state alone.
3. Read the target `SKILL.md`, its support files, and 1-3 nearby peer skills before proposing changes.
4. Run the read-only audit helper when a repo source tree is available:
   `python3 hermes/skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --skill <skill-name> --json`
5. Follow `references/audit-workflow.md` for provenance, source/runtime checks, scoped cleanup, verification, and final report evidence.
6. Choose the smallest durable layer:
   - short operational path or trigger -> `SKILL.md`;
   - long method, case detail, history, or research -> `references/`;
   - reusable report or worksheet -> `templates/`;
   - deterministic redaction, inventory, or pass/fail check -> `scripts/`;
   - stable machine-readable contract -> `schemas/`.
7. For semantic/deep audits, use `references/skill-quality-model.md` and replay only the relevant cases from `references/scenarios.md`; name the behavior delta and mistake prevented.
8. For CLI, JSON, schema, doctor-envelope, report-contract, golden-path, or bypass-surface questions, use `references/cli-schema-contracts.md` and the existing scripts/schemas before inventing a new contract.
9. Edit only the scoped files, then validate. If validation exposes a small related-skill defect, fix it only when it is clearly in scope and low risk.
10. Report with `templates/audit-report.md`: changed files, why, verification, behavior delta when relevant, remaining risk, rollback/commit state.

## Input
- Target skill name or path.
- User goal: audit, improve, shrink, create, validate, migrate structure, or review skill-owned CLI/schema.
- Available source evidence: branch, commit, diff, support files, prior session lesson, peer-skill reference, or runtime read-back.
- Explicit approval before mutating protected context, credentials, services, cron, production systems, external providers, or unrelated dirty files.

## Output
- Compact audit/improvement report.
- Updated `SKILL.md`, reference/template/script/schema changes, or justified no-change.
- Verification evidence: commands/read-back, static audit result, scenario replay when semantic behavior changed, and commit/push state if performed.
- Clear separation of completed work, baseline issues, and remaining follow-up.

## Check
- Frontmatter has `name`, `description`, and `version`; description starts with `Use when`.
- Main body uses the canonical section shape: `Goal`, `Steps`, `Input`, `Output`, `Check`, `Stop`, `References`, and optional `Dependencies`.
- `SKILL.md` stays compact; long rubrics, incident history, command cookbooks, and scenario matrices are linked from support files instead of copied into the main skill.
- Run before committing when a repo source tree is available:
  `git diff --check`
  `python3 hermes/skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --skill <skill-name> --json`
- If `audit_skill.py`, schemas, or report-contract fields changed, validate emitted JSON from the repo root:
  `python3 hermes/skills/software-development/skill-audit-and-improvement/scripts/validate_audit_report.py /tmp/audit_report.json`
- If scripts or CLIs changed, run syntax/tests without leaving generated artifacts (`PYTHONDONTWRITEBYTECODE=1` or equivalent cleanup).
- If the change claims a golden path, anti-path, or fail-closed behavior, verify positive path, negative path, bypass surfaces, and read-back/mutation proof.

## Stop
- Stop before editing if source/runtime provenance is unclear and no runtime-only fallback was explicitly accepted.
- Do not write to `~/.hermes/skills` as source in Konstantin's setup unless the task is explicitly runtime-only.
- Do not create a new skill, owning CLI, JSON schema, or report contract by default; use existing support layers unless a real repeated machine consumer exists.
- Do not print secrets, credential-bearing URLs, raw tokens, raw private paths, or unredacted grep output.
- Do not mutate protected context, credentials, external systems, services, cron, or production state without explicit approval.
- Do not claim `done`, `committed`, `pushed`, or `ready` unless that exact state was verified.

## References
- `references/audit-workflow.md` — use for branch/source provenance, scoped cleanup, source/runtime sync, verification, and reporting.
- `references/skill-quality-model.md` — use for semantic quality, behavior delta, scenario replay, progressive disclosure, and mistake-prevention analysis.
- `references/cli-schema-contracts.md` — use for CLI/schema/JSON report contracts, doctor envelope, advisory execution, schema-output mappings, and protocol rationale.
- `references/scenarios.md` — use for replaying recurring audit failure modes.
- `templates/audit-report.md` — use for final audit/improvement reports.
- `templates/deep-skill-audit.md` — use as a worksheet for high-impact or user-corrected skills.
- `scripts/audit_skill.py` — read-only deterministic audit helper.
- `scripts/validate_audit_report.py` and `schemas/audit-report.schema.json` — use when audit report contract/schema/script fields changed.
- `schemas/cli-doctor-envelope.v1.schema.json` — central advisory doctor JSON envelope contract.

## Dependencies
Use the repository's normal Python interpreter. Optional schema checks need `jsonschema` only when available; absence of `jsonschema` must remain a non-blocking advisory skip unless a later explicit enforcement task changes that contract.
