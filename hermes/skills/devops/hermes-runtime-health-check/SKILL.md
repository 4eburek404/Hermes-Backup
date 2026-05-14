---
name: hermes-runtime-health-check
description: "Read-only production health check for Hermes Agent: gateway status, compaction config, artifact integrity, critical logs, and synthetic live test. Use before/after config changes, after gateway restarts, or on any suspicion of degraded Telegram behaviour."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [devops, hermes, health-check, compaction, monitoring, systemd, telegram]
    related_skills: [systemd-web-service-deployment]
---

# Hermes Runtime Health Check

## Overview

Read-only production health check for Hermes Agent runtime. Monitors 5 signs, not "everything": gateway alive, compaction config correct, no fresh critical errors, artifacts writing to correct root, synthetic live test passes. Use before/after config changes, after gateway restarts, or on any suspicion of degraded Telegram behaviour.

Canonical reference docs: `docs/hermes-runtime-management.md` (runtime scheme, deploy/rollback), `docs/hermes-compaction-operational-status.md` (R13A status snapshot).

## When to Use

- Before and after any Hermes config change
- After `systemctl --user restart hermes-gateway`
- After release-dir switch (symlink change)
- When Telegram behaviour feels degraded or suspicious
- Periodic manual audit (daily/weekly)
- As smoke test after server reboot

Do **not** use this skill for:

- Debugging unknown Hermes runtime problems — use `systematic-debugging` first
- Code review of Hermes source changes — use `requesting-code-review`
- General system health checks — use `systemd-web-service-deployment` for external web services

## Operating Rule

**Read-only. No mutation.** Check, interpret, report. Do not restart gateway, edit config, move artifacts, or delete files. If something is broken, report what and suggest the appropriate rollback path from `hermes-runtime-management.md`.

## 5-Sign Health Check

Monitor these, not everything:

1. **Gateway alive** — `systemctl --user is-active hermes-gateway` → `active`
2. **Compaction config correct** — `tool_output_compaction.enabled: true`, `rollout_platforms: [telegram]`, `enabled_output_kinds: [terminal]`, `artifact_root` points to persistent path
3. **No fresh critical errors** — no `ImportError`, `ModuleNotFoundError`, `file is not a database`, `503`, `ToolOutputCompactionConfig`, `No adapter available`; when scanning flat log files, filter by timestamp since the restart/change, not just `tail`, because old tracebacks can dominate the tail.
4. **Artifacts in correct root** — new artifacts only in configured `artifact_root`, not in `/tmp` or elsewhere
5. **Compaction actually fires** — synthetic test: large terminal output → compacted summary in Telegram, new `.raw` artifact in root
6. **Skill integrity** — runtime skills present and non-stale, custom skills accounted for
7. **Memory/HRR integrity after dependency or release work** — active venv imports `numpy`, `plugins.memory.holographic.holographic._HAS_NUMPY` is true, `hrr.encode_text(..., 32)` works, `memory_store.db` integrity is `ok`, and `facts_with_hrr == facts`. For `fact_store probe/reason/related`, merely returning rows is insufficient: confirm the path is not FTS fallback (e.g. HRR result shape lacks `fts_rank`, while `search()`/fallback returns it).

## Raw-Leak Suspect Follow-up

When a previous compaction audit reports "raw leak" or "large raw output" suspects, do not jump straight to code changes. First classify whether the rows are active production leaks or historical/out-of-scope carry-over. Use `references/raw-leak-suspect-followup.md`: sanitized locator-only scanning, active-release symlink mtime as the activation cutoff, strict recent-session fallback, artifact/log aggregate checks, and a no-raw-payload reporting format.

## Quick Manual Check (one-liner)

```bash
echo "== runtime =="
readlink -f /home/konstantin/.hermes/hermes-agent

echo "== gateway =="
systemctl --user is-active hermes-gateway

echo "== compaction config =="
grep -nA12 "tool_output_compaction" ~/.hermes/config.yaml || true

echo "== latest artifacts =="
find /home/konstantin/.hermes/tool-output-artifacts -maxdepth 4 -type f \
  -printf '%TY-%Tm-%Td %TH:%TM %s %p\n' 2>/dev/null | sort | tail -10

echo "== recent critical logs =="
journalctl --user -u hermes-gateway --since "30 minutes ago" --no-pager \
  | grep -Ei "ImportError|ModuleNotFoundError|traceback|exception|file is not a database|503|server overloaded|ToolOutputCompactionConfig|No adapter available|python-telegram-bot" \
  || true

echo "== skill integrity =="
echo "Runtime SKILL.md count:"
find ~/.hermes/skills -maxdepth 4 -type f -name 'SKILL.md' | wc -l
echo "Manifest lines:"
wc -l ~/.hermes/skills/.bundled_manifest 2>/dev/null || echo "(no manifest)"
echo "Non-bundled (custom) skills:"
comm -23 <(find ~/.hermes/skills -maxdepth 4 -type f -name 'SKILL.md' -printf '%P\n' | sort) \
         <(find ~/.hermes/hermes-agent/skills -maxdepth 4 -type f -name 'SKILL.md' -printf '%P\n' | sort) \
  || true

echo "== memory / HRR =="
~/.hermes/hermes-agent/venv/bin/python - <<'PY'
import sqlite3
from pathlib import Path
from plugins.memory.holographic import holographic as hrr
p = Path.home() / '.hermes' / 'memory_store.db'
v = hrr.encode_text('runtime health hrr check', 32)
con = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
print('hrr_numpy=', bool(hrr._HAS_NUMPY), 'dim=', len(v))
print('integrity=', con.execute('PRAGMA integrity_check').fetchone()[0])
print('facts,total_hrr=', con.execute('SELECT COUNT(*), SUM(hrr_vector IS NOT NULL) FROM facts').fetchone())
con.close()
PY
```

## R13A Synthetic Live Test

This test proves that compaction is actually working end-to-end: terminal output → artifact → compacted summary in Telegram.

### Before test

```bash
find /home/konstantin/.hermes/tool-output-artifacts -maxdepth 4 -type f | wc -l
```

### Execute in Telegram

Ask Hermes via Telegram to run:

```bash
python - <<'PY'
for i in range(120):
    print(f"RUNTIME_HEALTH_LINE_{i:03d} " + "x" * 120)
PY
```

### After test — verify

```bash
# New artifact appeared
find /home/konstantin/.hermes/tool-output-artifacts -maxdepth 4 -type f \
  -printf '%TY-%Tm-%Td %TH:%TM %s %p\n' | sort | tail -5

# NOT in old /tmp location
find /tmp/hermes-tool-output-compaction-artifacts -maxdepth 4 -type f \
  -name "*RUNTIME_HEALTH*" 2>/dev/null | wc -l   # expected: 0

# No fresh critical errors
journalctl --user -u hermes-gateway --since "5 minutes ago" --no-pager \
  | grep -Ei "ImportError|ModuleNotFoundError|traceback|exception|file is not a database|503" \
  || echo "(no critical errors)"
```

### Expected result

- Telegram response is a **compacted summary** (not 120 raw lines)
- New `.raw` artifact in `/home/konstantin/.hermes/tool-output-artifacts`
- No new artifact in `/tmp/hermes-tool-output-compaction-artifacts`
- No critical errors in logs

## Interpretation

### Normal

- gateway: `active`
- `tool_output_compaction.enabled: true`
- `rollout_platforms: [telegram]`
- `enabled_output_kinds: [terminal]`
- `artifact_root: /home/konstantin/.hermes/tool-output-artifacts`
- New `.raw` artifacts appear after large terminal outputs
- Telegram gets summary, not full raw stdout
- No fresh `ImportError` / `503` / traceback
- All expected custom skills present (comm output matches known list)

### Degraded (needs attention)

- gateway `inactive`
- Telegram not responding
- Large terminal output returned **in full** (no compaction)
- Artifact did NOT appear after large terminal output
- Artifact appeared **outside** configured `artifact_root`
- `ImportError` / `ToolOutputCompactionConfig` / `file is not a database` in logs
- `503` on small ping

### When to roll back

If degraded and impacting Telegram usability:

1. **Soft rollback** — disable compaction, keep runtime:
   ```yaml
   tool_output_compaction:
     enabled: false
   ```
   ```bash
   systemctl --user restart hermes-gateway
   ```

2. **Hard rollback** — switch to previous release:
   ```bash
   systemctl --user stop hermes-gateway
   ln -sfn /home/konstantin/.hermes/hermes-agent.pre_r12a_messagingfix_20260512051431 /home/konstantin/.hermes/hermes-agent
   systemctl --user start hermes-gateway
   ```

Full rollback procedures: `docs/hermes-runtime-management.md`.

## Watchlist

Signs to watch after any runtime/config change (next 1–2 days):

- `503` on small ping
- `ImportError` / `ModuleNotFoundError`
- `file is not a database`
- Artifacts outside configured root
- Raw secrets in artifacts or messages
- Raw large terminal output returned fully (uncompacted)

## Automated Preflight Check

The `scripts/hermes_release_preflight.py` script in the Hermes repo automates most of the 5-sign health check plus additional safety checks (state files, holographic DB, config, artifact root, skills architecture). It is the canonical tool for RC validation and pre-deployment audits.

```bash
# Full preflight (no production switch):
python scripts/hermes_release_preflight.py \
  --repo /home/konstantin/.hermes/hermes-agent \
  --hermes-home /home/konstantin/.hermes \
  --extras messaging \
  --replace-rc

# With --allow-dirty for work-in-progress:
python scripts/hermes_release_preflight.py \
  --repo /home/konstantin/.hermes/hermes-agent \
  --hermes-home /home/konstantin/.hermes \
  --extras messaging --replace-rc --allow-dirty
```

R14D-2 added read-only checks for: holographic memory DB integrity, config.yaml/.env presence and readability, tool_output_compaction config validation, and artifact_root safety (not /tmp, under hermes_home, writable). All checks are strictly non-mutating — never modifies, vacuums, migrates, or repairs DB; never edits config; never creates/deletes artifact files.

## Common Pitfalls

1. **Restarting gateway without checking logs first.** The `## Quick Manual Check` is read-only — use it before and after any restart to detect ImportError/503 regressions.
2. **Trusting `systemctl is-active` alone.** An active gateway can still have broken compaction, auth failures, or stale release symlink. Always run the full 5-sign check.
3. **Forgetting to check artifact root after config change.** If `artifact_root` was changed but gateway was not restarted, artifacts may still land in the old location. Verify with a synthetic test.
4. **Assuming compaction works because config says so.** Config may say `enabled: true` but runtime could be on old release without compaction code. Always confirm with `readlink -f` and a synthetic live test.
5. **Confusing /tmp artifacts with persistent artifacts.** Old `/tmp/hermes-tool-output-compaction-artifacts` still exists with historical data. New artifacts must appear in `/home/konstantin/.hermes/tool-output-artifacts`.
6. **Relying on file counts instead of path comparison for skill integrity.** Running `find | wc -l` gives a single number but masks which skills are present. Use `comm -23` to compare runtime vs bundled paths and identify truly non-bundled (custom) skills. A count of 99 could include stale manifests, .archive files, or stale backups alongside active skills.
7. **Executing rollback without understanding severity.** Soft rollback (`enabled: false`) is almost always the right first step. Hard rollback (switch release symlink) is only for ImportError/gateway-crash scenarios.
8. **Writing "X not in source" safety tests for files that the script must read.** When a script gains read-only checks for config.yaml, memory_store.db, .env, or artifact_root, old tests asserting `"config.yaml" not in src` will break. Replace with read-only verification: extract the relevant function body and assert no write operations (no `.write(`, `write_text`, `INSERT`, `UPDATE`, `DELETE`, `VACUUM`). The pattern: `assert "X" in src` (must reference) + function-scoped mutation denylist.
9. **Treating historical raw-output suspects as active leaks.** Classify suspects against the active-release symlink mtime and rollout scope before recommending code/config changes. A pre-activation row can be real history without being current production risk.
10. **Counting benign config mentions as critical errors.** Split pattern matches from critical counts. INFO/debug mentions of `tool_output_compaction` or `artifact_root`, and old shell-command echoes, are not failures unless paired with hard error terms or ERROR/CRITICAL level.
11. **Flat log tails are not freshness checks.** `agent.log`, `gateway.log`, and `errors.log` can contain old tracebacks in the last N lines. For post-restart audits, first capture `ExecMainStartTimestamp`/change time, then count only lines whose parsed timestamp is newer. Keep unmatched traceback continuation lines only when attached to a fresh matching header.
12. **`fact_store` output alone does not prove HRR.** `probe`, `related`, and `reason` can silently degrade to FTS/keyword fallback when NumPy is missing or cached false. Verify `_HAS_NUMPY`, `hrr.encode_text`, vector coverage in `memory_store.db`, and result-shape evidence (`fts_rank` implies FTS path; HRR direct paths return scored facts without `fts_rank`).
13. **Active hotfix vs durable release.** After installing a dependency into the active venv, distinguish “runtime hotfixed” from “future release durable.” Check active symlink and release metadata. If the active release metadata lacks the new fields but the venv works, report it as an audit blind spot/hotfix state, not runtime breakage.
14. **Disk pressure is a Hermes reliability risk.** Under ~10% free disk, state/log/session writes become fragile. Include release-dir sizes, sessions DB/files, logs, and artifact root in suspicion audits before blaming providers or memory code.

## Verification Checklist

- [ ] Gateway `active` confirmed
- [ ] Compaction config matches expected scope
- [ ] No fresh critical errors in `journalctl`
- [ ] Artifacts only in configured `artifact_root`
- [ ] R13A synthetic test: compacted summary received, artifact created, no errors
- [ ] Skill integrity: all custom skills present, no stale manifest, no orphaned state
- [ ] If anything degraded: rollback path suggested, not executed without approval

## References

- `references/post-numpy-hrr-runtime-audit-2026-05-13.md` — case study: NumPy hotfix, gateway restart, HRR/fact_store verification, stale-log filtering, doctor false positive, and disk-pressure findings.
- `docs/hermes-runtime-management.md` — runtime scheme, release-dir, deploy/rollback, compaction config, monitoring
- `docs/hermes-compaction-operational-status.md` — R13A persistent root status snapshot
- `references/raw-leak-suspect-followup.md` — sanitized follow-up workflow for classifying raw-output suspects without exposing payloads
- `systemd-web-service-deployment` skill — generic systemd service deployment patterns
