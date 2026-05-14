# Hermes Release Candidate Dependency Preflight

## Why this exists

Previous incident: gateway failed to start after a release switch because the RC venv was built without `python-telegram-bot`. The `messaging` extras were not installed. The gateway restarted 3 times in a crash loop before succeeding on the 4th attempt — and only because the old working directory happened to have the dependency.

The preflight catches missing dependencies during the build phase, before any production switch. This eliminates the "deploy and pray" pattern.

R14C-1 addition: active symlink and systemd release-dir path checks. A misconfigured systemd unit pointing to a concrete release path (instead of the symlink) causes breakage after release rotation. The preflight now validates this at build time.

## Pattern

```bash
python scripts/hermes_release_preflight.py \
  --repo <path-to-hermes-git-repo> \
  --hermes-home /home/konstantin/.hermes \
  --extras messaging \
  --commit <hash>           # default: HEAD
  --replace-rc              # overwrite existing RC (refuses if RC = active target)
  --allow-dirty             # proceed even if working tree dirty
```

### What it does

1. **Repo checks** — git repo, clean working tree (unless `--allow-dirty`), commit resolution, remote info
2. **RC build** — `git archive <commit> | tar -x` into `~/.hermes/releases/hermes-agent-<commit12>` (never copies active runtime)
3. **Venv + install** — `python3 -m venv --system-site-packages`, then `venv/bin/python -m pip install <rc>[extras]`
4. **Dependency preflight** — validates:
   - `import telegram` + version
   - `import hermes_cli.main`
   - `import run_agent`
   - `from tools.skills_sync import sync_skills`
   - `from agent.skill_utils import get_all_skills_dirs`
   - `pip show python-telegram-bot`
   - `hermes --help`, `hermes gateway --help`, `hermes skills --help`
5. **Metadata** — writes `release_pip_freeze.txt` and `release_metadata.json`
6. **Active symlink check (R14C-1)** — verifies:
   - `~/.hermes/hermes-agent` exists and is a symlink
   - `readlink -f` target exists
   - resolved target is under `~/.hermes/releases/`
   - resolved target contains `pyproject.toml` and `venv/bin/python`
   - Any failure → FAIL
7. **Systemd path check (R14C-1)** — read-only verification:
   - Reads `systemctl --user show hermes-gateway -p ExecStart -p WorkingDirectory -p Environment`
   - `ExecStart` must use symlink path (`~/.hermes/hermes-agent/venv/bin/python`), not a concrete release path
   - `WorkingDirectory` must use symlink path (`~/.hermes/hermes-agent`)
   - `Environment` PATH must not contain concrete release paths (`~/.hermes/releases/hermes-agent-*`)
   - Any concrete release path → FAIL
   - **Only reads** — never calls `systemctl start/stop/restart/enable/disable`

### Safety guarantees

- Never switches the `~/.hermes/hermes-agent` symlink
- Never calls `systemctl start/stop/restart/enable/disable` — read-only `systemctl --user show/cat` only
- Never edits the live systemd unit file
- Never edits `config.yaml` or `.env`
- Never touches `memory_store.db`, `MEMORY.md`, `USER.md`, `SOUL.md`
- Never creates, edits, or deletes `MEMORY.md`, `USER.md`, `SOUL.md`
- Refuses to remove directories outside `~/.hermes/releases/` (even with `--replace-rc`)
- Refuses to remove RC if it matches the active production target (even with `--replace-rc`)
- Refuses dirty repo without `--allow-dirty`
- All pip commands use `venv/bin/python -m pip` (never system pip)

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | PASS |
| 1 | Fatal (config, repo, path) |
| 2 | FAIL (imports/CLI/symlink/systemd checks failed) |

### Tests

Source-based structural tests verify 70 invariants (R14C-1 through R14D-1):
- Non-git repo fails
- Dirty repo fails unless `--allow-dirty`
- Commit short hash is 12 chars
- Existing RC fails unless `--replace-rc`
- `--replace-rc` refuses paths outside `releases/`
- Build uses `git archive` (not cp active runtime)
- Install uses `venv/bin/python -m pip`
- Extras include `messaging`
- Preflight includes `import telegram`
- Preflight includes `pip show python-telegram-bot`
- Metadata JSON contains required fields + `production_switch: false`
- No `systemctl start/stop/restart/enable/disable` in source (read-only `show`/`cat` allowed)
- No symlink write operations (`symlink_to`, `os.symlink`) in source
- No `config.yaml` references in source
- No `memory_store.db` references in source
- Active symlink check: missing symlink → FAIL
- Active symlink check: target outside releases/ → FAIL
- Active symlink check: target under releases/ → passes
- Active symlink check: target without venv/python → FAIL
- Systemd ExecStart check exists in source
- Systemd ExecStart fails on concrete release path
- Systemd WorkingDirectory check exists in source
- Systemd WorkingDirectory fails on concrete release
- Systemd PATH concrete release check exists in source
- Systemd PATH symlink paths ok
- Metadata contains R14C-1 fields (`active_symlink_path`, `active_target`, `active_target_under_releases`, `systemd_execstart_symlink_based`, `systemd_working_directory_symlink_based`, `systemd_path_contains_concrete_release`, `systemd_release_dir_paths_ok`)
- No systemctl mutation (start/stop/restart/enable/disable) in source
- No symlink write or config.yaml or memory_store.db in source

### release_metadata.json R14C-1 fields

```json
{
  "active_symlink_path": "/home/konstantin/.hermes/hermes-agent",
  "active_target": "/home/konstantin/.hermes/releases/hermes-agent-fe6dbf61",
  "active_target_under_releases": true,
  "systemd_execstart_symlink_based": true,
  "systemd_working_directory_symlink_based": true,
  "systemd_path_contains_concrete_release": false,
  "systemd_release_dir_paths_ok": true
}
```

## Integration with release workflow

The preflight is step 1 of a 3-step release process:

1. **Preflight** (`hermes_release_preflight.py`) — build RC, validate dependencies, check symlink + systemd paths
2. **Switch** (future `hermes_release_switch.py`) — atomically update symlink, update systemd drop-in if needed, restart gateway
3. **Verify** — health check, gateway status, Telegram connectivity

## R14C-2: Skills architecture checks

Added skills architecture validation:

- **RC bundled skills**: `<RC>/skills` exists with SKILL.md files > 0
- **Runtime skills dir**: `~/.hermes/skills` is not a symlink, does not resolve to `<RC>/skills`, is inside hermes_home
- **Bundled manifest**: checks `.bundled_manifest` existence, readability, size
- **get_all_skills_dirs()**: state dir first, bundled source present and resolves to RC
- **sync_skills():** runs within RC's venv and CWD; verifies runtime skills count matches
- **hermes skills list:** validates RC can list skills
- **Import provenance (R14C-2):** `hermes_constants.py` file resolves to the RC directory

All checks run inside the RC's venv with `cwd=rc_dir` to avoid CWD leak and editable-install shadowing (see `systematic-debugging` skill pitfall on subprocess CWD leak).

## R14C-3: Metadata bug fix

**Bug:** `skills_bundled_source_resolves_to_rc` was `None` in `release_metadata.json` when skills architecture checks passed.

**Root cause:** In `check_skills_architecture()`, the local variable `skills_bundled_source_resolves_to_rc` was set to `True` inside the success loop, but only `results["skills_bundled_source_present"]` was written to the results dict. The failure branch (`else`) correctly wrote the field as `False`. At metadata assembly, `results.get("skills_bundled_source_resolves_to_rc")` returned `None` for the success case because the key was never inserted.

**Fix:** Added `results["skills_bundled_source_resolves_to_rc"] = skills_bundled_source_resolves_to_rc` after the existing `results["skills_bundled_source_present"]` line. Commit: `abcbf1df0`.

**General lesson:** When adding a new field to a results/metadata dict inside a conditional block, diff the success and failure branches to ensure both write the key. The `results.get()` pattern silently returns `None` instead of raising `KeyError`, making this class of bug hard to detect without explicit `None`-checks in tests.

### release_metadata.json R14C-2/R14C-3 fields

```json
{
  "rc_bundled_skills_dir": "/home/konstantin/.hermes/releases/hermes-agent-b8f3a0f6e51a/skills",
  "rc_bundled_skills_count": 97,
  "runtime_skills_dir": "/home/konstantin/.hermes/skills",
  "runtime_skills_count_before_sync": 97,
  "runtime_skills_count_after_sync": 97,
  "runtime_skills_is_symlink": false,
  "bundled_manifest_exists": true,
  "bundled_manifest_size_bytes": 1234,
  "skills_dirs": ["...list from get_all_skills_dirs()..."],
  "skills_state_dir_first": true,
  "skills_bundled_source_present": true,
  "skills_bundled_source_resolves_to_rc": true,
  "sync_skills_ok": true,
  "hermes_skills_list_ok": true,
  "hermes_constants_file": "/path/to/rc/hermes_constants.py",
  "hermes_constants_under_rc": true
}
```

## R14D-1: State files read-only checks

Added read-only verification of persistent state files in `~/.hermes/`:

- **MEMORY.md, USER.md, SOUL.md** — each checked for:
  - `exists`: yes/no
  - `readable`: yes/no
  - `size_bytes`: file size (0 if missing)
  - `mtime_iso`: ISO timestamp (None if missing/unreadable)
  - `status`: one of `missing_warning`, `ok`, `unreadable_fail`

### Rules

- Missing file → **warning**, not fail (preflight result stays PASS)
- Exists but unreadable → **FAIL**
- Directory instead of file → **FAIL**
- Symlink inside `hermes_home` and readable → **OK**
- Symlink pointing outside `hermes_home` → **FAIL**
- File contents are **never** printed or logged

### Structured report

```
State files:
- MEMORY.md: missing / ok / unreadable
- USER.md: missing / ok / unreadable
- SOUL.md: missing / ok / unreadable
- State files result: PASS/WARN/FAIL
```

- Only missing warnings → overall PASS with warnings
- Any unreadable/directory/external-symlink → overall FAIL

### Safety guarantees (unchanged)

The preflight **never** creates, edits, or deletes MEMORY.md, USER.md, SOUL.md, or `memory_store.db`.

### release_metadata.json R14D-1 fields

```json
{
  "memory_md_exists": false,
  "memory_md_readable": false,
  "memory_md_size_bytes": 0,
  "memory_md_mtime": null,
  "user_md_exists": false,
  "user_md_readable": false,
  "user_md_size_bytes": 0,
  "user_md_mtime": null,
  "soul_md_exists": true,
  "soul_md_readable": true,
  "soul_md_size_bytes": 8505,
  "soul_md_mtime": "2026-05-07T14:12:04.414468+00:00",
  "state_files_warnings": ["MEMORY.md missing (warning)", "USER.md missing (warning)"],
  "state_files_ok": true
}
```

### Tests (R14D-1, items 55–70)

16 new structural tests:

- 55–57: missing MEMORY.md/USER.md/SOUL.md is warning, not fail
- 58–60: existing readable MEMORY.md/USER.md/SOUL.md passes
- 61–62: unreadable MEMORY.md/USER.md fails
- 63: directory instead of MEMORY.md fails
- 64: symlink inside hermes_home passes (if readable)
- 65: symlink outside hermes_home fails
- 66: report does not include file contents
- 67: metadata contains all R14D-1 fields (including `_mtime` per file)
- 68: preflight does not create MEMORY.md/USER.md/SOUL.md
- 69: preflight does not edit MEMORY.md/USER.md/SOUL.md
- 70: preflight does not touch memory_store.db

**Known pitfall (R14D-1 fix):** When writing metadata fields from `check_state_files()` results, remember to include `mtime` fields explicitly in the metadata dict. The initial implementation added `*_exists`, `*_readable`, `*_size_bytes` but forgot `*_mtime`, causing `null` instead of ISO timestamp in `release_metadata.json`. Always verify the metadata dict has a 1:1 match with the results dict keys you intend to emit.

## Related docs

- `docs/hermes-release-preflight.md` — user-facing usage guide
- `docs/hermes-release-runtime-inventory.md` — runtime state snapshot (R14A)
- `docs/hermes-systemd-release-dir-paths.md` — systemd path convention
- `ops/systemd/hermes-gateway.release-dir-paths.conf` — drop-in template
- Cross-skill: `systemd-web-service-deployment` skill, pitfall #9 and `references/release-dir-systemd-paths.md` cover the same symlink-vs-concrete-path convention at the deployment level.