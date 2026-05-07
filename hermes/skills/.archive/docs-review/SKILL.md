---
name: docs-review
description: Use when auditing, reviewing, pruning, or reorganizing /home/konstantin/docs/ as a curated file-backed knowledge base. Default to read-only analysis first; classify findings by source-of-truth layer, staleness, duplication with holographic memory/skills, and proposed conservative edits.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [docs, memory, knowledge-management, audit, curation, source-of-truth]
    related_skills: [daily-knowledge-distillation, holographic-memory-hygiene, hermes-agent]
---

# Docs Review

## Overview

Use this skill to audit `/home/konstantin/docs/` as a curated, file-backed operational knowledge base. The goal is not to make the docs larger. The goal is to keep them accurate, structured, non-duplicative, recoverable, and clearly separated from other memory layers.

Current intended memory architecture:

- **Built-in `USER.md` / `MEMORY.md`**: compact always-injected index and critical behavioral rules.
- **Holographic `fact_store`**: atomic durable facts, user preferences, cross-domain recall, trust/helpful scoring, and pointers to source-of-truth docs/skills.
- **`/home/konstantin/docs/`**: human-readable source of truth for operational documentation: infrastructure maps, runbooks, plans, rationale, open questions, recovery instructions, and structured context.
- **Skills**: executable repeatable procedures with exact workflows and pitfalls.
- **`session_search`**: detailed history, raw transcripts, command outputs, and temporary progress.

Default stance: **read-only review first**. Editing docs, skills, built-in memory, holographic memory, cron, config, or credentials changes long-term state and requires either a direct user request to mutate or an explicit approval after an audit report.

## When to Use

Use when the user asks to:

- review, audit, clean, prune, compact, reorganize, or validate `/home/konstantin/docs/`;
- decide whether a note belongs in docs, holographic memory, built-in memory, a skill, a plan, or `session_search`;
- check whether docs are stale, duplicated, contradictory, overgrown, or missing source-of-truth boundaries;
- compare docs with current Hermes/holographic memory/skills/cron/config state;
- prepare proposed edits before updating docs;
- maintain `/home/konstantin/docs/` after knowledge-distillation runs.

Do **not** use for:

- daily session distillation into docs — use `daily-knowledge-distillation`;
- `fact_store` cleanup as the primary task — use `holographic-memory-hygiene`;
- general Hermes setup/debugging without a docs-audit component — use `hermes-agent` and relevant operational skills;
- blind rewriting, archival dumping, or “make it pretty” edits without an evidence-backed review.

## Execution Modes

Declare the mode before side effects.

### Read-only review

Use by default. Allowed:

- read docs;
- inspect headings, status markers, sizes, and cross-file references;
- search for duplicates/stale sections;
- compare against `fact_store`, skills, config, cron metadata, or live files when relevant;
- produce findings and proposed actions.

Forbidden:

- editing docs/plans/skills/config/memory/cron/credentials;
- adding/removing holographic facts;
- sending messages outside the current response.

### Approved docs maintenance

Use only when the user directly asks to update/clean docs or approves the proposed patch list. Allowed:

- targeted edits to `/home/konstantin/docs/`;
- plan status updates with evidence;
- small structure fixes and stale-question updates;
- removing duplicated or obsolete docs content after preserving canonical source of truth.

Still forbidden unless separately requested:

- changing cron jobs;
- changing Hermes config;
- changing credentials;
- migrating large docs content into holographic memory;
- rewriting all docs from scratch.

### Cross-layer maintenance

Use only when the user explicitly asks to reconcile docs with holographic memory/skills/built-in memory. Follow the relevant skill immediately before mutation:

- `holographic-memory-hygiene` before `fact_store update/remove/add`;
- `daily-knowledge-distillation` before distilling session knowledge into docs;
- `hermes-agent` before Hermes config/provider/tool changes.

## Canonical Destinations

Route findings by knowledge type:

| Knowledge type | Destination | Notes |
|---|---|---|
| Always-needed preference or critical behavioral guardrail | built-in memory | Keep tiny; declarative facts only. |
| Atomic durable fact or cross-domain recall hook | holographic `fact_store` | Search before add; prefer update over duplicate. |
| Infrastructure map, paths, cron metadata, model architecture, recovery instructions | `docs/infrastructure.md` | Verify live state for current operational claims. |
| Repeatable but short operational checklist | `docs/runbooks.md` | Promote to skill if frequent/risky/long. |
| Executable repeated procedure with pitfalls | skill | Keep runtime protocol in skill; docs may link/summarize. |
| Multi-step intention, work plan, status, verification criteria | `docs/plans/*.md` | Plans are control surface, not general memory. |
| User identity, communication contract, durable work-domain hypotheses | `docs/user-context.md` | Mark hypotheses as hypotheses. |
| Detailed conversation history, raw logs, command outputs, one-off progress | `session_search` | Do not copy into docs unless distilled. |

## Review Workflow

Reference: `references/2026-04-30-docs-sprawl-audit.md` captures the latest docs-sprawl inventory and cleanup plan seed.

### 1. Read the docs index first

Start with:

```text
/home/konstantin/docs/README.md
/home/konstantin/docs/user-context.md
/home/konstantin/docs/infrastructure.md
/home/konstantin/docs/runbooks.md
/home/konstantin/docs/plans/README.md
```

Read relevant plan files only when the task mentions that area or when plan status/staleness is part of the review.

### 2. Inventory files and structure

Collect:

- list of markdown files;
- char/line counts;
- headings up to level 3;
- plan statuses (`Current status`, `Status`, checkbox counts);
- recently modified files;
- unusually large files;
- obvious archive/superseded/done plans.

Use tools rather than guessing. A compact Python inventory is often best.

### 3. Check source-of-truth boundaries

For each major section ask:

1. Is this fact/procedure/plan in the right layer?
2. Is the section duplicating a skill or holographic fact without adding human-readable value?
3. Does the document clearly say whether a claim is stable, current, historical, a hypothesis, or an open question?
4. Is there a canonical source if docs and memory disagree?
5. Does a procedure belong in a skill instead of docs?
6. Does a fact belong in holographic as a short pointer instead of only in docs?
7. Does a completed plan need status cleanup or archival labeling rather than deletion?

### 4. Compare with holographic memory when relevant

Use `fact_store list/search/probe/reason` to compare only high-signal areas, not every word. Good comparison clusters:

```text
Gmail OR Calendar OR Himalaya
cron OR model pinning OR language
Daily OR knowledge OR distillation OR gpt
holographic OR fact_store OR auto_extract
n8n OR Docker OR 5678
plans OR permission OR workflow
```

Known caveat: a single `fact_store search` can miss facts with hyphen-heavy terms (`gpt-5.5`, model tags). If absence matters, verify with alternate queries plus `fact_store list` or SQLite.

After using facts to decide, call `fact_feedback` on facts that were actually useful and accurate.

### 5. Check live state for operational claims

Do not treat docs as proof of current state for volatile operational claims. Freshly verify before updating or reporting as current:

- cron schedules, job IDs, delivery targets, pinned models/providers;
- Hermes config, provider names, model availability;
- filesystem paths and installed command versions;
- Google Calendar ACLs/scopes and Gmail/Himalaya behavior;
- credentials presence/shape, without printing secret values;
- running services/ports/processes.

If not verified, label as “documented earlier” or “needs verification”.

### 6. Detect docs issues

Classify findings:

| Class | Meaning | Typical action |
|---|---|---|
| stale_current_claim | A “current” operational claim may no longer be true. | Verify live state, then update or mark historical. |
| duplicate_with_skill | Docs repeat a procedure now encoded in a skill. | Replace long procedure with short pointer, if approved. |
| duplicate_with_holographic | Docs and facts overlap. | Keep docs as source of truth if long/procedural; keep fact as pointer/summary. |
| wrong_layer | Content belongs in skill/holographic/session_search/plans instead. | Move/summarize after approval. |
| unresolved_open_question | Open question has been answered by later work. | Update question/status/rationale. |
| plan_status_drift | Plan status/checklists do not match completed work. | Update status with evidence. |
| dead_log | Raw logs/history/transcripts are in docs. | Remove or distill to stable rule. |
| secret_risk | Token/password/API key/credential path leaked. | Redact immediately if allowed; otherwise report urgent finding. |
| missing_index | README/index does not point to canonical location. | Add/update index row. |

Observed high-value checks from real docs reviews:

- **Cross-file deduplication.** The most common docs sprawl pattern: infrastructure.md accumulates procedural steps, credential-shape examples, pitfall lists, and output templates that duplicate runbooks. When cleaning: infrastructure.md keeps only "what exists, where it lives, what invariants hold"; runbooks.md keeps "how to do it, pitfalls, checklists". If a section has step-by-step commands or "Known pitfalls:", it probably belongs in runbooks. If infrastructure.md has a WMO-code table or output template, it belongs in the cron prompt or skill — not in the infrastructure map.
- **Benchmark runbook merging.** If multiple runbook sections share the same general method (e.g., "benchmark models for weather" vs "benchmark models for distillation"), merge into one unified section with a results table. The method is the same; only the results differ.
- **MEMORY compression guardrail.** After a docs cleanup, audit MEMORY for duplication with docs/runbooks. Remove descriptive content that lives verbatim in docs, but **keep always-on behavioral guardrails and safety rules** — even if they duplicate docs. Rules like "do not edit files", "pasted tokens = compromised", "search before add" are always-on constraints that must be in every prompt. Removing them from MEMORY because "it's in runbooks" is a mistake: the agent won't read runbooks on every turn. Only remove: factual pointers, procedural steps, descriptive context that's easy to find by reading the relevant file.
- Compare `infrastructure.md` cron rows against live `cronjob list`, especially `enabled_toolsets`; small differences such as a missing `web` toolset are real operational drift.
- Search `user-context.md` for "Open questions" that later work has resolved. Close them as decisions instead of leaving them as active uncertainty.
- When a runbook section now has a dedicated skill, keep a short pointer/rationale in `runbooks.md` and treat the skill as canonical for execution details.
- Normalize plan status conventions over time. Mixed `**Status:** done ✓`, `Current status: done`, and unstructured execution notes are readable but harder to audit automatically; prefer a consistent `Current status:` field for new/updated plans.
- For `/home/konstantin/docs/plans/` cleanup, prefer an active-root/archive model rather than destructive deletion: root contains only `README.md` plus active `planned|in_progress|blocked` plans; closed plans move to `archive/<year>/<done|cancelled|superseded>/`; completed plans are audit trail, not current source of truth.
- Treat credential **file paths** as possible metadata leakage. If a path is not operationally necessary in docs, prefer "stored in protected config/credentials area; exact path intentionally not documented".
- If docs review surfaces a stale holographic fact, report it as a candidate for `holographic-memory-hygiene`; do not mutate `fact_store` during read-only docs review unless the user explicitly authorizes cross-layer cleanup.

### 7. Produce an action plan before mutation

For each proposed edit include:

- file path;
- section/heading;
- action: `keep`, `update`, `remove`, `move_to_skill`, `move_to_holographic`, `leave_to_session_search`, `verify_live_state`, `archive_plan`;
- rationale;
- evidence source;
- risk if left unchanged;
- whether approval is needed.

Prefer conservative targeted patches. Avoid whole-file rewrites unless structure is fundamentally broken.

## Editing Protocol

When edits are approved:

1. Re-read the exact target section immediately before patching.
2. Apply the smallest targeted patch.
3. Re-read the changed section.
4. Search for duplicate/conflicting text across `/home/konstantin/docs/`.
5. Verify no secrets, raw logs, or token-like strings were introduced.
6. If the edit changes source-of-truth boundaries, consider whether a short holographic pointer needs update — but follow `holographic-memory-hygiene` before mutating facts.
7. Report exact files and sections changed.

## Secrets and Privacy

Never save or reveal:

- OAuth tokens;
- API keys;
- passwords;
- cookies;
- private keys;
- full credential JSON;
- tokenized webhook URLs;
- raw auth command outputs.

Credential file paths can also be sensitive metadata. Prefer “see config” or a section reference unless the path is already intentionally documented and operationally necessary. If a secret is found in docs, treat it as urgent: report path/section and propose redaction; do not reproduce the value.

## Recommended Report Format

```markdown
## Docs Review

### Mode
read-only | approved maintenance | cross-layer maintenance

### Sources checked
- docs files: ...
- fact_store queries: ...
- skills loaded: ...
- live checks: ...

### Verified facts
- ...

### Findings
| Class | File/section | Finding | Evidence | Proposed action |
|---|---|---|---|---|
| ... | ... | ... | ... | ... |

### Layering assessment
- Built-in memory: ...
- Holographic: ...
- Docs: ...
- Skills: ...
- Session history: ...

### Proposed edits
- `path`: action, reason, approval needed?

### Risks / limitations
- ...

### Compact conclusion
- ...
```

## Common Pitfalls

1. **Treating docs and holographic as substitutes.** They are different layers. Docs hold structured operational knowledge; holographic holds atomic facts and retrieval hooks.
2. **Deleting completed plans because they are “old”.** Done/superseded plans can be audit trail. Prefer status/archive labeling unless they contain clutter or sensitive data.
3. **Believing a stale doc over live state.** Operational claims need verification before being reported as current.
4. **Moving procedures into holographic facts.** Long procedures belong in skills or runbooks, not fact_store.
5. **Letting runbooks duplicate skills forever.** If a skill becomes canonical, docs should usually keep a short pointer and rationale.
6. **Using one search query as proof of absence.** Both file search and fact_store search can miss terms; use alternate queries for important conclusions.
7. **Over-normalizing uncertainty.** Mark hypotheses and open questions; do not convert them into confident facts.
8. **Silent mutation.** Docs edits, memory edits, skill edits, and cron/config changes must be clearly reported.
9. **Saving session history into docs.** Use `session_search` for history; docs get distilled durable knowledge.
11. **Over-correcting into meta-policy.** When a user corrects an approach, do not automatically add a long prohibition/rail to docs or skills. Capture the minimal reusable procedure, command, or pitfall. If the cause is not verified, mark it as a hypothesis or leave it out.

## Verification Checklist

- [ ] Mode declared before side effects.
- [ ] `docs/README.md` read before evaluating structure.
- [ ] Relevant docs files read directly; no conclusions from memory alone.
- [ ] Inventory collected: files, sizes, headings, statuses where relevant.
- [ ] Source-of-truth boundaries evaluated across built-in memory, holographic, docs, skills, and session history.
- [ ] Holographic comparison used when memory overlap matters, with feedback on used facts.
- [ ] Operational current-state claims verified with tools or labeled as unverified/historical.
- [ ] Findings distinguish verified facts from expert hypotheses.
- [ ] Proposed edits are targeted and include rationale/evidence/risk.
- [ ] No docs/memory/skill/config/cron mutation occurred in read-only mode.
- [ ] After approved edits, changed sections were re-read and duplicate/conflict search was performed.
- [ ] Final answer includes compact conclusion and exact changed/proposed paths.

## Success Standard

A successful docs review makes the knowledge base more trustworthy, not necessarily smaller. The best outcome may be “no edits needed” plus a clear source-of-truth map. When edits are needed, they should reduce future ambiguity: fewer stale claims, clearer boundaries, better pointers, and less duplicated procedure text.
