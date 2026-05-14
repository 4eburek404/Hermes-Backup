# External Switch Runner Pattern

## Problem

When deploying a gateway/messaging service that you are currently talking through (e.g., Hermes agent itself), stopping the service kills the controlling session before the switch can complete. The agent cannot stop its own host.

## Solution: Two Paths

There are two valid switch paths. **Prefer Path B (graceful restart signal) when the service supports it** — it avoids the downtime, deactivating-hang, and force-kill risks of `systemctl stop`.

### Path A: Stop-Based (fallback for services without graceful restart signals)

Use when the service has **no** graceful restart signal wired to the service manager's restart policy.

### Path B: Graceful Restart Signal (preferred)

Use when the service supports a graceful restart signal that drains active work, exits with a specific code, and the service manager auto-restarts from the symlink. **This is the correct path for Hermes gateway and any service that wires SIGUSR1 → drain → exit coded → restart.**

**How to determine if Path B is available:**
1. Check the service code for signal handlers (`SIGUSR1`, `SIGHUP`, etc.) that trigger graceful drain.
2. Check the systemd unit for `RestartForceExitStatus=<code>` — this tells systemd which exit code means "restart me."
3. Verify `ExecStart` uses the symlink path (not a concrete release directory).
4. If all three are present → use Path B. Otherwise fall back to Path A.

**Path B flow:**
```
Phase 1: Precheck (read-only)
Phase 2: KillMode=control-group (idempotent override, safety net only)
Phase 3: Atomic symlink switch OLD → NEW (gateway keeps running on OLD code)
Phase 4: Send graceful restart signal (SIGUSR1) to OLD_PID
         → service drains active work → exits with restart code (e.g., 75)
Phase 5: Service manager auto-restarts (RestartForceExitStatus matches)
         → new process follows symlink → gets NEW code
Phase 6: Postcheck (symlink, service, PID change, imports, integrity, skills)
Phase 7: Report
```

**Key differences from Path A:**
- **NO** `systemctl stop` — wrong tool for services with graceful restart
- **NO** `systemctl restart` — wrong tool
- **NO** `kill -9` or force-kill — not needed
- **YES** `SIGUSR1` (or equivalent signal) — matches the service's internal `/restart` behavior
- **YES** Atomic symlink switch **before** restart — new process picks up new code
- **YES** Systemd's `RestartForceExitStatus` handles the actual restart — no manual start needed
- **YES** The old process drains gracefully (active sessions get shutdown notifications, work is saved)

**Concrete example: Hermes gateway (Path B)**
```
kill -USR1 $OLD_PID
→ gateway/run.py: restart_signal_handler()
→ runner.request_restart(detached=False, via_service=True)
→ graceful drain of active sessions
→ exit(75)  # GATEWAY_SERVICE_RESTART_EXIT_CODE from gateway/restart.py
→ systemd RestartForceExitStatus=75
→ new process via ExecStart=/home/konstantin/.hermes/hermes-agent/venv/bin/python
→ symlink now points to new RC → new code loaded
```

## Runner Structure

```
/home/konstantin/.hermes/ops/switch_to_<target_hash>.sh
```

### Required Phases (Path B — Graceful Restart)

1. **Precheck** (read-only, no mutations): verify current symlink target, target RC exists, metadata valid, runtime files present, artifact root accessible. ~15-20 checks. Abort on any failure.

2. **KillMode override** (idempotent, safety net): create systemd drop-in at `~/.config/systemd/user/<service>.service.d/10-killmode-control-group.conf` with:
   ```ini
   [Service]
   KillMode=control-group
   ```
   Follow with `systemctl --user daemon-reload` and verify via `systemctl show -p KillMode --value`. This is a safety net for emergency situations, not the primary stop mechanism.

3. **Atomic switch** (gateway keeps running on OLD code): `ln -s "$NEW" "$LINK.tmp.$$" && mv -Tf "$LINK.tmp.$$" "$LINK"`. Set `SYMLINK_SWITCHED=true` flag — from here, rollback is mandatory on error.

4. **Graceful restart signal**: Send the service's restart signal (e.g., `kill -USR1 "$OLD_PID"`). Wait for OLD_PID to exit (timeout: 180s). If it doesn't exit, the service's drain is stuck — do NOT force-kill; let the trap handle rollback.

5. **Wait for service manager restart**: Monitor for new PID (different from OLD_PID) and `active` state. Derive the wait budget from live systemd before the switch path: read `RestartUSec`, parse it to `RestartSec`, and set `RESTART_WAIT_TIMEOUT=max(180, RestartSec + 90)`. Rollback must not fire on "no new PID" until this full timeout expires. Record both `RestartUSec` and actual seconds waited for the new PID; do not leave report fields at defaults like `restart_usec=` or `seconds_waited_for_new_pid=0` unless that is the observed value.

6. **Postcheck**: verify symlink target, service active, Python imports succeed (if Python service), database integrity, runtime files present, artifact root accessible, recent logs clean of critical patterns. For log checks, distinguish release/runtime failures (`ImportError`, `Traceback`, SQLite corruption, adapter errors, SIGKILL) from provider/transient warnings (e.g., upstream HTTP 503 during old-process drain).

7. **Report**: write markdown report with all fields: `result`, `final_active_target`, `service_active`, `rollback_performed`, `symlink_switched`, `graceful_restart_sent`, `graceful_restart_completed`, `old_pid`, `new_pid`, `old_pid_exit_seconds`, `RestartUSec`/`restart_sec`, `restart_wait_timeout_sec`, `seconds_waited_for_new_pid`, and `restart_method`.

### Required Phases (Path A — Stop-Based, Fallback)

(Path A documentation preserved for services without graceful restart signals.)

...

### Rollback

Triggered via `trap 'rollback' ERR`. Guarded by `SYMLINK_SWITCHED` flag — only executes if symlink was already moved.

1. Stop gateway (with force-kill fallback)
2. Atomic rollback: `ln -s "$OLD" "$LINK.rollback.$$" && mv -Tf "$LINK.rollback.$$" "$LINK"`
3. Reset failed + start gateway
4. Verify `active`
5. Report: `rollback_performed: yes`

### Launch Command

```bash
systemd-run --user \
  --unit <transient-unit-name> \
  --wait \
  -- bash /path/to/switch_script.sh
```

The `--wait` flag blocks until completion and returns the exit code.

### Precheck-Only Mode

For safe validation before committing to switch:

```bash
systemd-run --user \
  --unit <precheck-unit-name> \
  --wait \
  -- bash /path/to/switch_script.sh --precheck-only
```

## Concrete Example: Hermes Agent Switch

- Service: `hermes-gateway`
- Symlink: `/home/konstantin/.hermes/hermes-agent`
- Release dirs: `~/.hermes/releases/hermes-agent-<hash>`
- Runner: `/home/konstantin/.hermes/ops/switch_to_d04c50f2f614.sh`
- Drop-in: `~/.config/systemd/user/hermes-gateway.service.d/10-killmode-control-group.conf`
- Logs: `~/.hermes/ops/switch_logs/switch_<hash>_<timestamp>.{log,report.md}`

## Pitfalls

- **Never** run the switch script from within the service's own session (Telegram, CLI, etc.).
- **Never** use `ln -sfn` for release-directory switches — it is non-atomic.
- **Always** verify KillMode before stopping — `mixed` mode causes deactivating hangs with child processes.
- **Always** set `SYMLINK_SWITCHED=true` immediately after `mv -Tf` — the trap must know to roll back.
- **Always** guard rollback against double-execution with a flag.
- **Post-success audits are read-only unless the runner/docs need diagnostic fixes.** After a successful switch, do not re-run the switch, restart the service, move the symlink, or rollback. Audit live state (`readlink -f`, `systemctl show`, integrity checks), parse the report, then only patch runner/reporting details if needed. Create a timestamped backup before touching the runner.
- **Do not trust static timeout defaults in reports.** If the runner has a `parse_restart_usec` helper, call it before the switch path and precheck-only report path. A successful report with `restart_usec` empty or `seconds_waited_for_new_pid=0` can mean diagnostics were never populated, not that the restart was instantaneous.

## Related

- Pitfall 11 in SKILL.md: KillMode=mixed deactivating hangs
- Pitfall 13 in SKILL.md: Atomic symlink replacement
- `references/release-dir-systemd-paths.md` — symlink path convention
