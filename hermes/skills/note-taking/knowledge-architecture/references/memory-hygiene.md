# Holographic Memory Hygiene — Detailed Workflow

Audit and maintain Hermes' holographic memory: facts in `fact_store`, entity links, trust scores, FTS/SQLite state, built-in memory pressure, duplicates, stale operational claims, and unsafe memory patterns.

## Safety Rules

1. **Audit before mutation.** Gather metrics, clusters, and candidate actions before changing facts.
2. **Separate verified facts from hypotheses.** A SQLite count is verified. A semantic duplicate cluster is an expert hypothesis until reviewed.
3. **Never delete only because `trust_score == 0.5`.** New or rarely-used facts naturally sit at baseline trust.
4. **Do not treat `contradict=[]` as proof of no duplicates.** It only means no explicit contradictions were detected.
5. **Do not rely on `retrieval_count` until verified.** It may remain zero even after search/probe/reason. Prefer `helpful_count`, `trust_score`, timestamps, and manual relevance review.
6. **Built-in memory composition.** MEMORY.md should contain only three types of content: (a) indices pointing to where detailed knowledge lives, (b) self-protection guardrails that prevent the agent from modifying its own configuration without permission, and (c) known-wrong technical quirks — concrete failures the agent will silently repeat if not reminded (e.g., `ollama run :cloud = ENOSPC`, `json_schema broken for Ollama Cloud`, exact model tag format). Group multiple known-wrongs into one compound entry. Use the "would I search for this?" and "would I know to search?" tests: if the agent would naturally look up the fact when the relevant task arises, it belongs on-demand. If the agent would NOT think to search for the correction before acting, it may belong in MEMORY. Guard against two anti-patterns: (1) over-protectiveness — don't pad MEMORY with rules already covered by SOUL or USER; (2) invented guardrails — if the user didn't explicitly request a rule and it's already in USER.md or fact_store, don't add it to MEMORY. Additionally: **MEMORY.md, USER.md, and SOUL.md must not be edited without explicit user permission.** When requesting permission, show the proposed diff. These are first-class guardrails that must not drift.
7. **Anti-pollution over batch cleanup.** When writing facts, ask "would I look for this in a week?" If not, don't save it. Immediately update or remove stale facts. A well-maintained memory never needs a batch cleanup session. The goal is a curated library, not an attic that periodically needs sorting.
8. **Procedures belong in skills, not memory facts.** If a fact says how to perform a recurring workflow, consider promoting it to a skill.
7. **Operational claims need freshness.** Credentials, ACLs, scopes, cron model pinning, write permissions, service status, model availability should be reverified with tools before being reported as current truth.
8. **Backups can preserve leaks.** When editing built-in memory or `SOUL.md`, make a backup when appropriate, but include the backup directory in secret/credential-path scans and redact backup copies too.
9. **Respect no-edit / dry-run requests.** If the user asks for analysis only, do not write docs, skills, memory, cron, or config.

## Quick Audit Workflow

### 1. Load context and verify provider

For Hermes memory configuration tasks, load `hermes-agent` first. Then check live state:

```bash
hermes memory status
python3 - <<'PY'
from pathlib import Path
import yaml, json
p = Path.home() / '.hermes/config.yaml'
d = yaml.safe_load(p.read_text())
print(json.dumps({
    'memory': d.get('memory'),
    'plugin_hermes_memory_store': (d.get('plugins') or {}).get('hermes-memory-store'),
}, ensure_ascii=False, indent=2))
PY
```

Expected healthy cautious setup: provider is `holographic`; plugin status is available; `auto_extract` is `false` unless explicitly wanted.

### 2. Locate and inspect SQLite DB

Default DB path: `~/.hermes/memory_store.db`

Collect schema and metrics without dumping secrets or full raw content unless needed:

```python
import sqlite3, os, json, statistics
from pathlib import Path

path = Path.home() / '.hermes/memory_store.db'
print('db_exists', path.exists())
print('db_size_bytes', path.stat().st_size if path.exists() else 0)

con = sqlite3.connect(path)
con.row_factory = sqlite3.Row
cur = con.cursor()

print('tables', [r[0] for r in cur.execute("select name from sqlite_master where type='table' order by name")])
print('indexes', [r[0] for r in cur.execute("select name from sqlite_master where type='index' order by name")])

for table in ['facts', 'facts_fts', 'entities', 'fact_entities', 'memory_banks']:
    try:
        print(table, cur.execute(f'select count(*) from {table}').fetchone()[0])
    except Exception as e:
        print(table, 'missing_or_error', str(e))

rows = [dict(r) for r in cur.execute('''
    select fact_id, category, tags, trust_score, retrieval_count,
           helpful_count, created_at, updated_at, length(content) as len
    from facts
''')]

if rows:
    def stat(xs):
        return {'min': min(xs), 'max': max(xs), 'avg': sum(xs)/len(xs), 'median': statistics.median(xs)}
    cats = {}
    by_day = {}
    tagged = 0
    for r in rows:
        cats[r['category']] = cats.get(r['category'], 0) + 1
        by_day[(r['created_at'] or '')[:10]] = by_day.get((r['created_at'] or '')[:10], 0) + 1
        tagged += bool(r['tags'])
    print(json.dumps({
        'facts': len(rows),
        'categories': cats,
        'created_by_day': by_day,
        'tagged': tagged,
        'trust': stat([r['trust_score'] for r in rows]),
        'helpful': stat([r['helpful_count'] for r in rows]),
        'retrieval': stat([r['retrieval_count'] for r in rows]),
        'content_len': stat([r['len'] for r in rows]),
        'top_helpful': sorted(
            [(r['fact_id'], r['helpful_count'], r['trust_score'], r['category']) for r in rows],
            key=lambda x: (-x[1], -x[2])
        )[:10],
        'low_trust': sorted(
            [(r['fact_id'], r['trust_score'], r['category'], r['len']) for r in rows],
            key=lambda x: x[1]
        )[:10],
    }, ensure_ascii=False, indent=2))
con.close()
```

### 3. Check built-in memory pressure

```bash
python3 - <<'PY'
from pathlib import Path
for name in ['USER.md', 'MEMORY.md']:
    p = Path.home() / '.hermes/memories' / name
    text = p.read_text() if p.exists() else ''
    print(name, 'exists=', p.exists(), 'chars=', len(text), 'bytes=', p.stat().st_size if p.exists() else 0, 'lines=', text.count('\n') + bool(text))
PY
```

If `USER.md` / `MEMORY.md` are near limits, do not add more broad detail there. Keep built-in memory as a compact index to docs/skills/holographic facts.

### 4. Use fact_store tools, not only SQLite

- `fact_store(action='list', limit=100)` — high-level inventory
- `fact_store(action='contradict', limit=10)` — explicit contradiction check
- `fact_store(action='search', query='keyword OR keyword', limit=10)` — cluster discovery
- `fact_store(action='probe', entity='...', limit=10)` — entity recall
- `fact_store(action='reason', entities=['A','B'], limit=10)` — cross-entity facts

After using facts: `fact_feedback(action='helpful', fact_id=...)` for useful/accurate facts, `fact_feedback(action='unhelpful', fact_id=...)` for stale/misleading facts (usually followed by `update` or `remove`).

## Duplicate and Staleness Detection

### Candidate duplicate signals

Look for clusters sharing: same resource (`Gmail`, `Calendar`, `n8n`, `cron`, `distillation`, `model pool`), same warning (model pinning, OAuth failure, scope vs ACL, timezone errors), same setup facts with slightly different wording, old model architecture contradicted or superseded.

Search queries: `"n8n OR Docker OR 5678"`, `"cron OR model pinning OR language"`, `"distillation OR worker OR curator OR gpt-5.5"`, `"Gmail OR personal OR work mail"`.

### Classification

| Action | Meaning |
|---|---|
| `keep` | Fact is durable, non-duplicative, and in the right layer |
| `update` | Fact is useful but stale, too broad, too narrow, or missing verification context |
| `merge` | Multiple facts should become one canonical; update best, remove weaker duplicates |
| `remove` | Fact is false, obsolete, transient progress, raw log, or superseded |
| `promote_to_builtin` | Critical preference/warning should be always in prompt. Use sparingly. |
| `demote_to_docs` | Long stable context should live in docs, with only a pointer in built-in memory |
| `promote_to_skill` | Procedure/checklist should become a reusable skill |
| `leave_to_session_search` | Task progress or history should not be durable memory |

### Canonical merge pattern

1. Choose the fact with highest `helpful_count`, highest `trust_score`, or most accurate recent wording as canonical.
2. Draft the replacement content as a compact declarative fact.
3. Update canonical fact with `fact_store(action='update', fact_id=..., content=...)`.
4. Remove weaker duplicate facts with `fact_store(action='remove', fact_id=...)`.
5. Re-run `search` on the same cluster keywords to verify duplicates are gone.
6. If search unexpectedly returns empty, retry with alternate distinctive terms and confirm against `fact_store list` / SQLite fact IDs.
7. Verify storage consistency: `facts` and `facts_fts` counts should match, removed IDs absent from `fact_store list`.

Do not bulk-remove facts without listing candidate IDs and rationale first unless the user explicitly asked for autonomous cleanup.

## Mutation Protocol

Before adding: `search` for similar, use `update` if exists, `add` only if new.
Before updating/removing: Show proposed action, fact IDs, reason. Confirm if user didn't authorize. Execute minimal mutation. Verify with `list`/`search`. Report checked facts separately from hypotheses.

## Report Template

```markdown
## Holographic Memory Hygiene Report

### Checked facts
- Provider: ...
- DB: ...
- auto_extract: ...
- Facts / FTS / entities / links / banks: ...

### Metrics
| Metric | Value |
|---|---|
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

## Memory-Hygiene Pitfalls

1. `retrieval_count` may stay zero — treat as unverified/low-value.
2. `contradict` is not a deduper — semantic duplicates may remain while no contradictions are detected.
3. Daily distillation/model-pool facts can stale quickly — verify cron metadata, prompts, skills, and config before reporting current model architecture.
4. Google Calendar scope vs ACL is easy to conflate. API scopes and calendar sharing permissions are different layers.
5. Built-in memory is small and often near full — do not dump content there.
6. `memory(action='add')` may mirror into holographic — this is expected behavior for the plugin, not a bug.
7. Automatic extraction is intentionally off for cautious users — do not enable unless explicitly asked.