---
name: knowledge-architecture
description: Maintain Konstantin's personal knowledge architecture — distill sessions into docs, audit/review/prune docs, clean holographic memory, and govern plan lifecycle. Shared layering model, cross-cutting safety rules, and routing to detailed reference workflows.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [memory, knowledge-management, distillation, docs, holographic, fact-store, audit, curation, plans, governance, source-of-truth]
    related_skills: [hermes-agent]
---

# Knowledge Architecture

Maintain Konstantin's personal knowledge base across all durable layers: built-in memory, holographic fact_store, `/home/konstantin/docs/`, skills, and session history.

## Knowledge Layering Model

```
Built-in USER.md / MEMORY.md  ← always-on index + preemptive corrections + self-protection guardrails
Holographic fact_store        ← atomic durable facts, retrieval hooks, trust/helpful scoring
/home/konstantin/docs/        ← human-readable source of truth for operational documentation
Skills                        ← executable repeatable procedures with workflows and pitfalls
session_search                ← detailed history, raw transcripts, temporary progress
```

**Routing rule:** When deciding where knowledge belongs, prefer the smallest layer that serves the need. Procedures → skills. Atomic facts → fact_store. Long structured context → docs. Always-on index → built-in memory. History → session_search.

**MEMORY.md composition principle:** MEMORY contains exactly four types of content, each justified by the "would the agent know to search for this before acting?" test:

1. **Indices** — pointers to where detailed knowledge lives (e.g., `§ Docs: /home/konstantin/docs/ — infrastructure.md, runbooks.md, user-context.md, plans/`). Without these, the agent cannot locate on-demand sources.
2. **Self-protection guardrails** — rules that protect the agent from modifying its own configuration without permission (e.g., `DO-NOT-EDIT`), and rules about the memory architecture itself (e.g., `search before add → update not duplicate, auto_extract = off`). These are self-referential and must be always-on because the agent won't think to load them before the action that violates them. The DO-NOT-EDIT guardrail lives ONLY in MEMORY, not in SOUL — per explicit user decision.
3. **Holographic hygiene** — meta-rules about how to use the memory system itself (search before add, update not duplicate, remove stale, don't save without value). These are self-referential: the agent won't search for rules about how to search.
4. **Known-wrong technical quirks** — concrete technical failures the agent will silently repeat if not reminded every prompt (e.g., `ollama run :cloud = ENOSPC`, `json_schema broken for Ollama Cloud`, `model tags must be exact`). Group multiple known-wrongs into one compound entry to save space.

**What does NOT belong in MEMORY:**
- Facts discoverable via fact_store probe/search (Gmail config, credential paths, n8n setup, model configs, cron schedules)
- Behavioral preferences already in USER.md (language, analysis depth, bare commands, Gmail personal-only, attribution)
- Principles already in SOUL.md (cause attribution, proactive analysis, execution gate, not hoarding dead weight)
- Procedural steps loadable from skills/docs (cron procedures, credential handling, timezone conversions)
- Preferences loadable only when relevant (App Password preference, service account details)
- Invented safety-guardrails not explicitly requested by the user. If a rule is already in USER.md or fact_store, do NOT duplicate it in MEMORY. Do not over-protect the user beyond what they explicitly stated. Example: "Gmail is personal-only" appears in USER.md, user-context.md, and fact_store — adding it to MEMORY is over-protection, not safety.

**Two tests for MEMORY inclusion:**
- **"Would I know to search for this?"** — If the agent would NOT think to search before acting → candidate for MEMORY (self-referential rules, indices, known-wrongs).
- **"Is this already covered elsewhere?"** — If SOUL or USER.md already carries this rule → do NOT duplicate. Duplication wastes tokens without adding safety.

**Canonical destinations within docs:**

| Destination | Content |
|---|---|
| `user-context.md` | User identity, communication contract, durable preferences, work-context hypotheses |
| `infrastructure.md` | Paths, cron metadata, model architecture, recovery instructions |
| `runbooks.md` | Repeatable operational checklists and procedures |
| `plans/*.md` | Multi-step intentions, status, verification criteria |

## Cross-Cutting Rules

These rules apply to ALL knowledge architecture operations — distillation, review, hygiene, and plan governance.

### Read-Only Evidence Collector

For local knowledge architecture work, prefer the installed `knowledge` CLI as the first deterministic evidence-gathering step before proposing edits. Start with `knowledge --json doctor` or `knowledge --json report --all`, then drill into `docs`, `plans`, `memory`, `scan`, or `distill` subcommands as needed. The CLI is read-only by design; its output is evidence, not permission to mutate docs, plans, memory, skills, config, or cron. See `references/knowledge-cli.md` for command inventory, verified paths, verification recipe, and pitfalls.

When the user asks to audit local CLIs or the skill↔CLI layer, use `references/local-cli-audit.md`. It covers `/home/konstantin/code/clis/`, safe smoke checks, packaging/version drift checks, header-redaction checks, and the known `article`/`flights`/`hh-ru`/`knowledge`/`fli` boundaries.

### Safety

1. **Audit before mutation.** Always gather metrics, read current state, and classify before editing.
2. **Separate verified facts from hypotheses.** A tool check is verified. A mocked/unit check verifies implementation shape only; a live smoke verifies endpoint behavior only; production readiness requires production-shaped benchmark evidence.
3. **Never save secrets.** No OAuth tokens, API keys, passwords, cookies, private keys, full auth JSON, or tokenized webhook URLs. Credential **file paths** are also sensitive metadata — store only section references like "(see config)", not actual paths.
4. **Respect mode boundaries.** Read-only/dry-run mode forbids all edits. If the user says "do not edit files", that includes docs, plans, skills, config, memory, and cron.
5. **Conservative edits.** Prefer update/replace/skip over add. Prefer targeted patches over whole-file rewrites. Never delete because something wasn't mentioned today.

### Operational Fact Verification

Claims about external-system permissions, ACLs, OAuth scopes, cron schedules, model pinning, credentials, or write capability must be:
- backed by a fresh tool/API/config check in the current run, OR
- copied from already-verified current doc sections and marked as such, OR
- left out / reported under "Needs user decision".

Never infer permissions from a successful read. Never collapse "not tested" into "not enabled".

### Agent Mistake Handling

When the user corrects the agent, extract the durable behavioral rule — not the incident diary.

Bad: `On 2026-04-27 the assistant created a benchmark plan incorrectly.`
Good: `When the user says not to edit files, treat that as including docs, plans, skills, config, memory, and cron unless explicitly exempted.`

### Mode Declaration

Before any side effects, declare the mode:

| Mode | Allowed | Forbidden |
|---|---|---|
| **Normal** (distillation, approved maintenance) | Read, patch docs conservatively, update plan status, send audit report | Cron/config/credential changes unless explicitly requested |
| **Dry-run / review** | Read, report proposals, `/tmp` scratch only | Editing docs, plans, skills, config, memory, cron, credentials |
| **Benchmark** | Fixed `/tmp` files, final comparison | Editing docs/plans/skills/config/memory/cron, storing rankings as durable facts before review |

## Sub-Domain Workflows

This skill routes to four detailed workflows, each stored as a reference file. Load the relevant reference for full procedures, pitfalls, and checklists.

### 1. Daily Knowledge Distillation → `references/distillation.md`

Turn recent Hermes conversations into compact, curated, file-backed knowledge. For scheduled cron or manual "distill/actualize docs" requests.

**Key trigger words:** distill, выжать знания, актуализировать docs, update/actualize docs, daily cron.

**Quick reference:**
- Read `/home/konstantin/docs/README.md` and target files first.
- Source budget: 8k–12k chars, hard cap 15k.
- Candidate quality gate: Will this matter weeks from now? Is evidence direct/verified? Will it prevent a future mistake?
- Two-tier ensemble: 2 Ollama Cloud workers (glm-5.1 and gemma4:31b) extract candidates; gpt-5.5 curator makes final decisions. DeepSeek V4 Pro is excluded from the production pool unless re-benchmarked and explicitly approved.
- Use `json_object` mode + explicit enums in prompts (NOT `json_schema` — broken for cloud models). See `references/json-schema-benchmark.md`.
- Worker script: `scripts/distillation_worker.py`.
- Verification wording for worker/model changes: distinguish implemented, unit/mocked, live smoke, and production-shaped benchmark. See `references/verification-claims-2026-05-07.md`.
- DeepSeek native Ollama benchmark lesson: do not blame the model when settings fail. Native `/api/chat` + `think:false` fixes hidden reasoning; a concise output contract (`max 10 candidates`, short claim/reason) fixed visible JSON truncation and passed repeated production-shaped runs even at `num_predict=3000`. See `references/deepseek-native-distillation-benchmark-2026-05-07.md`.
- NEVER use `ollama run` / `ollama pull` for cloud models (`:cloud` suffix) — causes ENOSPC crash.
- Memory architecture: see `references/memory-refactoring-2026-05.md` for the 2026-05 refactoring session details, final MEMORY/USER/SOUL composition, and lessons on over-protection anti-patterns.
- SOUL as behavioral constitution: see `references/soul-behavioral-constitution.md` before auditing/restoring/editing `~/.hermes/SOUL.md`; it captures the 2026-05 restoration, required invariants, and prompt-snapshot activation boundary.

### 2. Docs Review → `references/docs-review.md`

Audit, review, prune, or reorganize `/home/konstantin/docs/` as a curated knowledge base. Default to read-only analysis.

**Key trigger words:** review, audit, clean, prune, compact, reorganize, validate docs.

**Quick reference:**
- Default mode: read-only review. Produce findings and proposed actions.
- Classify findings: stale_current_claim, duplicate_with_skill, duplicate_with_holographic, wrong_layer, unresolved_open_question, plan_status_drift, dead_log, secret_risk, missing_index.
- Compare against `fact_store` when overlap matters; use `fact_feedback` on facts that were helpful.
- Verify live state for operational claims before reporting as current.
- Cross-layer edits require the relevant skill loaded first.

### 3. Holographic Memory Hygiene → `references/memory-hygiene.md`

Audit, clean, deduplicate, or maintain Hermes' holographic memory (`fact_store`). Produce metrics first; only mutate after explicit permission.

**Key trigger words:** analyze memory, memory metrics, clean memory, deduplicate, prune memory, fact_store audit.

**Quick reference:**
- Check provider: `hermes memory status` + config. Verify `auto_extract` state.
- Collect SQLite metrics: fact count, categories, trust/helpful stats, FTS consistency.
- MEMORY.md composition: only indices, self-protection guardrails, and preemptive corrections. See pitfall #12 for the detailed test.
- **Anti-pollution principle:** write only facts with durable value. Immediately update or remove stale facts. If you wouldn't look for this fact in a week, don't save it. A well-maintained memory never needs a batch cleanup.
- **Core agent files guardrail:** MEMORY.md, USER.md, and SOUL.md must not be edited without explicit user permission. When requesting permission, show the proposed diff. These are first-class guardrails that must not drift.
- Use `fact_store search/probe/reason/contradict` for cluster discovery.
- Classify actions: keep, update, merge, remove, promote_to_builtin, demote_to_docs, promote_to_skill, leave_to_session_search.
- Canonical merge pattern: keep highest helpful_count/trust_score fact, update it, remove weaker duplicates, verify with search.
- **Anti-pollution:** when adding facts, ask "would I look for this in a week?" If not, skip it. Stale facts → update/remove immediately. The goal is never needing a batch cleanup.
- **Core agent files:** MEMORY.md, USER.md, and SOUL.md must not be edited without explicit user permission. Show diff when requesting. These files are first-class guardrails.
- `retrieval_count` may stay zero — treat as unverified.
- After using facts, call `fact_feedback` on each actually-used fact.

### 4. Plan Governance → `references/plan-governance.md`

Create, update, close, archive, or review durable multi-step plans for Konstantin. Thin procedural hook — full policy is in `/home/konstantin/docs/plans/README.md`.

**Key trigger words:** create plan, update plan, close plan, archive plan, plan status.

**Quick reference:**
- ALWAYS read `/home/konstantin/docs/plans/README.md` before mutating plan state.
- Default path: `/home/konstantin/docs/plans/YYYY-MM-DD-short-topic.md`.
- Root contains only `README.md` + active (planned/in_progress/blocked) plans.
- Closed plans → `archive/<year>/<done|cancelled|superseded>/`.
- Status must be machine-readable: `Current status: in_progress`.
- Plans are control surface and audit trail. Durable knowledge → promote to docs/skills/holographic.
- Do not duplicate the canonical policy in this skill.

## Multi-Instance Infrastructure

Konstantin runs **two Hermes instances** on the same machine. Skills, memory, and config are **not shared**.

| Instance | Data Path | Process | Skill source |
|---|---|---|---|
| **Main** | `/home/konstantin/.hermes/` | `hermes_cli gateway` | `/home/konstantin/.hermes/skills/` |
| **Guest** | `/home/konstantin/hermes-instances/guest/data/` | Docker `hermes-guest` + `hermes-guest-dashboard` | `/home/konstantin/hermes-instances/guest/data/skills/` |

**Key skill differences (as of 2026-05):**
- Guest-only: `apple/` (apple-notes, apple-reminders, findmy, imessage), `domain/`, `inference-sh/`, `diagramming/`, `travel-planning` (with `references/abkhazia.md`)
- Main-only: `flight-search-routing`, `knowledge-architecture`, `holographic-memory-hygiene`, `docs-review`, `daily-knowledge-distillation`, `konstantin-plan-governance`

**Pitfall:** When a user asks "where is skill X?" and it's not in `skills_list`, check the guest instance tree before concluding it doesn't exist. `skills_list` only shows the current instance.

## Cross-Domain Pitfalls

1. **Docs and holographic are different layers.** Docs hold structured operational knowledge; holographic holds atomic facts and retrieval hooks. Don't treat them as substitutes.
2. **Don't move procedures into holographic facts.** Long procedures belong in skills or runbooks, not fact_store.
3. **Don't delete completed plans because they're "old".** Done/superseded plans are audit trail. Archive, don't destroy.
4. **Don't believe a stale doc over live state.** Verify operational claims with tools before reporting as current.
5. **Don't use one search query as proof of absence.** Both file search and fact_store search can miss terms; use alternate queries for important conclusions.
6. **Don't over-normalize uncertainty.** Mark hypotheses and open questions; don't convert them to confident facts.
7. **Silent mutation is forbidden.** All edits to docs, memory, skills, config, cron must be reported.
8. **Don't save session history into docs.** Use `session_search` for history; docs get distilled durable knowledge.
9. **Credential paths leak metadata.** Even paths can reveal operational shape. Store minimal references.
10. **Never use `ollama run` / `ollama pull` for cloud models** — causes ENOSPC on small disks. Cloud models use HTTP API only.
11. **Cross-file deduplication cuts both ways.** When one doc file has a procedure and another has the same factual claims, keep the procedure in runbooks and keep only the invariant/map/factual summary in infrastructure. Don't maintain two copies of the same operational knowledge. When cleaning up, infrastructure.md = "what/where/invariants", runbooks.md = "how/checklists/pitfalls".
12. **MEMORY.md composition: only indices, self-protection guardrails, holographic hygiene, and known-wrong quirks.** Behavioral preferences live in USER.md. Principles live in SOUL.md. Procedures live in skills/docs. Facts live in fact_store. When auditing MEMORY, ask: "if the agent removed this line, would it (a) silently repeat a concrete technical failure, break a self-referential rule, or lose the only pointer to docs, or (b) just mean a slower path via on-demand lookup?" If (b), it doesn't belong in always-on. Guard against two anti-patterns: (1) over-protectiveness — don't pad MEMORY with rules already covered by SOUL or USER; (2) invented guardrails — if the user didn't explicitly request a rule and it's already in USER.md/fact_store, don't add it to MEMORY. Example: "Gmail is personal-only" is in USER.md, user-context.md, and fact_store — a fourth copy in MEMORY is over-protection, not safety.
13. **Core agent files guardrail.** MEMORY.md, USER.md, and SOUL.md must not be edited without explicit user permission. When requesting permission, show the proposed diff. Other files (docs, plans, skills, config, fact_store, cron, credentials) also require permission but the core agent config files are especially sensitive — the user treats them as first-class guardrails that must not drift.
14. **No restart during pending mutations.** `/restart` and `/reset` are forbidden while a session has unresolved write operations (files, memory, fact_store, cron, config). Instead: complete all steps, report what was done, then ask the user to confirm the restart. External crashes (OOM, OS signal, provider timeout) are the only exception — the agent cannot control those. This applies to ALL mutations, not just MEMORY/USER/SOUL.
14. **Anti-pollution over batch cleanup.** Memory should be a curated library, not an attic. Write only facts with durable value; immediately update or remove facts that go stale. A well-maintained memory never needs a batch cleanup session. If you wouldn't look for this fact in a week, don't save it.

## Verification Checklist (All Domains)

- [ ] Mode declared before side effects.
- [ ] Current state read before evaluation.
- [ ] Source-of-truth boundaries evaluated across layers.
- [ ] Operational current-state claims verified with tools or labeled as unverified.
- [ ] Findings distinguish verified facts from expert hypotheses.
- [ ] No duplicate/overlapping entries created.
- [ ] No secrets, raw logs, or token-like values saved.
- [ ] Changes are targeted patches, not blind appends or whole-file rewrites.
- [ ] After edits, changed sections re-read and duplicate/conflict search performed.
- [ ] Final answer includes compact conclusion and exact changed/proposed paths.