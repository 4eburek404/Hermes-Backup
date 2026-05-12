# Holographic memory SQLite recovery

Use this when `memory.provider: holographic` is active but `fact_store` fails with errors such as:

- `'NoneType' object has no attribute 'search'`
- `'NoneType' object has no attribute 'list_facts'`
- logs show `Memory provider 'holographic' initialize failed: file is not a database`

## Evidence chain

1. Confirm the current DB is the failing layer, not the tool schema:

```bash
hermes memory status
rg "Memory provider 'holographic' initialize failed|file is not a database|NoneType" ~/.hermes/logs/agent.log ~/.hermes/logs/errors.log
sqlite3 ~/.hermes/memory_store.db 'PRAGMA integrity_check;'
```

If SQLite says `file is not a database`, the provider initialization failed and `fact_store` may still appear in the tool list while `_store`/`_retriever` are `None`.

2. Look for a valid local backup before creating an empty store. Known backup locations in Konstantin's setup:

```bash
find /home/konstantin -maxdepth 5 \( -iname '*holographic-memory*' -o -iname '*memory_store.sqlite*' -o -iname '*memory_store.db*' \) 2>/dev/null
```

Typical valid backup path from the Hermes backup repo snapshot:

```bash
/home/konstantin/backups/hermes-github/hermes/holographic-memory/memory_store.sqlite
```

A source checkout may also contain:

```bash
/home/konstantin/code/Hermes/hermes/holographic-memory/memory_store.sqlite
```

3. Validate candidate backups before restoring:

```bash
python - <<'PY'
import sqlite3
from pathlib import Path
for p in [
    Path('/home/konstantin/backups/hermes-github/hermes/holographic-memory/memory_store.sqlite'),
    Path('/home/konstantin/code/Hermes/hermes/holographic-memory/memory_store.sqlite'),
]:
    if not p.exists():
        continue
    con = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
    print(p, con.execute('PRAGMA integrity_check').fetchone()[0])
    print('facts', con.execute('select count(*) from facts').fetchone()[0])
    print('updated_range', con.execute('select min(updated_at), max(updated_at) from facts').fetchone())
    con.close()
PY
```

Prefer the newest valid backup with `integrity_check = ok` and expected `facts/entities` counts.

## Safe restore

Preserve the current DB, WAL, and SHM first; do not delete them until recovery is verified.

```bash
set -euo pipefail
TS=$(date +%Y%m%d_%H%M%S)
DST="$HOME/.hermes/memory_store.db"
SRC="/home/konstantin/backups/hermes-github/hermes/holographic-memory/memory_store.sqlite"
BKP_DIR="$HOME/.hermes/recovery-backups/holographic-memory-$TS"
mkdir -p "$BKP_DIR"
for f in "$DST" "$DST-wal" "$DST-shm"; do
  if [ -e "$f" ]; then cp -a "$f" "$BKP_DIR/$(basename "$f")"; fi
done
cp -a "$SRC" "$DST.tmp-$TS"
python - <<PY
import sqlite3
p='$DST.tmp-$TS'
con=sqlite3.connect(p)
res=con.execute('PRAGMA integrity_check').fetchone()[0]
assert res == 'ok', res
con.close()
PY
mv "$DST.tmp-$TS" "$DST"
rm -f "$DST-wal" "$DST-shm"
chmod 600 "$DST"
```

## Verify after restore

```bash
python - <<'PY'
import sqlite3
p='/home/konstantin/.hermes/memory_store.db'
con=sqlite3.connect(p)
print('integrity:', con.execute('PRAGMA integrity_check').fetchone()[0])
print('facts:', con.execute('select count(*) from facts').fetchone()[0])
print('entities:', con.execute('select count(*) from entities').fetchone()[0])
print('updated_range:', con.execute('select min(updated_at), max(updated_at) from facts').fetchone())
con.close()
PY
```

Then verify a fresh provider process, not only raw SQLite:

```bash
cd /home/konstantin/.hermes/hermes-agent
python - <<'PY'
from plugins.memory.holographic import HolographicMemoryProvider
p=HolographicMemoryProvider()
p.initialize('restore-test')
print(p.system_prompt_block().split('\n')[1])
print(p.handle_tool_call('fact_store', {'action':'search','query':'Hermes backup','limit':2}))
p.shutdown()
PY
```

Expected: `Active. <N> facts stored...` and a JSON result, not `NoneType`.

## Runtime boundary

Restoring the DB file does **not** necessarily repair the current Telegram session. If the gateway/session initialized the provider while the DB was corrupt, the in-process provider object may still hold `_store = None` and `_retriever = None`.

After file restore:

1. Ask for or trigger a fresh session with `/reset` when safe.
2. If `fact_store` still returns `NoneType`, restart the gateway and verify again.
3. Do not claim the current chat's `fact_store` works until the tool itself succeeds; distinguish "file restored and fresh-process provider works" from "this runtime has reinitialized".

## Pitfalls

- GitHub backup repo access may fail if `gh` auth is invalid; use local backup snapshots first.
- A file can start with `SQLite`-looking bytes and still fail SQLite integrity checks; trust `PRAGMA integrity_check`, not headers.
- Preserve corrupt files in `~/.hermes/recovery-backups/` for forensic recovery.
- Avoid creating an empty store if a valid backup exists; it loses durable facts even though it makes the provider initialize.
