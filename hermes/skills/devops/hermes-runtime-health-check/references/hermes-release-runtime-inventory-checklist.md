# Hermes Release Runtime Inventory

Full inventory checklist to run **before writing release automation scripts**. This is broader than the 5-sign health check — it captures the complete release/runtime/state picture.

## When to Run

- Before writing release scripts
- Before/after release-dir symlink switch
- When documenting current state for a release plan
- As a snapshot before any batch of systemd/config changes

## Operating Rule

**Read-only. No mutation.** Do not restart gateway, switch symlinks, edit config, install packages, or touch state files.

## Automated Alternative

The `scripts/hermes_release_preflight.py` script automates most of this inventory plus safety validation (R14D-1 state files, R14D-2 holographic DB/config/artifact-root, skills architecture). It produces structured `release_metadata.json` with all check results.

```bash
python scripts/hermes_release_preflight.py \
  --repo /home/konstantin/.hermes/hermes-agent \
  --hermes-home /home/konstantin/.hermes \
  --extras messaging --replace-rc [--allow-dirty]
```

R14D-2 fields in metadata: `memory_db_exists`, `memory_db_integrity_ok`, `memory_db_facts_count`, `memory_db_entities_count`, `memory_db_status`, `config_yaml_exists`, `config_yaml_readable`, `env_exists`, `env_readable`, `tool_output_compaction_block_exists`, `compaction_enabled`, `compaction_artifact_root`, `compaction_config_ok`, `artifact_root_exists`, `artifact_root_resolved`, `artifact_root_under_hermes_home`, `artifact_root_is_tmp`, `artifact_root_writable`, `artifact_root_status`.

## Inventory Checklist

### 1. Active Runtime
```bash
readlink -f /home/konstantin/.hermes/hermes-agent
ls -la /home/konstantin/.hermes/hermes-agent
systemctl --user status hermes-gateway --no-pager -n 40
```

### 2. Systemd Unit
```bash
systemctl --user cat hermes-gateway
```

### 3. Releases
```bash
ls -la /home/konstantin/.hermes/releases
find /home/konstantin/.hermes/releases -maxdepth 2 -type f -name 'pyproject.toml' -print
```

### 4. Active Venv Dependencies
```bash
/home/konstantin/.hermes/hermes-agent/venv/bin/python -c "import telegram; print(telegram.__version__)"
/home/konstantin/.hermes/hermes-agent/venv/bin/python -m pip show python-telegram-bot || true
```

### 5. Skills
```bash
find /home/konstantin/.hermes/hermes-agent/skills -maxdepth 3 -name 'SKILL.md' | wc -l
find /home/konstantin/.hermes/skills -maxdepth 3 -name 'SKILL.md' | wc -l
/home/konstantin/.hermes/hermes-agent/venv/bin/hermes skills list | head -80
```

### 6. State Files
```bash
ls -l /home/konstantin/.hermes/MEMORY.md /home/konstantin/.hermes/USER.md /home/konstantin/.hermes/SOUL.md 2>/dev/null || true
```

### 7. Holographic DB
```bash
sqlite3 /home/konstantin/.hermes/memory_store.db "PRAGMA integrity_check;" || true
sqlite3 /home/konstantin/.hermes/memory_store.db ".tables" || true
```

### 8. Config / Artifacts
```bash
grep -nA12 "tool_output_compaction" /home/konstantin/.hermes/config.yaml || true
readlink -f /home/konstantin/.hermes/tool-output-artifacts || true
ls -ld /home/konstantin/.hermes/tool-output-artifacts || true
```

### 9. Fresh Critical Logs
```bash
journalctl --user -u hermes-gateway --since "30 minutes ago" --no-pager \
  | grep -Ei "traceback|exception|importerror|modulenotfounderror|python-telegram-bot not installed|No adapter available|failed to connect|file is not a database|503|ToolOutputCompactionConfig" \
  | tail -100 || true
```

## Report Sections

- **A. Active target** — symlink resolution + target release
- **B. Gateway status** — PID, memory, CPU, uptime, child processes
- **C. Systemd ExecStart** — ExecStart, WorkingDirectory, PATH, key settings
- **D. Releases found** — all release dirs, which is active
- **E. Telegram dependency status** — version, location
- **F. Skills counts** — built-in vs user skills
- **G. MEMORY/USER/SOUL status** — file existence, sizes, last modified
- **H. Holographic integrity** — DB check + tables
- **I. Compaction artifact_root** — path, symlink status
- **J. Fresh critical logs** — errors in recent journal
- **K. Immediate risks** — mismatches, orphaned releases, fragility

## R14A Case Study

Ran on 2026-05-12 before release scripts. Found critical mismatch:

- **Active symlink:** `hermes-agent → releases/hermes-agent-fe6dbf61`
- **Systemd WorkingDirectory:** `releases/hermes-agent-d1c549c4` (old release)
- **PATH** also referenced old release node_modules

Fixed in R14A-2 via drop-in override. Result: gateway restarted cleanly with canonical symlink paths.

## R14D-2 Case Study

R14D-2 added automated preflight checks for:
- Holographic DB: `PRAGMA integrity_check`, facts/entities counts (read-only, never vacuum/migrate)
- Config files: config.yaml readable, .env existence, tool_output_compaction block, artifact_root ≠ /tmp
- Artifact root: exists, directory, under hermes_home, not /tmp/symlink, writable, permissions 0o700

Key testing pitfall discovered: old safety tests asserted `"config.yaml" not in src` and `"memory_store.db" not in src`. When R14D-2 added read-only checks referencing these files, those tests broke. Fix: replace "no mention" assertions with function-scoped mutation denylist checks (no `write_text`, `INSERT`, `UPDATE`, `DELETE`, `VACUUM` in the relevant function body).