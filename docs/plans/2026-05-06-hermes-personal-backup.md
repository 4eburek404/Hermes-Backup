# Plan: Hermes personal backup to GitHub

## Goal
Create a safe, repeatable git backup of Konstantin's Hermes overlay state — settings, curated memory, skills, plugins, cron definitions, personal docs, secrets, `state.db`, and session transcripts — into `https://github.com/4eburek404/Hermes`, with raw secrets and privacy-heavy runtime history committed only as encrypted artifacts.

## Context
- Target repository: `4eburek404/Hermes`, GitHub URL `https://github.com/4eburek404/Hermes`, visibility verified as `PRIVATE`.
- No local clone was found at common paths: `/home/konstantin/Hermes`, `/home/konstantin/code/Hermes`, `/home/konstantin/backups/Hermes`, `/home/konstantin/repos/Hermes`.
- Current Hermes home: `/home/konstantin/.hermes`.
- Upstream Hermes source repo lives at `/home/konstantin/.hermes/hermes-agent` and is explicitly out of backup scope.
- Memory state:
  - Built-in memory: always active, files under `/home/konstantin/.hermes/memories/`.
  - External memory provider: `holographic`, local SQLite DB at `/home/konstantin/.hermes/memory_store.db` with active WAL/SHM sidecars.
- Long-term docs are under `/home/konstantin/docs/` and are part of the durable Hermes context layer.
- Tool availability checked:
  - Available before execution: `git`, `gh`, `sqlite3`, `gpg`, `zstd`, `tar`, `python3`.
  - Installed during execution: `age`.
  - Missing: `git-lfs`.
- GitHub auth is available through `gh` as `4eburek404`; token scopes include `repo` and `workflow`.
- Security constraint: private GitHub is not treated as sufficient protection for raw tokens, OAuth refresh tokens, service account JSON, app passwords, or private keys. Raw secrets must be excluded or encrypted before commit.

## Non-goals
- Do not update Hermes Agent itself.
- Do not restart the gateway.
- Do not change runtime config, cron jobs, memory, skills, plugins, or credentials during planning.
- Do not back up `/home/konstantin/.hermes/hermes-agent` source code; it is upstream repo state, not personal overlay.
- Do not commit raw `.env`, OAuth tokens, service-account JSON, Gmail app password, private keys, or full credential files in plaintext.
- Do not commit volatile runtime files: locks, pids, caches, live WAL/SHM sidecars, logs, screenshots, audio/video cache.
- Do not include raw session history / `state.db` in plaintext. They are now in scope as required encrypted archives because they are large and privacy-sensitive.

## Backup target layout
Proposed local clone path:

```text
/home/konstantin/code/Hermes
```

Proposed repository layout:

```text
README.md
.gitignore
MANIFEST.md
scripts/
  collect-hermes-backup.py
  verify-hermes-backup.py
hermes/
  SOUL.md
  config.yaml.redacted
  env.keys
  memories/
    USER.md
    MEMORY.md
  holographic-memory/
    memory_store.sqlite
  skills/
  plugins/
  cron/
    jobs.json
  backups/
  legacy-plans/
docs/
  README.md
  user-context.md
  infrastructure.md
  runbooks.md
  plans/
external-integrations/
  himalaya/
    config.toml.redacted
  codex/
    config.toml.redacted
secrets-encrypted/
  README.md
  hermes-secrets-YYYYMMDD-HHMMSS.tar.zst.age
session-history-encrypted/
  README.md
  hermes-state-and-sessions-YYYYMMDD-HHMMSS.tar.zst.age
restore/
  README.md
```

## File selection

### Include in plaintext / git-safe form
These are the core backup set.

- `/home/konstantin/docs/`
  - `README.md`
  - `user-context.md`
  - `infrastructure.md`
  - `runbooks.md`
  - `plans/` including active plans and archive
- `/home/konstantin/.hermes/SOUL.md`
- `/home/konstantin/.hermes/memories/USER.md`
- `/home/konstantin/.hermes/memories/MEMORY.md`
- `/home/konstantin/.hermes/skills/`
  - Include installed/custom skills, `.archive/`, references, scripts, templates.
  - Exclude transient usage counters only if secret scan or noise review says they are not useful.
- `/home/konstantin/.hermes/plugins/`
  - Current custom plugin observed: `travelpayouts-flights/`.
- `/home/konstantin/.hermes/cron/jobs.json`
  - Include job definitions because schedules/prompts/model pins are operational state.
  - Do not include `cron/.tick.lock`.
  - Do not include `cron/output/` by default; optional encrypted/archive only if needed for audit history.
- `/home/konstantin/.hermes/backups/`
  - Include old USER/MEMORY/SOUL snapshots if secret scan passes.
- `/home/konstantin/.hermes/plans/`
  - Include legacy Hermes plan files not already under `/home/konstantin/docs/plans/`.
- Redacted transform outputs:
  - `config.yaml.redacted` from `/home/konstantin/.hermes/config.yaml`.
  - `env.keys` from `/home/konstantin/.hermes/.env` containing key names only, no values.
  - `external-integrations/himalaya/config.toml.redacted` from `/home/konstantin/.config/himalaya/config.toml`.
  - `external-integrations/codex/config.toml.redacted` from `/home/konstantin/.codex/config.toml`.

### Include via consistent snapshot, not raw live sidecars
- Holographic memory DB:
  - Source: `/home/konstantin/.hermes/memory_store.db`.
  - Backup method: use SQLite backup API or `sqlite3 .backup` into `hermes/holographic-memory/memory_store.sqlite`.
  - Do not copy live `memory_store.db-wal` / `memory_store.db-shm` directly.
  - After snapshot, verify `PRAGMA integrity_check` on the copied DB.

### Required encrypted backup artifacts
These are in scope for full disaster recovery but must not enter plaintext git. They are copied into a temporary staging directory, compressed with `zstd`, encrypted with `age` to the approved SSH public key, then only the `.tar.zst.age` artifact is committed.

- `/home/konstantin/.hermes/.env`
- `/home/konstantin/.hermes/.env.bak.*`
- `/home/konstantin/.hermes/auth.json`
- `/home/konstantin/.hermes/credentials/gcal_service_account.json`
- `/home/konstantin/.hermes/gmail_app_password`
- Raw `/home/konstantin/.hermes/config.yaml` if it contains any secret-like value.
- `/home/konstantin/.hermes/channel_directory.json` and `/home/konstantin/.hermes/pairing/` unless later reviewed and approved as plaintext-safe.
- `/home/konstantin/.codex/auth.json` if Codex OAuth restore is in scope for the encrypted secret bundle.

Current encryption tool situation:
- `gpg` is available.
- `age` was installed from Ubuntu package `1.1.1-1ubuntu0.24.04.3` during execution so SSH-recipient encryption can be used.
- `git-lfs` is missing.

Default execution decision after the scope change: use `age` SSH-recipient encryption to the local SSH Ed25519 public key `/home/konstantin/.ssh/server_monitor_iOS_app_ed25519.pub`. Test-decrypt with the matching local private key before push. No passphrase or private key is printed or committed.

### Required encrypted state/session backup
These files are now part of the backup scope because Konstantin explicitly asked to include `state.db` and sessions. They must be encrypted and must not appear in plaintext git:

- `/home/konstantin/.hermes/state.db` — about 267 MB, session DB / search state.
- `/home/konstantin/.hermes/state.db-wal`, `state.db-shm` — do not copy raw sidecars; use SQLite backup if needed.
- `/home/konstantin/.hermes/sessions/` — about 623 files / 234 MB observed.
- `/home/konstantin/.hermes/state.db.bak-*` — old large DB backup.

Required method:
- create a consistent SQLite backup of `state.db` into temporary staging;
- copy `sessions/` into the same temporary staging tree;
- optionally include `state.db.bak-*` only if the encrypted artifact remains practical in size, otherwise split it into a separate encrypted archive;
- compress with `zstd`;
- encrypt with `age` to the approved SSH public key;
- check final encrypted file size before git commit because GitHub rejects regular files over 100 MB unless Git LFS is installed/configured. If the encrypted archive is too large, split by archive part/date range or install/configure Git LFS before pushing.

### Exclude
- `/home/konstantin/.hermes/hermes-agent/` — upstream source repo.
- `/home/konstantin/.hermes/bin/tirith` — binary, reinstallable.
- `/home/konstantin/.hermes/logs/` — raw logs, volatile, may contain sensitive snippets.
- `/home/konstantin/.hermes/cache/`, `audio_cache/`, `image_cache/`, screenshots/videos — generated media cache.
- Locks and runtime markers:
  - `.lock`, `.pid`, `gateway.lock`, `gateway.pid`, `auth.lock`, `cron/.tick.lock`.
- Runtime state/noise:
  - `gateway_state.json`, `processes.json`, `.restart_last_processed.json`, `.update_check`.
- Model/dev caches:
  - `models_dev_cache.json`, `ollama_cloud_models_cache.json`, `context_length_cache.yaml` unless later needed for diagnostics.
- Live SQLite WAL/SHM sidecars after creating proper `.backup` snapshots.

## Steps

- [x] Load relevant Hermes/GitHub/plan skills and read `/home/konstantin/docs/plans/README.md`.
- [x] Inspect current Hermes overlay inventory without printing secret values.
- [x] Verify target GitHub repo visibility and local clone absence.
- [ ] Create local clone at `/home/konstantin/code/Hermes` from `https://github.com/4eburek404/Hermes`.
- [ ] Create feature branch before changing repo contents, e.g. `backup/bootstrap-2026-05-06`.
- [ ] Add deny-by-default `.gitignore` for raw secrets, raw sessions, logs, caches, DB sidecars, locks, pids, binaries, and raw `.env`/auth/credential paths, while allowing `*.tar.zst.age` encrypted artifacts under approved directories.
- [ ] Add `README.md`, `MANIFEST.md`, `restore/README.md`, `secrets-encrypted/README.md`, and `session-history-encrypted/README.md` explaining scope and restore order.
- [ ] Write `scripts/collect-hermes-backup.py` to copy/transform the selected files into the repo layout.
- [ ] Implement redaction transforms:
  - [ ] `config.yaml` -> `config.yaml.redacted` with secret-like values replaced.
  - [ ] `.env` -> `env.keys` with names only.
  - [ ] `auth.json` -> provider/key-name inventory only if useful, no token values.
  - [ ] external config redaction for Himalaya/Codex.
- [ ] Implement SQLite snapshot for holographic memory using SQLite backup API or `sqlite3 .backup`.
- [ ] Use/verify `age` SSH-recipient encryption without exposing private keys in chat/tool output.
- [ ] Build required encrypted secret bundle under `secrets-encrypted/` from raw credential sources.
- [ ] Build required encrypted state/session bundle under `session-history-encrypted/` from a consistent `state.db` snapshot plus `sessions/`.
- [ ] Test-decrypt encrypted bundles into a temporary directory and verify expected file names without printing secret values or transcript contents.
- [ ] Run the collector once and inspect `git status --short`.
- [ ] Run a secret-risk scan on the generated repo contents before commit.
- [ ] Verify copied DB with `PRAGMA integrity_check`.
- [ ] Verify no plaintext or encrypted artifact exceeds GitHub regular file limit; if an encrypted archive is near or above 100 MB, split it or install/configure Git LFS before pushing.
- [ ] Commit backup bootstrap on the feature branch.
- [ ] Push branch to `origin`.
- [ ] After review, either merge to main or keep backup branch as the active backup branch, per user decision.
- [ ] Optional later: add scheduled backup job after first manual backup is proven safe.

## Verification
Backup implementation is complete only when all are true:

- Repository exists locally at `/home/konstantin/code/Hermes` and has remote `origin` = `https://github.com/4eburek404/Hermes`.
- Work was done on a non-main feature branch first.
- `git status --short` before commit contains only expected backup files.
- Plaintext repo contains:
  - docs files;
  - `SOUL.md`;
  - built-in memory markdown;
  - skills;
  - plugins;
  - cron `jobs.json`;
  - redacted config/env inventories;
  - holographic memory SQLite snapshot.
- Plaintext repo does not contain raw `.env`, OAuth tokens, service-account private key, Gmail app password, raw `auth.json`, raw session DB, raw session transcripts, logs, cache media, locks, pids, or upstream `hermes-agent` source.
- Encrypted repo artifacts exist for secrets and for `state.db`/sessions, and their manifests list source paths without values/content.
- Encrypted `*.tar.zst.age` artifacts pass a test-decrypt into a temporary directory; decrypted checks are path/count/integrity only, not content printing.
- Secret scan passes on the generated repo content.
- Holographic memory snapshot passes SQLite `PRAGMA integrity_check`.
- `state.db` encrypted bundle contains a SQLite backup that passes `PRAGMA integrity_check` after test-decrypt.
- Commit exists locally with a clear message, e.g. `backup: bootstrap hermes personal overlay`.
- Branch is pushed to GitHub and visible under `4eburek404/Hermes`.

## Risks / pitfalls
- Private GitHub repo is not a substitute for encryption of raw credentials.
- `config.yaml` is mode `0600`; treat it as possibly sensitive even if most secrets live in `.env`.
- `auth.json` contains OAuth tokens and must never be plaintext in git.
- Google Calendar service-account JSON contains private key material and must never be plaintext in git.
- Gmail app password file is small but critical secret; never plaintext.
- Live SQLite WAL/SHM files can produce inconsistent backups if copied directly; use SQLite backup.
- Session DB/history is large and privacy-sensitive; include only as encrypted archive, never plaintext.
- GitHub rejects regular files over 100 MB; `git-lfs` is currently missing.
- Encrypted archives can still be too large for normal GitHub git pushes; size must be measured after compression/encryption, not guessed.
- Redaction scripts must fail closed: if a file cannot be safely redacted, skip it and report, rather than committing it.
- Secret scanners can false-negative; combine explicit denylist with regex scan.
- Restoring from backup must preserve file modes for sensitive files, especially `0600` credentials.

## Decisions required before encrypted/full backup
- Encryption mode chosen during execution: `age` SSH-recipient encryption to `/home/konstantin/.ssh/server_monitor_iOS_app_ed25519.pub`.
- If encrypted state/session archive is over GitHub's regular file limit: split archive, install/configure Git LFS, or store the large encrypted artifact outside git and commit only manifest/checksum?
- Include Telegram channel/pairing files plaintext, redacted, or encrypted? Current default: encrypted.
- After first manual backup: schedule automatic backup cron or keep manual-only?

## Status
Current status: in_progress

## Notes
- 2026-05-06: Inventory completed. Plan intentionally stops before cloning/pushing because user requested file selection and written plan first.
- 2026-05-06: Target repo is private, but raw secrets remain encrypted-only/excluded by default.
- 2026-05-06: Scope updated after user decision: secrets, `state.db`, and sessions are included in backup as required encrypted artifacts, not plaintext.
