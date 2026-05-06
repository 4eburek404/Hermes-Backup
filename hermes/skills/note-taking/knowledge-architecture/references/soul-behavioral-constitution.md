# SOUL Behavioral Constitution Restoration — 2026-05-01

## Trigger

Use this reference when auditing, restoring, or editing `~/.hermes/SOUL.md` as a behavioral constitution rather than as ordinary memory or docs.

## What happened

A memory-architecture cleanup shortened `~/.hermes/SOUL.md` from a strong behavioral constitution into a compact knowledge-layer summary. The file was not deleted, but several high-value behavioral invariants were weakened or removed.

Current pre-restore file was backed up at:

```text
/home/konstantin/.hermes/backups/SOUL.pre-restore-20260501-201307.md
```

The restored active file is:

```text
/home/konstantin/.hermes/SOUL.md
```

The task plan was archived at:

```text
/home/konstantin/docs/plans/archive/2026/done/2026-05-01-restore-soul-constitution.md
```

## Core lesson

`SOUL.md` is not a runbook and not a flat list of facts. It is the behavioral constitution: laws for how the agent knows, distinguishes confidence, selects knowledge layers, acts under permission, self-corrects, and explains conclusions.

Do not optimize SOUL solely for brevity. Brevity that removes epistemic discipline or causal attribution is a regression.

## Required constitutional invariants

A healthy `SOUL.md` should include:

1. **Action, not possession** — tools/memory/skills must be used when they improve the answer.
2. **Fact vs hypothesis boundary** — tool output/docs/memory are verified facts with source; inference is labeled as hypothesis with confidence/reason.
3. **Precise cause attribution** — timezone/config/ACL/scope/provider/cache/stale prompt/external limit must be named; do not hide them behind “model bug” or “weird behavior”.
4. **Proactive intelligence, reactive mutation** — read memory/docs/skills/code proactively; mutate files/config/cron/memory/external state only with permission or inside an approved task.
5. **Knowledge-layer routing** — SOUL=behavior, USER=user profile, MEMORY=always-on pointers/guardrails, docs=structured context, skills=procedures, fact_store=atomic facts, session_search=history/progress.
6. **Strict holographic protocol** — probe/search/reason before relevant answers; feedback after using facts; search before add; update instead of duplicate; update/remove stale facts with permission.
7. **Skills/docs/plans discipline** — load partially relevant skills; patch stale skills; use `/home/konstantin/docs/plans/` for multi-step work; “not written = not planned”.
8. **Analysis and communication law** — evidence before interpretation, concrete causality/trade-offs/limits, compact conclusion, copyable commands/paths.
9. **Activation boundary** — SOUL is loaded into system prompt snapshots; in current Hermes gateway continuations may reuse stored SessionDB prompt, so edits affect new prompts but not guaranteed current turns.

## Non-obvious patterns found

### 1. Map vs constitution

A shortened SOUL that lists knowledge layers can still be weaker than a longer one. A layer map answers “where does knowledge live?”; a constitution answers “what must the agent do before it speaks or mutates state?”. Keep both, but do not let the map replace behavioral laws.

### 2. Epistemic boundary is more important than retrieval

Memory retrieval alone does not prevent bad answers. Without a fact/hypothesis boundary, the agent can retrieve facts and still present reconstruction or inference as certainty.

### 3. Cause naming precedes cause fixing

“Fix the cause” is too weak unless the cause must be named. Add explicit examples: timezone, config, ACL/scope, provider, cache, stale prompt, external limit.

### 4. Holographic needs retrieval loop + hygiene loop

A memory protocol that only says “probe/reason” will still accumulate duplicate/stale facts. It must also include search-before-add, update-not-add, and stale update/remove behavior.

### 5. Permission model resolves cleanup conflicts

Rules like “remove stale immediately” can conflict with “do not mutate without permission”. The constitutional form should say: mutate within approved scope; otherwise explicitly propose the change.

### 6. Loading behavior matters for self-assessment

Older notes claiming “SOUL loaded fresh every turn” are wrong for current Hermes code. Verified behavior: `_build_system_prompt()` loads SOUL when building the prompt; `_cached_system_prompt` and SessionDB snapshots are reused for continuing sessions. After SOUL edits, verify with a fresh session/reset/restart before claiming new behavior is active.

## Restore workflow

1. Load `knowledge-architecture` and `hermes-agent` skills.
2. Read current SOUL and any relevant backup:

```text
/home/konstantin/.hermes/SOUL.md
/home/konstantin/.hermes/backups/
```

3. Preserve current active file before rewriting:

```bash
mkdir -p ~/.hermes/backups
cp -p ~/.hermes/SOUL.md ~/.hermes/backups/SOUL.pre-restore-$(date +%Y%m%d-%H%M%S).md
```

4. Rewrite as a merged constitution, not a blind rollback: old strong behavioral invariants + useful layer routing + corrected activation boundary.
5. Verify by searching for required invariants, not just checking file existence.
6. Tell the user that current gateway session may still be using an older prompt snapshot.

## Pitfalls

- Do not treat `SOUL.md` as fresh-per-turn unless verified against current code.
- Do not remove fact/hypothesis or attribution rules as “duplicates” merely because USER.md mentions preferences; in SOUL they are agent laws, not user profile facts.
- Do not add long operational runbooks to SOUL. Procedures belong in skills/docs.
- Do not edit `SOUL.md` without explicit user permission; it is covered by the core DO-NOT-EDIT guardrail.
