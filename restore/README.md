# Restore notes

## Requirements

- `age`
- `zstd`
- `tar`
- `sqlite3`
- Matching SSH private key for one of the public recipients recorded in `backup/age-recipients.txt` and the encrypted artifact manifests.

## Plaintext overlay restore order

1. Review this repository first; do not blindly overwrite a live Hermes home.
2. Restore docs from `docs/` to `/home/konstantin/docs/` if needed.
3. Restore safe Hermes overlay files from `hermes/` to `/home/konstantin/.hermes/`:
   - `SOUL.md`
   - `memories/`
   - `plugins/`
   - `cron/jobs.json`
4. Restore `hermes/holographic-memory/memory_store.sqlite` to `/home/konstantin/.hermes/memory_store.db` only after stopping Hermes processes that may write to memory.
5. Restore redacted config files only as references. They are not drop-in replacements for raw secrets.

## Development source restore notes

Hermes Agent development source is restored from Git refs, not from copied source snapshots:

1. Read `development/hermes-agent.json`.
2. Clone `repo_url`.
3. Checkout `branch`.
4. Verify `HEAD` equals the recorded `head`.
5. The skill source and skill-owned CLIs live inside that development checkout under `skills/`.

Do not restore `.git`, virtualenvs, pycache, build outputs, or caches from this backup; they are intentionally excluded.

## Decrypt encrypted artifacts

The current tree should contain one active encrypted generation per directory. Use the latest `manifest-*.json` files to identify exact artifact names; do not restore old generated files left only in Git history unless you intentionally check out an older commit.

For a single archive:

```bash
age -d -i /path/to/private_ssh_key secrets-encrypted/hermes-secrets-YYYYMMDD-HHMMSS.tar.zst.age | tar --zstd -tvf -
```

For split state/session archive:

```bash
cat session-history-encrypted/hermes-state-and-sessions-YYYYMMDD-HHMMSS.tar.zst.age.part* \
  | age -d -i /path/to/private_ssh_key \
  | tar --zstd -tvf -
```

To extract, replace `tar --zstd -tvf -` with:

```bash
tar --zstd -xvf - -C /safe/restore/dir
```

Do not extract directly over a live `~/.hermes` until DB integrity and file modes are checked.

## Sensitive file modes

Before trusting a restore, run the strict verifier in the checked-out backup repo:

```bash
python3 scripts/verify-hermes-backup.py --max-encrypted-age-days 8 --require-single-active-generation
```

On a MacBook/off-server restore test, pass the MacBook identity explicitly:

```bash
python3 scripts/verify-hermes-backup.py --identity-file ~/.ssh/id_ed25519 --max-encrypted-age-days 8 --require-single-active-generation
```

After restoring secrets, enforce restrictive permissions:

```bash
chmod 600 ~/.hermes/.env ~/.hermes/auth.json 2>/dev/null || true
chmod 600 ~/.hermes/credentials/* 2>/dev/null || true
```
