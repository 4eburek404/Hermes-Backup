# Hermes personal overlay backup scope — Konstantin, 2026-05-06

Use this reference when asked to back up Hermes Agent settings, memory, skills, plugins, docs, cron, or session/state data that live **on top of** the upstream Hermes repo.

## Verified environment facts from the session

- Hermes home: `/home/konstantin/.hermes`.
- Upstream source checkout: `/home/konstantin/.hermes/hermes-agent` — excluded from personal overlay backup unless source patches are explicitly requested.
- Target backup repo: `https://github.com/4eburek404/Hermes`, private.
- Local backup clone: `/home/konstantin/code/Hermes`.
- Backup branch: `backup/bootstrap-2026-05-06`.
- Commit: `9a212c4f2ffa152e82ddb101574c676fe64fd2dd` (`backup: bootstrap hermes personal overlay`).
- GitHub default branch became `backup/bootstrap-2026-05-06` after the bootstrap push.
- `age` was initially missing and was installed from Ubuntu apt package `1.1.1-1ubuntu0.24.04.3`.
- `git-lfs` was missing and not used.
- Encryption recipient: SSH Ed25519 public key `/home/konstantin/.ssh/server_monitor_iOS_app_ed25519.pub`.
- Matching private key existed locally at `/home/konstantin/.ssh/server_monitor_iOS_app_ed25519` with mode `0600`; never print or back up the private key plaintext.

## Default plaintext backup set

Include these in git-safe form:

- `/home/konstantin/docs/` — durable docs, runbooks, plans.
- `/home/konstantin/.hermes/SOUL.md`.
- `/home/konstantin/.hermes/memories/USER.md` and `MEMORY.md`.
- `/home/konstantin/.hermes/skills/` including `.archive/`, references, templates, scripts.
- `/home/konstantin/.hermes/plugins/`.
- `/home/konstantin/.hermes/hooks/`.
- `/home/konstantin/.hermes/backups/` and `/home/konstantin/.hermes/plans/` if secret scan passes.
- `/home/konstantin/.hermes/cron/jobs.json` only, not cron output/locks.
- CLI backup layer after Konstantin's 2026-05-06 scope expansion:
  - `/home/konstantin/.hermes/hermes-agent` is still not vendored wholesale; store manifest + `git diff --binary --full-index` patch + safe untracked source files under `cli/hermes-agent/`.
  - `/home/konstantin/code/clis/` is included as source snapshots under `cli/skill-clis/`, excluding `.git`, virtualenvs, caches, pycache, build/dist, and `*.egg-info`.
- Redacted/inventory transforms:
  - `config.yaml` → `config.yaml.redacted`.
  - `.env` → `env.keys` with variable names only.
  - `auth.json` → inventory/shape only, no token values.
  - Codex/Himalaya/external integration config → redacted copies or key inventories only.

## SQLite memory snapshot

For holographic memory, do not copy live WAL/SHM files directly. Create a consistent backup of:

```text
/home/konstantin/.hermes/memory_store.db
```

with SQLite backup API or `sqlite3 .backup`, then verify the copied DB with:

```sql
PRAGMA integrity_check;
```

The bootstrap backup included a verified snapshot at:

```text
hermes/holographic-memory/memory_store.sqlite
```

## Required encrypted artifacts after user scope change

Konstantin explicitly decided that secrets, `state.db`, and sessions are also in backup scope. They must still never be committed in plaintext, even to a private GitHub repo. Commit only encrypted `.tar.zst.age` artifacts plus non-secret manifests/checksums.

Required encrypted secret bundle sources:

- `.env`, `.env.bak.*`.
- `auth.json`.
- `credentials/gcal_service_account.json`.
- `gmail_app_password`.
- raw `config.yaml` if it contains secret-like values.
- `channel_directory.json` and `pairing/` by default, unless later approved as plaintext-safe.
- Codex OAuth/auth files if Codex restore is in scope.

Required encrypted state/session bundle sources:

- consistent SQLite backup of `state.db` — do not copy live WAL/SHM directly.
- `sessions/`.
- old `state.db.bak-*` only if practical in size; otherwise separate encrypted archive.

Bootstrap artifacts created with timestamp `20260506-123053`:

```text
secrets-encrypted/hermes-secrets-20260506-123053.tar.zst.age
secrets-encrypted/manifest-20260506-123053.json
session-history-encrypted/hermes-state-and-sessions-20260506-123053.tar.zst.age.part000
session-history-encrypted/hermes-state-and-sessions-20260506-123053.tar.zst.age.part001
session-history-encrypted/manifest-20260506-123053.json
```

Still exclude from the default backup unless explicitly requested separately:

- logs/cache/audio/video/screenshots and other generated media/noise.

## Scripts created in the backup repo

The bootstrap repo contains reusable scripts:

```text
scripts/collect-hermes-backup.py
scripts/verify-hermes-backup.py
```

`collect-hermes-backup.py` responsibilities:

- collect plaintext overlay into the backup repo;
- create redacted config/env/auth inventories;
- create consistent SQLite snapshots;
- sanitize plaintext copies for high-risk token-shaped literals before commit;
- create encrypted `age` artifacts and manifests.

`verify-hermes-backup.py` responsibilities:

- validate manifests/checksums;
- test-decrypt/list encrypted artifacts with `age`;
- run SQLite `PRAGMA integrity_check` on copied DBs;
- scan for raw denied filenames;
- scan plaintext for high-risk secret/token patterns;
- check GitHub hard file limit.

## Plan file lifecycle

Plan was created at:

```text
/home/konstantin/docs/plans/2026-05-06-hermes-personal-backup.md
```

After successful push and verification it was updated to `Current status: done` and archived to:

```text
/home/konstantin/docs/plans/archive/2026/done/2026-05-06-hermes-personal-backup.md
```

## Verification result from bootstrap

Passed checks:

- `python3 scripts/verify-hermes-backup.py` exit `0`.
- Holographic memory SQLite snapshot integrity: `ok`.
- `state.db` backup integrity: `ok`.
- Encrypted secrets bundle test-decrypt/list: ok.
- Encrypted state/session bundle test-decrypt/list: ok.
- Plaintext high-risk secret scan findings: `0`.
- Raw denied filename scan: no raw denied filenames found.
- No file exceeded GitHub hard `100 MB` regular-file limit.
- Remote branch verified at commit `9a212c4f2ffa152e82ddb101574c676fe64fd2dd`.

Non-blocking GitHub warnings:

- `session-history-encrypted/hermes-state-and-sessions-20260506-123053.tar.zst.age.part000` was `95.00 MB`, above GitHub's recommended `50 MB`.
- `session-history-encrypted/hermes-state-and-sessions-20260506-123053.tar.zst.age.part001` was `56.26 MB`, above GitHub's recommended `50 MB`.
- Push succeeded because both were under the hard `100 MB` limit. Future runs should prefer ~45–49 MB split chunks or Git LFS for cleaner repo hygiene.

## Pitfalls and lessons learned

- Private GitHub does not make raw secrets safe.
- `memory_store.db-wal`/`memory_store.db-shm` and `state.db` sidecars are live runtime files; snapshot DBs consistently instead of raw-copying sidecars.
- `state.db` and session transcripts are large and privacy-sensitive; after Konstantin's scope change they are required encrypted artifacts, never plaintext.
- GitHub rejects regular files over 100 MB; it warns above 50 MB. Passing the hard limit check is not the same as clean long-term Git hygiene.
- Redaction must fail closed: if a file cannot be safely redacted, skip and report instead of committing.
- Secret scanners can flag token-shaped examples inside skill/docs files. Do not weaken the scanner; sanitize the plaintext backup copy (replace high-risk token-shaped literals) and rerun verification.
- `age` SSH-recipient encryption works well for non-interactive backup, but restore depends on preserving the matching private SSH key locally. Do not print or commit the private key.
- Do not run `hermes update`, `git pull` in the upstream Hermes Agent repo, `/restart`, or cron/config mutations as part of backup unless the user explicitly expands scope.
