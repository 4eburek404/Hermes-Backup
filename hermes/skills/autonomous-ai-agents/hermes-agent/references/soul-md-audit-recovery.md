# SOUL.md audit and recovery

Use when a user asks where `SOUL.md` went, why behavior rules disappeared, or whether the Hermes persona/behavior constitution changed.

## Known paths

- Main Hermes instance: `~/.hermes/SOUL.md`
- Main source/docker template: `~/.hermes/hermes-agent/docker/SOUL.md`
- Guest Docker instance: `~/hermes-instances/guest/data/SOUL.md`
- Possible manual backups: `~/.hermes/backups/**/SOUL.md`

Do not confuse main and guest instances. The guest may have a minimal 536-byte template while the main instance has the active behavior file.

## Read-only diagnostic commands

```bash
printf 'HOME=%s\nHERMES_HOME=%s\n' "$HOME" "${HERMES_HOME:-}"
hermes config path 2>/dev/null || true
find ~/.hermes -maxdepth 4 \( -name 'SOUL.md' -o -name '*SOUL*' \) -printf '%p %TY-%Tm-%Td %TH:%TM:%TS %s bytes\n' 2>/dev/null || true
find ~/hermes-instances -maxdepth 5 \( -name 'SOUL.md' -o -name '*SOUL*' \) -printf '%p %TY-%Tm-%Td %TH:%TM:%TS %s bytes\n' 2>/dev/null || true
stat ~/.hermes/SOUL.md 2>&1 || true
```

If a backup exists, compare without editing:

```bash
diff -u ~/.hermes/backups/<backup-dir>/SOUL.md ~/.hermes/SOUL.md || true
```

Use `session_search` for phrases like `SOUL.md`, `memory-revision`, `behavioral DNA`, `holographic memory protocol`, and the observed file sizes/timestamps to identify the session that changed it.

## Reporting pattern

Separate:

- Verified facts: file exists/missing, exact path, size, mtime, active `HERMES_HOME`, backup paths.
- Delta: what changed vs backup, preferably with a compact diff summary.
- Hypothesis: likely rewrite/trim session and why, clearly marked as hypothesis if not proven.
- Action boundary: `SOUL.md` is a DO-NOT-EDIT file for Konstantin. Do not restore or rewrite it without explicit permission; offer diff or restore after approval.

## Recovery pattern

Only with explicit user approval:

```bash
cp ~/.hermes/SOUL.md ~/.hermes/SOUL.md.bak-$(date +%Y%m%d-%H%M%S)
cp ~/.hermes/backups/<backup-dir>/SOUL.md ~/.hermes/SOUL.md
stat ~/.hermes/SOUL.md
```

Then verify by reading the file and, if needed, starting a fresh Hermes session/gateway restart depending on current loader behavior.

## Pitfalls

- Do not answer from memory; check the live filesystem.
- Do not treat a guest `SOUL.md` as the main file.
- Do not say the file is deleted when search at shallow depth missed `~/.hermes/SOUL.md`; explicitly search `~/.hermes` and `~/hermes-instances`.
- Do not collapse diff findings into narrative only; show concrete paths/sizes/timestamps first.
