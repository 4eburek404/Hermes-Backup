# Restore notes

## Requirements

- `age`
- `zstd`
- `tar`
- `sqlite3`
- Matching SSH private key for the public recipient recorded in the encrypted artifact manifests.

## Plaintext overlay restore order

1. Review this repository first; do not blindly overwrite a live Hermes home.
2. Restore docs from `docs/` to `/home/konstantin/docs/` if needed.
3. Restore safe Hermes overlay files from `hermes/` to `/home/konstantin/.hermes/`:
   - `SOUL.md`
   - `memories/`
   - `skills/`
   - `plugins/`
   - `cron/jobs.json`
4. Restore `hermes/holographic-memory/memory_store.sqlite` to `/home/konstantin/.hermes/memory_store.db` only after stopping Hermes processes that may write to memory.
5. Restore redacted config files only as references. They are not drop-in replacements for raw secrets.

## CLI/source restore notes

Hermes Agent CLI/source is restored as a reproducible source-state layer, not as a full vendored repo:

1. Install or clone Hermes Agent from the upstream remote recorded in `cli/hermes-agent/manifest.json`.
2. Checkout the recorded `git_head`.
3. Apply `cli/hermes-agent/tracked-changes.patch` if present.
4. Copy files from `cli/hermes-agent/untracked/` only after reviewing whether they are still needed.
5. Restore local skill CLIs from `cli/skill-clis/` to `/home/konstantin/code/clis/` if needed, then run each CLI's own tests/doctor commands.

Do not restore `.git`, virtualenvs, pycache, build outputs, or caches from this backup; they are intentionally excluded.

## Decrypt encrypted artifacts

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

After restoring secrets, enforce restrictive permissions:

```bash
chmod 600 ~/.hermes/.env ~/.hermes/auth.json 2>/dev/null || true
chmod 600 ~/.hermes/credentials/* 2>/dev/null || true
```
