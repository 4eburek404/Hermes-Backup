# Memory Hygiene Audit — 2026-05-07

Full audit of `fact_store` (87→76 facts). First production run of the holographic-memory-hygiene workflow.

## Findings that changed the skill

### F1. `contradict` is blind to fact↔reality
- `contradict` returned 0 contradictions across 87 facts
- Fact 163 claimed "MEMORY pointer: flight-search" in MEMORY.md — no such pointer existed
- No other fact contradicted it; the mismatch was between fact and live file state
- **Result:** Added "Fact↔Reality Verification Pass" section to memory-hygiene.md

### F2. `retrieval_count` dead metric
- All 87 facts had `retrieval_count = 0`
- Cannot distinguish active from dormant facts via retrieval
- **Result:** Documented reliance on `helpful_count`, `trust_score`, timestamps instead; retrieval count already listed as pitfall

### F3. Gray zone: iterative drafts vs separate facts
- Flight-search guardrail facts 160/161/162/163 were iterative refinements, not exact copies
- Each slightly different wording; canonical choice was manual
- DeepSeek cluster (31/34/155/156/159) carries different aspects per fact — not true duplicates
- **Result:** Added pitfall #8 to memory-hygiene.md

### F4. Volatile state as durable fact
- Fact 82: cron job snapshot on specific date — stale within a week
- Fact 81: skill version v1.1.1 — stale as soon as skill updated
- Both had zero contradictions because no other fact claimed the opposite
- **Result:** Added `tags="volatile"` convention; added pitfall #9

### F5. Trust ≠ canonical
- Within duplicate groups, highest trust sometimes belonged to the worst-worded variant
- Trust measures retrieval usefulness, not accuracy or authority
- **Result:** Added `tags="canonical"` convention; added pitfall #10

### F6. `.archive/` = skills category, not literal archive
- Stale cron ID `62e7a25f4e15` in `~/.hermes/skills/.archive/daily-knowledge-distillation/SKILL.md`
- Active skill was patched; archive copy was not
- User corrected: `.archive/` is a category inside skill structure, not a dead-letter archive
- 7 dead duplicate skills removed (356K freed)
- **Result:** Added pitfall #11 to both SKILL.md and memory-hygiene.md

### F7. Process doesn't scale past ~100 facts manually
- 87 facts required full manual review, grouping, and 11 decisions
- No built-in dedup/merge flow; only `search` + judgment
- **Result:** Added pitfall #12; documented prep-script approach for larger stores

## Actions taken

| Action | Fact IDs | Reason |
|--------|----------|--------|
| Update canonical | 44, 161 | Merged best wording from duplicate groups |
| Update stale | 152 | Backup cron job exists but `enabled=false`; fact now accurate |
| Update preference | 107 | Canonical line-by-line review guardrail |
| Remove duplicate | 105, 128, 148, 149, 157, 158, 160, 162, 163 | Weaker versions of canonical facts |
| Remove stale | 81, 82 | Volatile runtime snapshots with no durable value |

## Verification

- DB integrity: OK (facts=76, FTS=76, entity coverage=100%)
- All 11 removed IDs confirmed absent
- No misleading phrases in active facts
- Trust avg 0.598, median 0.55, helpful total 202
