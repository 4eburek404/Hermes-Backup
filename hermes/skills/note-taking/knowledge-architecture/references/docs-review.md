# Docs Review — Detailed Workflow

Audit `/home/konstantin/docs/` as a curated, file-backed operational knowledge base.

## Default Stance: Read-Only Review First

Editing docs, skills, built-in memory, holographic memory, cron, config, or credentials changes long-term state and requires either a direct user request or explicit approval after an audit report.

## Execution Modes

### Read-only review (default)

Allowed: read docs, inspect structure, search duplicates/stale sections, compare against fact_store/skills/config/cron, produce findings and proposed actions.
Forbidden: editing docs/plans/skills/config/memory/cron/credentials.

### Approved docs maintenance

Use only when the user directly asks to update/clean docs or approves the proposed patch list.
Allowed: targeted edits to `/home/konstantin/docs/`, plan status updates with evidence, small structure fixes, removing duplicated/obsolete content after preserving canonical source of truth.
Still forbidden unless separately requested: changing cron, config, credentials, migrating large content into holographic memory, rewriting all docs from scratch.

### Cross-layer maintenance

Use only when the user explicitly asks to reconcile docs with holographic memory/skills/built-in memory. Follow the relevant skill before mutation:
- `holographic-memory-hygiene` (→ `references/memory-hygiene.md`) before `fact_store update/remove/add`
- `daily-knowledge-distillation` (→ `references/distillation.md`) before distilling session knowledge into docs
- `hermes-agent` before Hermes config/provider/tool changes

## Review Workflow

### 1. Read the docs index first

Start with:
```
/home/konstantin/docs/README.md
/home/konstantin/docs/user-context.md
/home/konstantin/docs/infrastructure.md
/home/konstantin/docs/runbooks.md
/home/konstantin/docs/plans/README.md
```

Read relevant plan files only when the task mentions that area or when plan status/staleness is part of the review.

### 2. Inventory files and structure

Collect: list of markdown files, char/line counts, headings up to level 3, plan statuses, recently modified files, unusually large files, obvious archive/superseded/done plans. Use tools rather than guessing.

### 3. Check source-of-truth boundaries

For each major section:
1. Is this fact/procedure/plan in the right layer?
2. Is the section duplicating a skill or holographic fact without adding human-readable value?
3. Does the document clearly say whether a claim is stable, current, historical, a hypothesis, or an open question?
4. Is there a canonical source if docs and memory disagree?
5. Does a procedure belong in a skill instead of docs?
6. Does a fact belong in holographic as a short pointer instead of only in docs?
7. Does a completed plan need status cleanup or archival labeling rather than deletion?

### 4. Compare with holographic memory when relevant

Use `fact_store list/search/probe/reason` to compare high-signal areas only. Good comparison clusters: `Gmail OR Calendar OR Himalaya`, `cron OR model pinning OR language`, `Daily OR knowledge OR distillation OR gpt`, `holographic OR fact_store OR auto_extract`, `n8n OR Docker OR 5678`, `plans OR permission OR workflow`.

Known caveat: single `fact_store search` can miss hyphen-heavy terms (`gpt-5.5`, model tags). Use alternate queries plus `fact_store list` or SQLite for important absence conclusions.

After using facts, call `fact_feedback` on facts that were actually useful and accurate.

### 5. Check live state for operational claims

Freshly verify before updating or reporting as current: cron schedules, job IDs, delivery targets, pinned models/providers, Hermes config, provider names, model availability, filesystem paths, installed commands, Google Calendar ACLs/scopes, Gmail/Himalaya behavior, credentials presence/shape (without printing values), running services/ports/processes.

If not verified, label as "documented earlier" or "needs verification".

### 6. Detect docs issues

Classify findings:

| Class | Meaning | Typical action |
|---|---|---|
| stale_current_claim | A "current" operational claim may no longer be true | Verify live state, update or mark historical |
| duplicate_with_skill | Docs repeat a procedure now encoded in a skill | Replace with short pointer, if approved |
| duplicate_with_holographic | Docs and facts overlap | Keep docs as source of truth if long/procedural; keep fact as pointer/summary |
| wrong_layer | Content belongs in skill/holographic/session_search/plans instead | Move/summarize after approval |
| unresolved_open_question | Open question has been answered by later work | Update question/status/rationale |
| plan_status_drift | Plan status/checklists do not match completed work | Update status with evidence |
| dead_log | Raw logs/history/transcripts are in docs | Remove or distill to stable rule |
| secret_risk | Token/password/API key/credential path leaked | Redact immediately if allowed; otherwise report urgent finding |
| missing_index | README/index does not point to canonical location | Add/update index row |

High-value checks from real reviews:
- **Cross-file deduplication.** The most common docs sprawl pattern: infrastructure.md accumulates procedural steps, credential-shape examples, pitfall lists, and output templates that duplicate runbooks. When cleaning: infrastructure.md keeps only "what exists, where it lives, what invariants hold"; runbooks.md keeps "how to do it, pitfalls, checklists". If a section has step-by-step commands or "Known pitfalls:", it probably belongs in runbooks. If infrastructure.md has a WMO-code table or output template, it belongs in the cron prompt or skill — not in the infrastructure map.
- **Benchmark runbook merging.** If multiple runbook sections share the same general method (e.g., "benchmark models for weather" vs "benchmark models for distillation"), merge into one unified section with a results table. The method is the same; only the results differ.
- **MEMORY pressure from doc-content duplication.** Built-in MEMORY entries often repeat rules already captured in docs/runbooks (timezone, do-not-edit, holographic hygiene, plan governance). After a docs cleanup, audit MEMORY: remove any entry whose full content exists in docs/runbooks/infrastructure. MEMORY should hold only always-on pointers and rules not found in any doc file.
- Compare `infrastructure.md` cron rows against live `cronjob list`, especially `enabled_toolsets`; small differences are real operational drift.
- Search `user-context.md` for "Open questions" that later work has resolved. Close them as decisions.
- When a runbook section has a dedicated skill, keep short pointer/rationale in `runbooks.md` and treat skill as canonical for execution details.
- Normalize plan status conventions: prefer consistent `Current status:` field.
- For plans cleanup: root contains only `README.md` plus active `planned|in_progress|blocked` plans; closed plans move to `archive/<year>/<done|cancelled|superseded>/`.
- Treat credential file paths as possible metadata leakage. Prefer "stored in protected config/credentials area; exact path intentionally not documented".

### 7. Produce an action plan before mutation

For each proposed edit include: file path, section/heading, action (`keep`/`update`/`remove`/`move_to_skill`/`move_to_holographic`/`leave_to_session_search`/`verify_live_state`/`archive_plan`), rationale, evidence source, risk if left unchanged, whether approval is needed.

Prefer conservative targeted patches. Avoid whole-file rewrites unless structure is fundamentally broken.

## Editing Protocol

When edits are approved:
1. Re-read the exact target section immediately before patching
2. Apply the smallest targeted patch
3. Re-read the changed section
4. Search for duplicate/conflicting text across `/home/konstantin/docs/`
5. Verify no secrets, raw logs, or token-like strings were introduced
6. If the edit changes source-of-truth boundaries, consider whether a short holographic pointer needs update (but follow `references/memory-hygiene.md` before mutating facts)
7. Report exact files and sections changed

## Docs-Review Pitfalls

1. Treating docs and holographic as substitutes. They are different layers.
2. Deleting completed plans because they are "old". Done/superseded plans are audit trail. Prefer status/archive labeling.
3. Believing a stale doc over live state. Verify before reporting as current.
4. Moving procedures into holographic facts. Long procedures belong in skills or runbooks.
5. Letting runbooks duplicate skills forever. If a skill becomes canonical, docs should keep a short pointer.
6. Using one search query as proof of absence. Use alternate queries for important conclusions.
7. Over-normalizing uncertainty. Mark hypotheses and open questions; don't convert them to confident facts.
8. Silent mutation. All edits must be clearly reported.
9. Saving session history into docs. Use `session_search` for history; docs get distilled knowledge.
10. Credential path leakage. Even paths can reveal operational shape. Store minimal references.