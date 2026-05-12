---
name: knowledge-architecture
description: "Use when maintaining Konstantin's personal knowledge architecture: distilling sessions into docs, auditing/reviewing/pruning docs, cleaning holographic memory, governing plan lifecycle, or routing durable knowledge across memory, docs, skills, and session history."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [memory, knowledge-management, distillation, docs, holographic, fact-store, audit, curation, plans, governance, source-of-truth]
    related_skills: [hermes-agent]
---

# Knowledge Architecture

## Overview

This skill governs durable knowledge routing and maintenance across Konstantin's Hermes layers: protected built-in context (`USER.md`, `MEMORY.md`, `SOUL.md`), holographic `fact_store`, `/home/konstantin/docs/`, Hermes skills, and `session_search` history. Its job is to pick the right layer, gather read-only evidence before edits, and prevent drift, duplication, stale current-state claims, and memory pollution.

Default stance: evidence first, conservative targeted edits second, compact report last. The bundled `knowledge` CLI is the preferred deterministic evidence collector, not a permission channel and not an editor.

## When to Use

Use this skill when the user asks to:

- distill/actualize recent sessions into durable knowledge;
- audit, prune, reorganize, or validate `/home/konstantin/docs/`;
- audit or clean holographic memory / `fact_store`;
- create, update, close, archive, or review plans under `/home/konstantin/docs/plans/`;
- decide whether something belongs in memory, docs, a skill, `fact_store`, or session history;
- modify or audit this `knowledge-architecture` skill, its references, or its bundled `knowledge` CLI;
- investigate stale paths, duplicated durable rules, wrong-layer knowledge, or current-state claims in Konstantin's knowledge system.

Do **not** use it for ordinary one-off answers unless durable knowledge routing, docs/memory/skill maintenance, or plan governance is actually involved. For Hermes Agent setup/config/tooling itself, load `hermes-agent` too.

## Knowledge Layer Routing

Prefer the smallest durable layer that solves the problem:

- **`USER.md`** — stable user identity, communication preferences, work context, and durable style contract.
- **`MEMORY.md`** — always-on index plus self-referential guardrails and known-wrong technical quirks that the agent would otherwise silently repeat.
- **`SOUL.md`** — behavioral constitution: fact/hypothesis boundary, permission model, tool-use discipline, source verification, and communication laws.
- **`fact_store`** — atomic durable facts, entity recall, trust/helpful scoring, and compositional queries. Search/probe/reason before answering user/environment/history questions; rate facts after use.
- **`/home/konstantin/docs/`** — human-readable source of truth for structured operational context, runbooks, user context, and plan audit trail.
- **Skills** — executable repeatable workflows with exact commands, pitfalls, and verification.
- **`session_search`** — raw history, detailed past-session recall, temporary progress, and evidence that should not become durable by default.

`MEMORY.md` composition has four canonical content classes: indices, self-protection guardrails, holographic hygiene, and known-wrong quirks. The full rationale and historical refactor evidence live in `references/memory-hygiene.md` and `references/memory-refactoring-2026-05.md`.

## Default Workflow

1. **Classify the task.** Identify whether it is distillation, docs review, memory hygiene, plan governance, skill/CLI maintenance, or layer-routing.
2. **Load the relevant reference.** Use the reference map below; do not rely on the compact main skill for detailed procedures.
3. **Collect read-only evidence.** Prefer `knowledge --json doctor` or `knowledge --json report --all`, then drill into `paths`, `docs`, `plans`, `memory`, `scan`, `skill`, or `distill` subcommands. For repo changes, verify branch, HEAD, status, and target diff first.
4. **Verify current-state claims.** External permissions, ACLs, scopes, cron schedules, model/provider state, path existence, services, and credentials metadata need fresh tool/config/API evidence or must be labeled unverified.
5. **Choose the target layer.** Procedures → skills. Atomic facts → `fact_store`. Long structured context → docs. Always-on bootstrap rules → built-in memory. Raw history/progress → `session_search`.
6. **Mutate only in approved scope.** Use targeted patches; never edit `USER.md`, `MEMORY.md`, or `SOUL.md` without showing an exact diff and receiving explicit approval.
7. **Verify and report.** Re-read changed sections, run the owning audit/CLI/tests, check for generated artifacts, and separate intended findings from unrelated dirty-tree baseline issues.

## Reference Map

Load the specific reference before acting in that sub-domain:

- `references/knowledge-cli.md` — command inventory and read-only contract for the bundled `knowledge` CLI.
- `references/knowledge-cli-maintenance.md` — modifying the CLI/companion skill, regression cases, verification recipe, generated-artifact cleanup, and P3 `memory policy audit` preservation notes.
- `references/knowledge-cli-p2-readonly-audits-2026-05-08.md` — completed P2 pattern for adding deterministic read-only CLI audits (`paths audit`, `skill audit`, `distill worker-check`) and report rollups without turning the CLI into an editor or approval source.
- `references/knowledge-skill-refactor-audit-2026-05-08.md` — audit evidence, P0/P1/P2 roadmap, and prose-to-CLI transfer candidates for this skill.
- `references/distillation.md` — daily/manual session distillation, worker/curator flow, model constraints, output quality gates, verification levels, and JSON schema compliance on Ollama Cloud.
- `references/docs-review.md` — read-only docs audit, pruning, wrong-layer findings, stale-current claims, secret-risk classes.
- `references/memory-hygiene.md` — holographic memory metrics, duplicate/stale fact review, merge/update/remove workflow, tagging conventions, fact↔reality verification.
- `references/memory-refactoring-2026-05.md` — final MEMORY/USER/SOUL composition and over-protection lessons from the 2026-05 refactor.
- `references/plan-governance.md` plus `/home/konstantin/docs/plans/README.md` — plan lifecycle, statuses, archive rules, and control-surface policy.
- `references/local-cli-audit.md` — auditing skill-owned local CLIs, installed wrappers, packaging drift, and redaction boundaries.
- `references/soul-behavioral-constitution.md` — auditing/restoring/editing `~/.hermes/SOUL.md` and prompt-snapshot activation boundary.
- `references/json-schema-benchmark.md` — Ollama Cloud JSON compliance benchmark: `json_schema` vs `json_object` vs plain text, model-by-model results.
- `references/multi-instance-infrastructure.md` — volatile Hermes instance/source/runtime inventory. Re-verify paths/processes before making current-state claims.

## `knowledge` CLI Contract

The bundled CLI is a read-only evidence collector for local knowledge architecture work.

Start commands:

```bash
knowledge --json doctor
knowledge --json report --all
```

Drill-down examples:

```bash
knowledge --json paths audit
knowledge --json docs audit
knowledge --json plans audit
knowledge --json memory metrics
knowledge --json memory policy audit
knowledge --json skill companion
knowledge --json skill audit
knowledge --json distill worker-check
knowledge --json scan secrets --path /home/konstantin/docs
knowledge --json distill candidates --input -
```

Rules:

- CLI output is evidence, not approval to mutate docs, plans, skills, memory, config, cron, or credentials metadata.
- Secret scans must report counts/classes/locations carefully and never preserve or print secret values.
- The CLI should only gain deterministic read-only checks: inventory, path existence, stale-path detection, schema/heading checks, report rollups, generated-artifact checks, and redacted metadata.
- Do not move semantic curator judgment, approval decisions, protected-file edits, or behavioral constitution rules into the CLI.

## Safety Guardrails

- **Audit before mutation.** Gather metrics, read current state, and classify before editing.
- **Mode matters.** Dry-run/review forbids edits. Normal approved maintenance allows scoped docs/skill/plan patches. Benchmark mode may use fixed `/tmp` artifacts but must not mutate durable knowledge unless approved.
- **Protected core files.** `USER.md`, `MEMORY.md`, and `SOUL.md` require explicit user-approved diff before any write.
- **No secrets.** Do not save OAuth tokens, API keys, passwords, cookies, private keys, full auth JSON, tokenized webhook URLs, or sensitive credential paths.
- **No stale production claims.** Freshly verify path/version/commit/config/cache/prompt/runtime state before root-cause, repair, or “current system does X” claims.
- **No silent durable pollution.** Prefer update/replace/skip over add. If it will not matter weeks from now, leave it to `session_search`.
- **No restart/reset while writes are pending.** Complete writes, verify, and report first; only then discuss restart/reset if needed.

## Common Pitfalls

1. Treating docs, `fact_store`, skills, and memory as interchangeable. They are different layers with different retrieval costs and mutation rules.
2. Saving procedures into holographic facts. Procedures belong in skills or runbooks.
3. Duplicating `USER.md`/`SOUL.md` rules into `MEMORY.md`; always check whether a rule is already covered elsewhere.
4. Using one failed search as proof of absence. Retry important lookups with alternate terms and sources.
5. Believing a stale doc over live state. Verify operational claims with tools.
6. Leaving completed plans in root `plans/`. Closed plans go to `archive/<year>/<status>/`.
7. Preserving raw logs, full transcripts, or secret-looking values in docs/plans/skills.
8. Making `knowledge` CLI a mutator. Its safe role is deterministic read-only evidence.
9. Reporting all-repo dirty-tree failures as new regressions. Separate intended files from unrelated baseline changes.
10. Letting tests create `__pycache__`/`.pyc` blockers under skills. Use `PYTHONDONTWRITEBYTECODE=1` and clean generated artifacts before final audit.
11. Hitting tool-call/context limits mid-verification and then phrasing the work as complete. If gates were not run, report `not done`, name the missing gates, and preserve a resume point rather than archiving/closing the plan.
12. Using `ollama run` or `ollama pull` for cloud models with `:cloud` suffix. Use HTTP API; the CLI path can trigger ENOSPC.
13. Treating volatile multi-instance inventory as durable current truth. Re-check paths/processes before saying an instance is active.

## Verification Checklist

- [ ] Relevant reference(s) loaded for the sub-domain.
- [ ] Mode and mutation scope are clear before side effects.
- [ ] `knowledge --json doctor` or another focused read-only evidence command was run when local knowledge state matters.
- [ ] Branch, HEAD, status, and target diff checked before repo/skill edits.
- [ ] Source-of-truth layer chosen explicitly; no duplicate/overlapping durable entries created.
- [ ] Operational current-state claims are tool-verified or labeled as hypotheses.
- [ ] Protected core files were not edited, or exact approved diff is recorded.
- [ ] Secret values and sensitive credential paths are absent from saved content and final report.
- [ ] Changed sections were re-read; duplicate/conflict/stale-path search completed where relevant.
- [ ] `audit_skill.py --skill knowledge-architecture --json` run after skill/reference changes.
- [ ] CLI tests/smokes run with `PYTHONDONTWRITEBYTECODE=1` after CLI-related changes.
- [ ] No generated artifacts remain under the skill tree.
- [ ] If interrupted by tool-call/context limits, final answer explicitly marks the task incomplete, lists missing gates, and leaves the plan unarchived for continuation.
- [ ] Final answer lists touched paths, cause, verification, remaining baseline issues, and commit/push state.
