---
name: holographic-memory-hygiene
description: Use when auditing, cleaning, deduplicating, or maintaining Hermes holographic memory. Produce metrics first, separate verified facts from hypotheses, and only mutate fact_store after explicit permission or clear user instruction.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [memory, holographic, hygiene, fact-store, audit, deduplication]
    related_skills: [hermes-agent, daily-knowledge-distillation]
---

# Holographic Memory Hygiene

## Overview

Use this skill to audit and maintain Hermes' `holographic` memory provider: facts in `fact_store`, entity links, trust scores, FTS/SQLite state, built-in memory pressure, duplicates, stale operational claims, and unsafe memory patterns.

The goal is not to maximize the number of facts. The goal is a compact, high-signal, auditable memory system where durable facts live in the right layer:

- **Built-in `USER.md` / `MEMORY.md`**: tiny critical index and high-priority preferences.
- **Holographic `fact_store`**: durable facts and entity-linked recall.
- **Skills**: procedures, workflows, checklists, reusable commands.
- **Docs**: long-form stable context and runbooks.
- **`session_search`**: detailed past-task history and transient progress.

Default stance: **read-only audit first**. `fact_store update/remove/add` changes long-term state and needs either explicit user permission or a direct user request to perform cleanup.

## When to Use

Use when the user asks to:

- analyze holographic memory;
- show memory metrics;
- clean, deduplicate, prune, merge, or compact memory;
- audit or revise built-in `USER.md` / `MEMORY.md` as part of memory architecture hygiene;
- audit or revise `SOUL.md` when the change concerns memory protocol, knowledge-layer boundaries, skill-loading behavior, or agent self-correction rules;
- investigate stale facts, contradictions, bad recall, missing recall, or memory bloat;
- decide whether something belongs in built-in memory, holographic memory, docs, session history, `SOUL.md`, or a skill;
- maintain daily/weekly memory hygiene as a recurring operation.

Do **not** use for:

- normal task execution where no memory architecture or hygiene question is involved;
- writing arbitrary new user facts without first following the `fact_store search → update/add` protocol;
- bulk destructive cleanup without a clear audit report and explicit approval.

## Safety Rules

1. **Audit before mutation.** Gather metrics, clusters, and candidate actions before changing facts.
2. **Separate verified facts from hypotheses.** A SQLite count is verified. A semantic duplicate cluster is an expert hypothesis until reviewed.
3. **Never delete only because `trust_score == 0.5`.** New or rarely-used facts naturally sit at baseline trust.
4. **Do not treat `contradict=[]` as proof of no duplicates.** It only means no explicit contradictions were detected.
5. **Do not rely on `retrieval_count` until verified.** In the current setup it may remain zero even after search/probe/reason. Prefer `helpful_count`, `trust_score`, timestamps, and manual relevance review.
6. **Procedures belong in skills, not memory facts.** If a fact says how to perform a recurring workflow, consider promoting it to a skill and replacing the fact with a short pointer if needed.
7. **Operational claims need freshness.** Credentials, ACLs, scopes, cron model pinning, write permissions, service status, and current model availability should be reverified with tools before being reported as current truth.
8. **Backups can preserve leaks.** When editing built-in memory or `SOUL.md`, make a backup when appropriate, but include the backup directory in secret/credential-path scans and redact backup copies too; otherwise the active file can be clean while sensitive metadata remains in backups.
9. **Respect no-edit / dry-run requests.** If the user asks for analysis only, do not write docs, skills, memory, cron, or config.

## Instruction update workflow for USER.md / MEMORY.md / SOUL.md

Use this when the user asks to “update instructions”, “change memory”, or decide what belongs in `USER.md`, `MEMORY.md`, and `SOUL.md`.

1. Start read-only: load current `USER.md`, `MEMORY.md`, `SOUL.md`, relevant facts, and any skill that governed the session.
2. Propose layer-specific actions before editing: `add`, `update`, or `no change` for each file. A no-op for `MEMORY.md` is often correct when the new lesson belongs to user style (`USER.md`) or behavior constitution (`SOUL.md`).
3. Apply the routing test: `USER.md` = who Konstantin is / stable preferences; `MEMORY.md` = tiny always-on routing/guardrail index; `SOUL.md` = agent behavioral law; procedures/pitfalls = skills/references; route-specific details = fact_store/docs/session_search.
4. When the user approves, patch minimal exact strings, then verify by reading the changed files and reporting chars/bytes/lines.
5. After `SOUL.md` or built-in memory edits, state the activation boundary: files are updated on disk, but cached SessionDB prompt may require fresh session, `/reset`, or gateway restart before the change is guaranteed in the system prompt.
6. User corrections about style/workflow are skill signals too: after editing memory/SOUL, patch the relevant class-level skill so the procedure improves outside always-on memory.

## Quick Audit Workflow

### 1. Load context and verify provider

For Hermes memory configuration tasks, load `hermes-agent` first.

Then check live state:

Run `python3 /home/konstantin/.hermes/skills/.archive/holographic-memory-hygiene/scripts/probe_memory_config.py`. The executable probe is kept in `scripts/` so `SKILL.md` stays procedural.

Expected healthy cautious setup:

- provider is `holographic`;
- plugin status is available;
- `plugins.hermes-memory-store.auto_extract` is `false` unless the user explicitly wants automatic extraction.

### 2. Locate and inspect SQLite DB

The default DB path is usually:

```text
~/.hermes/memory_store.db
```

Collect schema and metrics without dumping secrets or full raw content unless needed:

Run `python3 /home/konstantin/.hermes/skills/.archive/holographic-memory-hygiene/scripts/sqlite_metrics.py` for the read-only SQLite metrics probe.

### 3. Verify FTS5 search and entity extraction health

Run `python3 /home/konstantin/.hermes/skills/.archive/holographic-memory-hygiene/scripts/verify_fts5_and_entities.py`. Exit code 0 = healthy, 1 = one or more checks degraded.

This script validates:

- FTS5 OR fallback logic is present in `_fts_candidates()` (code check)
- FTS5 multi-word AND vs OR: OR results ≥ AND results (live DB test)
- FTS5 Cyrillic tokens are properly indexed (live DB test)
- Entity extraction has Cyrillic and single-word regex patterns (code check)
- Entity extraction correctly extracts "Konstantin" / "Константин" / backtick-terms (live test)
- Entity link coverage ≥ 50% of facts
- "Konstantin" entity has ≥ 3 linked facts

If any check fails, see `references/fts5-or-fallback-and-cyrillic-entities.md` for fix details and re-verification steps.

### 4. Check built-in memory pressure

Run `python3 /home/konstantin/.hermes/skills/.archive/holographic-memory-hygiene/scripts/builtin_memory_pressure.py` for built-in memory size pressure.

Interpretation:

- If `USER.md` / `MEMORY.md` are near limits, do not add more broad detail there.
- Keep built-in memory as a compact index to docs/skills/holographic facts.
- Move procedures to skills; move long stable system context to `/home/konstantin/docs/` where appropriate.

### 4. Use fact_store tools, not only SQLite

Run these as relevant:

- `fact_store(action='list', limit=100)` — high-level inventory.
- `fact_store(action='contradict', limit=10)` — explicit contradiction check.
- `fact_store(action='search', query='keyword OR keyword', limit=10)` — cluster discovery.
- `fact_store(action='probe', entity='...', limit=10)` — entity recall.
- `fact_store(action='reason', entities=['A','B'], limit=10)` — cross-entity facts.

After using facts to make decisions, close the feedback loop:

- `fact_feedback(action='helpful', fact_id=...)` for facts actually used and accurate.
- `fact_feedback(action='unhelpful', fact_id=...)` for stale or misleading facts, usually followed by `update` or `remove`.

Executable audit helpers live in `scripts/`: `probe_memory_config.py`, `sqlite_metrics.py`, and `builtin_memory_pressure.py`.

## Duplicate and Staleness Detection

### Candidate duplicate signals

Look for clusters sharing:

- same resource: `Gmail`, `Calendar`, `n8n`, `cron`, `distillation`, `model pool`;
- same warning: model pinning, OAuth failure, scope vs ACL, timezone errors;
- same setup facts with slightly different wording;
- old model architecture contradicted or superseded by newer architecture.

Use both direct search and reasoning:

```text
fact_store search: "n8n OR Docker OR 5678"
fact_store search: "cron OR model pinning OR language"
fact_store search: "distillation OR worker OR curator OR gpt-5.5"
fact_store search: "Gmail OR personal OR work mail"
fact_store reason: entities=["Konstantin", "Gmail"]
```

### Classification

For each candidate fact or cluster, classify as one of:

| Action | Meaning |
|---|---|
| `keep` | Fact is durable, non-duplicative, and in the right layer. |
| `update` | Fact is useful but stale, too broad, too narrow, or missing verification context. |
| `merge` | Multiple facts should become one canonical fact; usually update best fact, remove weaker duplicates. |
| `remove` | Fact is false, obsolete, transient progress, raw log, or superseded by a stronger canonical fact. |
| `promote_to_builtin` | Critical preference/warning should be always in prompt. Use sparingly due to char limits. |
| `demote_to_docs` | Long stable context should live in `/home/konstantin/docs/`, with only a pointer in built-in memory. |
| `promote_to_skill` | Procedure/checklist should become a reusable skill. |
| `leave_to_session_search` | Task progress or history should not be durable memory. |

### Canonical merge pattern

When merging duplicates:

1. Choose the fact with highest `helpful_count`, highest `trust_score`, or most accurate recent wording as canonical.
2. Draft the replacement content as a compact declarative fact.
3. Update canonical fact with `fact_store(action='update', fact_id=..., content=...)`.
4. Remove weaker duplicate facts with `fact_store(action='remove', fact_id=...)`.
5. Re-run `search` on the same cluster keywords to verify duplicates are gone.
6. If a targeted search unexpectedly returns empty after updates/removals, do not assume the facts are gone: retry with alternate distinctive terms from the canonical fact (for example model names, URLs, exact tool names, or short words without hyphen-heavy tokens) and confirm against `fact_store list` / SQLite fact IDs.
7. Verify storage consistency after cleanup: `facts` and `facts_fts` counts should match, and removed IDs should be absent from `fact_store list`.
8. Report exact fact IDs changed.

Do not bulk-remove facts without listing candidate IDs and rationale first unless the user explicitly asked for autonomous cleanup.

## Mutation Protocol

Before adding a new fact:

1. Run `fact_store(action='search', query='key terms', limit=10)`.
2. If a similar fact exists, use `update`, not `add`.
3. If no similar fact exists and the fact is durable, use `add`.
4. Rate the resulting fact when it is used.

Before updating/removing facts:

1. Show proposed action, fact IDs, and reason.
2. Confirm if the user did not already authorize cleanup.
3. Execute the minimal mutation.
4. Verify with `list`/`search`.
5. Report checked facts separately from hypotheses.

## Metrics to Report

A useful memory hygiene report should include:

- provider status and `auto_extract` state;
- DB path and size;
- fact count, FTS count, entity count, fact-entity links, memory bank count;
- category distribution;
- created-by-day distribution;
- tag coverage;
- trust stats: min/max/avg/median;
- helpful stats: total/avg/median/max;
- retrieval stats, but mark unreliable if all zero after active use;
- content length stats;
- top helpful facts;
- low-trust facts, with caveat that low trust alone is not a deletion reason;
- explicit contradiction result;
- duplicate/stale clusters with proposed action;
- built-in memory pressure (`USER.md`, `MEMORY.md` chars vs limits when known);
- final action plan: safe read-only findings, proposed mutations, and what needs user approval.

## Memory Layer Routing Guardrails

Before writing to any memory layer, apply these routing tests. This prevents the common failure of storing episodic facts in expensive always-on context.

### Current MEMORY.md structure (canonical, revised 2026-05-03)

MEMORY.md is a compact 3-section always-on routing guardrail (~1.2KB after the 2026-05-03 second revision). It is not a fact database. Expected shape:

```text
§ DO-NOT-EDIT for MEMORY.md/USER.md/SOUL.md + no /restart|/reset while writes are unfinished.
§ MEMORY = always-on guardrails + pointers, not facts. Gate: «нужно на КАЖДОМ ходу?» routes to MEMORY/USER/SOUL vs fact_store/skills/docs/session_search. Promotion from fact_store requires 5+ independent uses.
§ Routing cues for USER/SOUL/docs/skills/fact_store + holographic trigger: probe/search/reason when user/environment/past decisions are relevant; feedback after use; search before add; stale → update/remove; audit → this skill.
```

When auditing built-in memory, verify MEMORY.md conforms to this structure. If it grows beyond guardrails + routing cues + holographic trigger, flag for evacuation to fact_store/skills/docs. Do not optimize bytes by deleting safety-critical triggers.

| Layer | Contents | Cost |
|---|---|---|
| `MEMORY.md` | Identity, core preferences, behavioral guardrails, retrieval cues (pointers to fact_store) | High — injected every turn |
| `USER.md` | User profile: language, style, quality requirements, irritants, communication preferences | High — injected every turn |
| `SOUL.md` | Agent behavioral constitution: principles, routing, permission model | High — injected every turn |
| `fact_store` | Atomic durable facts: incidents, project details, service configs, entity-linked knowledge | Low — on-demand |
| Skills (`SKILL.md`) | Procedural knowledge: workflows, checklists, step-by-step | Low — loaded when triggered |
| Docs (`/home/konstantin/docs/`) | Long-form stable context: infrastructure, runbooks, plans | Low — on-demand |
| `session_search` | Raw logs, transient progress, task history | Lowest — past only |

### Write-through test (mandatory before MEMORY.md write)

Before any write to `MEMORY.md`, ask: **"Will I need this fact on EVERY future turn?"**

- **Yes** → MEMORY.md is the right place (identity, behavioral rule, guardrail)
- **No** → fact_store (incidents, project facts, service details, episodic events)

### Holographic memory protocol

1. **Before answering** — `probe` or `search` on relevant entities.
2. **After using a fact** — `fact_feedback` (helpful/unhelpful) to train trust scores.
3. **Before adding** — `search` for duplicates. Similar fact → `update`, not `add`.
4. **Stale/erroneous** — `update`/`remove`.
5. **Periodically** — `contradict` and hygiene audit.

### Entity test and procedure routing

If the fact has a natural entity (a project, a person, a service, a VPS), it belongs in `fact_store` under that entity. Only truly cross-cutting identity/preference data belongs in MEMORY.md.

Procedures and step-by-step workflows belong in **Skills**, not in memory or fact_store.

### Promotion rule

A fact in `fact_store` that was independently retrieved 5+ times across sessions can earn a one-line pointer in MEMORY.md — not the full fact, just a retrieval cue like "See fact_store for: VPS incidents, backup strategy."

### Budget

MEMORY.md should stay under ~1KB. If over budget: move oldest/least-used facts to fact_store, keep only pointers.

### Common failure modes from context pollution

1. **Priority inversion**: Low-value episodic facts take slots from high-value rules → model ignores instructions.
2. **Fact conflation**: Adjacent unrelated facts in always-on context → model hallucinates relationships.
3. **Amnesia cascade**: When always-on context exceeds limits and gets truncated, system instructions are cut first.

Source: MemGPT/Letta core vs archival separation, Zep classification pipeline, Baddeley/Ericsson cognitive architecture research. See `references/memory-routing-research.md`.

Session-specific detail on the 2026-05-03 MEMORY.md optimization: `references/memory-routing-session-2026-05-03.md`.

Session-specific detail on the later 2026-05-03 cross-layer compaction of `MEMORY.md`, `USER.md`, and `SOUL.md`: `references/memory-architecture-optimization-2026-05-03.md`.

Session-specific closeout and SQLite verification notes from the 2026-05-05 hygiene run: `references/memory-hygiene-closeout-and-sqlite-verification-2026-05-05.md`.

### User preference corrections (sessions 2026-05-03)

- **Promotion threshold**: 5+ independent retrievals from fact_store before earning a pointer in MEMORY.md. (User explicitly corrected from 3+.)
- **MEMORY.md budget**: ~1KB. Always-on context is expensive; keep it minimal.
- **DO-NOT-EDIT**: never edit MEMORY.md, USER.md, SOUL.md without explicit permission.
- **Default-deny routing**: By default do NOT write to MEMORY.md. Apply Gate test: «Нужен на КАЖДОМ ходу?» — only identity, preferences, cues pass. Everything else routes to fact_store, skills, or docs.
- **Holographic protocol pointer**: MEMORY.md §3 contains `гигиена → skill holographic-memory-hygiene` as the bidirectional link. The full protocol lives here (in this skill), not in always-on context.
- **Procedures → Skills**: never store procedures in fact_store or MEMORY.md.
- **Layer routing is canonical in MEMORY.md §2-3**, not in SOUL.md. If SOUL.md contains duplicate routing rules, flag for removal during SOUL.md optimization.

## Known Current Pitfalls in This Setup

1. **`retrieval_count` may stay zero.** Treat as unverified/low-value until the implementation is checked or a run proves it increments.
2. **`contradict` is not a deduper.** It can return no results while semantic duplicates remain.
3. **Daily distillation/model-pool facts can stale quickly.** Verify cron metadata, prompts, skills, and config before reporting current model architecture.
4. **Google Calendar scope vs ACL is easy to conflate.** API scopes and calendar sharing permissions are different layers.
5. **Built-in memory is small and often near full.** Do not use it as a dumping ground.
6. **`memory(action='add')` may mirror into holographic.** This is expected behavior for the plugin, not a bug.
7. **Automatic extraction is intentionally off for cautious users.** Do not enable it unless explicitly asked.
8. **FTS5 defaults to AND for multi-word queries.** `fact_store search "сервер VPS n8n backup"` returns 0 if no single fact contains ALL four words. `_fts_candidates` in `retrieval.py` was patched (May 2026) with OR fallback: if AND returns 0, retry with each word OR'd. If search returns 0 unexpectedly, verify this fix is in place: check `_fts_candidates` in `plugins/memory/holographic/retrieval.py` for the OR retry block. See `references/fts5-or-fallback-and-cyrillic-entities.md`.
9. **Entity extraction misses Cyrillic and single Title-case words.** `_extract_entities` in `store.py` was patched (May 2026) to add `_RE_CYRILLIC_TITLE`, `_RE_CYRILLIC_MULTI`, `_RE_CAPITALIZED_1`, `_RE_BACKTICK`, and a `_STOP_ENTITIES` set. Before the patch, "Konstantin" (single word), "Константин" (Cyrillic), and backtick-quoted terms were invisible to probe/reason. If probe by entity returns surprisingly few results, verify the patch is in place and run `rebuild_all_vectors()` to re-extract entities. See `references/fts5-or-fallback-and-cyrillic-entities.md`.
10. **SQLite fact ID column is `fact_id`, not always `id`.** When writing ad-hoc verification against `/home/konstantin/.hermes/memory_store.db`, inspect `PRAGMA table_info(facts)` or use `fact_id` for the facts table. A removed-ID check that assumes `id` will fail with `sqlite3.OperationalError: no such column: id`. See `references/memory-hygiene-closeout-and-sqlite-verification-2026-05-05.md`.
11. **Plan closeout is part of memory hygiene completion.** If a hygiene run created/updated a plan in `/home/konstantin/docs/plans/`, do not report done until the plan is both marked complete and archived according to plan governance. Under tool-call/context pressure, prioritize archive/root verification over extra narrative.

## Report Template

Keep Konstantin-facing hygiene reports concise: start with the decision/status and exact files changed or proposed. If the analysis is long, put evidence after the practical conclusion; avoid broad narrative unless requested. If the user says the review is too verbose, update the plan/skill directly and report only the delta.

```markdown
## Holographic Memory Hygiene Report

### Checked facts
- Provider: ...
- DB: ...
- auto_extract: ...
- Facts / FTS / entities / links / banks: ...

### Metrics
| Metric | Value |
|---|---:|
| facts | ... |
| avg trust | ... |
| median trust | ... |
| helpful total | ... |
| retrieval median | ... |

### Findings
1. ...

### Duplicate / stale clusters
| Cluster | Fact IDs | Assessment | Proposed action |
|---|---|---|---|
| ... | ... | ... | ... |

### Recommended mutations
- `update fact_id=...`: reason
- `remove fact_id=...`: reason
- `add`: reason

### Needs user approval
- ...

### Compact conclusion
- Healthy / needs cleanup / risky because ...
```

## Verification Checklist

- [ ] `hermes memory status` or config confirms provider state.
- [ ] SQLite metrics collected from the live DB, not guessed.
- [ ] FTS5 search + entity extraction health verified via `verify_fts5_and_entities.py` (exit 0).
- [ ] Built-in memory pressure checked if the task concerns memory architecture.
- [ ] `fact_store list` and `contradict` used for live semantic view.
- [ ] Duplicate clusters checked with targeted `search` / `probe` / `reason`.
- [ ] `fact_feedback` applied to every retrieved fact actually used in analysis.
- [ ] Proposed mutations distinguish verified facts from expert hypotheses.
- [ ] No destructive `remove` or broad `update` performed without authorization.
- [ ] Post-mutation verification done with `search`/`list`.
- [ ] If SQLite is used for removed-ID verification, the facts primary key column was detected (`fact_id` in current DB) rather than assumed to be `id`.
- [ ] If a `/home/konstantin/docs/plans/` plan was created or updated, it was closed and archived before reporting done.
- [ ] Final report includes exact fact IDs for any changed or proposed records.
