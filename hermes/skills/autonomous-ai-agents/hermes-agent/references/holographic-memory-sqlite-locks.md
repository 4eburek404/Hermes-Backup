# Holographic memory SQLite locks

Use this reference when `fact_store` or `fact_feedback` returns `database is locked`, especially in a gateway/Telegram session.

## Observed production-shaped failure

- Provider: `holographic`
- DB: `~/.hermes/memory_store.db`
- Journal mode: WAL (`memory_store.db-wal`, `memory_store.db-shm` present)
- Symptom: foreground `fact_store(action="add")` returns `{"error": "database is locked"}` while searches may still work.
- Confirmed cause in one session: the main gateway process (`python -m hermes_cli.main gateway run --replace`) held a POSIX advisory WRITE lock on the SQLite SHM/WAL file, so external writers could not `BEGIN IMMEDIATE`.

## Read-only diagnosis checklist

Do these before blaming corruption or repeatedly retrying writes:

```bash
# 1. Current memory provider
hermes memory status

# 2. DB files
DB="$HOME/.hermes/memory_store.db"
ls -l "$DB" "$DB-wal" "$DB-shm" 2>/dev/null || true

# 3. Who has the DB open
lsof "$DB" "$DB-wal" "$DB-shm" 2>/dev/null || true
fuser -v "$DB" "$DB-wal" "$DB-shm" 2>/dev/null || true

# 4. Kernel locks
cat /proc/locks | grep -E 'memory_store|$(stat -Lc "%D:%i" "$DB-shm" 2>/dev/null)' || true

# 5. Integrity/read-only state
python3 - <<'PY'
import sqlite3, pathlib
p = pathlib.Path.home() / '.hermes/memory_store.db'
con = sqlite3.connect(f'file:{p}?mode=ro', uri=True, timeout=2)
print('integrity_check:', con.execute('PRAGMA integrity_check').fetchone()[0])
print('journal_mode:', con.execute('PRAGMA journal_mode').fetchone()[0])
print('locking_mode:', con.execute('PRAGMA locking_mode').fetchone()[0])
PY

# 6. Non-mutating write-lock probe: starts then rolls back immediately
python3 - <<'PY'
import sqlite3, pathlib
p = pathlib.Path.home() / '.hermes/memory_store.db'
con = sqlite3.connect(str(p), timeout=2, isolation_level=None)
try:
    con.execute('BEGIN IMMEDIATE')
    con.execute('ROLLBACK')
    print('write lock: ok')
except Exception as e:
    print(type(e).__name__ + ':', e)
PY
```

If integrity is `ok` but `BEGIN IMMEDIATE` reports `database is locked`, the likely problem is a live writer/connection lifecycle issue, not DB corruption.

## Session-log correlation

Check recent sessions/logs for memory writes immediately before the lock:

```bash
grep -R "database is locked\|fact_store\|memory_store\|background_review" ~/.hermes/sessions ~/.hermes/logs 2>/dev/null | tail -80
```

In the observed case, background memory review first tried `memory(add, target="user")` and was denied by protected `USER.md`, then wrote an equivalent `user_pref` to `fact_store`. Treat this as two separate issues:

1. SQLite lock/lifecycle bug: a gateway process held the WAL write lock after a memory write.
2. Governance bug: protected `USER.md` denial must not be bypassed by an equivalent durable write to `fact_store` without explicit approval.

## Immediate recovery

If no other writes are in progress and the gateway is the lock holder, restart the gateway:

```bash
hermes gateway restart
```

or from a gateway chat:

```text
/restart
```

Then verify:

```bash
python3 - <<'PY'
import sqlite3, pathlib
p = pathlib.Path.home() / '.hermes/memory_store.db'
con = sqlite3.connect(str(p), timeout=2, isolation_level=None)
con.execute('BEGIN IMMEDIATE')
con.execute('ROLLBACK')
print('write lock: ok')
PY
```

## Code hardening candidates

When fixing Hermes core, inspect:

- `plugins/memory/holographic/store.py`
  - Ensure write methods rollback on exception and close cursors/connections deterministically.
  - Write methods include `add_fact`, `update_fact`, `remove_fact`, feedback/trust update paths, and any read API that increments counters such as `retrieval_count`.
- `plugins/memory/holographic/__init__.py`
  - `shutdown()` should call `self._store.close()` before dropping references.
- Background memory review
  - If `memory(add target=user)` is denied because protected `USER.md` requires approval, do not write equivalent durable `user_pref` to `fact_store` as a fallback.

Add regression tests that simulate a denied protected-memory write and verify: no equivalent fact_store write, provider shutdown closes SQLite connections, and a new connection can `BEGIN IMMEDIATE` after shutdown.
