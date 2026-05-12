# SQLite Fact Store Recovery

Emergency recovery procedures for the holographic memory SQLite database (`~/.hermes/memory_store.db`). These are last-resort techniques; prefer backup restoration when available.

## Damage Classes Observed

### 1. Corrupted Header (bytes 0–99)

**Symptoms:**
- `sqlite3 file.db "PRAGMA integrity_check"` → `Error: file is not a database`
- `xxd file.db | head -1` shows `5351 4c69 7417 0303...` instead of `5351 4c69 7465 2066 6f72 6d61 7420 3300`
- `file file.db` reports `data` (not `SQLite 3.x database`)

**Cause:** Magic string "SQLite format 3\0" damaged — only first 5 bytes (`SQLit`) survive; rest of header (page_size, page_count, encoding) also corrupted. Often accompanied by a zero-length `-wal` file and a valid `-shm` file, indicating a crash during an incomplete write rather than disk corruption.

**Fix:**
```bash
# Copy first 100 bytes from a working DB to the corrupted one
python3 -c "
with open('/home/konstantin/.hermes/memory_store.db', 'rb') as f:
    good_header = f.read(100)
with open('/path/to/corrupted.db', 'rb') as f:
    rest = f.read()
fixed = good_header + rest[100:]
with open('/tmp/fixed.db', 'wb') as f:
    f.write(fixed)
"
```

### 2. B-Tree Corruption (valid header, broken page references)

**Symptoms:**
- `PRAGMA integrity_check` passes or fails on header but reveals 50+ B-tree errors: "invalid page number 341", "freelist leaf count too big", "never used" pages
- `.dump` and `.mode insert` fail with "database disk image is malformed" — they traverse B-tree pointers
- But `SELECT * FROM facts WHERE fact_id = N` and `SELECT fact_id FROM facts` still work for individual rows

**Why:** `SELECT` by primary key uses index lookup or direct rowid access, avoiding the damaged B-tree interior nodes. `.dump` and `.mode insert` do full table scans through B-tree structure.

**Recovery workflow:**

```bash
# 1. Fix header first (see above section)

# 2. Extract all readable IDs
sqlite3 /tmp/fixed.db "SELECT fact_id FROM facts;" > /tmp/fact_ids.txt
sqlite3 /tmp/fixed.db "SELECT entity_id FROM entities;" > /tmp/entity_ids.txt

# 3. Export each row by ID (avoid .dump)
while read fid; do
    sqlite3 /tmp/fixed.db ".mode insert facts" "SELECT * FROM facts WHERE fact_id = $fid;" >> /tmp/facts_all.sql
done < /tmp/fact_ids.txt

while read eid; do
    sqlite3 /tmp/fixed.db ".mode insert entities" "SELECT * FROM entities WHERE entity_id = $eid;" >> /tmp/entities_all.sql
done < /tmp/entity_ids.txt

# 4. Build clean DB
rm -f /tmp/clean.db
sqlite3 /tmp/clean.db < /tmp/facts_all.sql
sqlite3 /tmp/clean.db < /tmp/entities_all.sql
sqlite3 /tmp/clean.db "INSERT INTO facts_fts(facts_fts) VALUES('rebuild');"

# 5. Verify
sqlite3 /tmp/clean.db "PRAGMA integrity_check;"  # must return "ok"
sqlite3 /tmp/clean.db "SELECT count(*) FROM facts;"

# 6. Compare against current working DB to find missing facts
sqlite3 /home/konstantin/.hermes/memory_store.db "SELECT fact_id FROM facts;" | sort -n > /tmp/curr.txt
sqlite3 /tmp/clean.db "SELECT fact_id FROM facts;" | sort -n > /tmp/recov.txt
comm -13 /tmp/curr.txt /tmp/recov.txt  # facts in recovered DB not in current
comm -23 /tmp/curr.txt /tmp/recov.txt  # facts in current DB not in recovered

# 7. Re-add missing facts via fact_store
#    fact_store add each missing fact with original category/tags
```

## Python vs Shell sqlite3

- **Python `sqlite3` module** is stricter: throws `DatabaseError` on first malformed page during iteration
- **Shell `sqlite3` CLI** is more tolerant: many `SELECT` operations succeed where Python fails
- Use shell for extraction, Python for data reshaping and clean-DB assembly

## Fact vs Entity Recovery

- `facts` table: primary data, 149 rows in largest recovered DB
- `entities` table: entity resolution, 676 rows, also recoverable by ID
- `fact_entities` join table: most fragile — cross-page references mean high corruption probability; often unrecoverable
- `memory_banks` table: small (4 rows), usually intact
- FTS5 virtual tables (`facts_fts_*`): always rebuild with `INSERT INTO facts_fts(facts_fts) VALUES('rebuild')`

## Prevention

- Regular backups: `cp ~/.hermes/memory_store.db ~/.hermes/memory_store.db.$(date +%Y%m%d)`
- The `holographic-memory-hygiene` skill should be extended with a backup check
- Avoid SQLite operations during system shutdown or when disk space is critically low
