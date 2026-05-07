# Memory hygiene closeout and SQLite verification notes (2026-05-05)

Session signal: a memory hygiene run completed the semantic cleanup and wrote `Current status: done` into `/home/konstantin/docs/plans/2026-05-05-memory-hygiene.md`, but hit the tool-call limit before physically archiving the closed plan. Future memory hygiene runs should treat plan archive as part of closeout, not a cosmetic follow-up.

## Reusable lessons

- If a hygiene task created or touched a durable plan under `/home/konstantin/docs/plans/`, final verification is not complete until the plan status and file location agree:
  - active root plan => `planned`, `in_progress`, or `blocked`;
  - closed plan => `done`, `cancelled`, or `superseded` and moved to `archive/<year>/<status>/`.
- Under context compression or tool-call pressure, prioritize mechanical closeout over extra narrative: update plan, archive/move it, verify root cleanliness, then report.
- Do not mark a plan `Current status: done` and leave it in root unless the next immediate operation is the archive move.
- When checking removed fact IDs in SQLite, do not assume the primary key column is `id`. In this Hermes holographic DB the `facts` primary key is `fact_id`; robust checks should inspect `PRAGMA table_info(facts)` and choose `fact_id` if present.

## Robust removed-ID check pattern

```python
import sqlite3
ids = [115, 117, 120]
db = '/home/konstantin/.hermes/memory_store.db'
con = sqlite3.connect(db)
cur = con.cursor()
cols = [r[1] for r in cur.execute('pragma table_info(facts)')]
id_col = 'fact_id' if 'fact_id' in cols else ('id' if 'id' in cols else cols[0])
q = ','.join('?' for _ in ids)
cur.execute(f'select {id_col} from facts where {id_col} in ({q}) order by {id_col}', ids)
print('removed_ids_still_present=', [r[0] for r in cur.fetchall()])
print('facts=', cur.execute('select count(*) from facts').fetchone()[0])
print('fts=', cur.execute('select count(*) from facts_fts').fetchone()[0])
con.close()
```

## Report shape if interrupted by tool limits

If a hard tool-call limit prevents archive/verification, be explicit:

- completed: provider/config/DB/FTS/entity checks, exact fact IDs updated/removed, post-mutation DB consistency;
- not completed: physical plan archive or todo closeout;
- next mechanical action: move the plan to `archive/<year>/done/` and verify root cleanliness.
