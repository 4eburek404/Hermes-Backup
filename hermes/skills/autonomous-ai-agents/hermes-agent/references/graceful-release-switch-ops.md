# Graceful Hermes release switch and post-switch ops

## Trigger

Use this reference when auditing or adjusting Konstantin's Hermes production release switch workflow, especially tasks involving:

- release-dir symlink switches under `/home/konstantin/.hermes/releases/`;
- `hermes-gateway` systemd user service graceful restart behavior;
- switch runners under `/home/konstantin/.hermes/ops/switch_to_<release>.sh`;
- post-switch reports, release status files, restart monitor outputs, or rollback readiness.

## Safety boundary

For post-switch audit/fix tasks, production is often already healthy. Preserve that by default:

- Do **not** run the switch again unless explicitly requested.
- Do **not** restart/stop the gateway during a report-formatting or baseline task.
- Do **not** change the production symlink during an audit/fix task.
- Do **not** rollback unless the task explicitly authorizes rollback and live checks show failure.
- Runner/docs edits are allowed only when the user asked for them; make a timestamped backup first.
- Historical reports are evidence. If a report was generated with formatting bugs, prefer fixing the generator and documenting the defect; do not silently regenerate old evidence unless explicitly requested.

## Live baseline checks

Before interpreting a switch report or editing an ops runner, capture read-only live state:

```bash
readlink -f /home/konstantin/.hermes/hermes-agent
systemctl --user is-active hermes-gateway
systemctl --user show hermes-gateway \
  -p MainPID \
  -p ActiveState \
  -p SubState \
  -p Result \
  -p Restart \
  -p RestartUSec \
  -p RestartForceExitStatus \
  -p NRestarts \
  --no-pager
```

For runtime-state integrity, add checks as needed:

```bash
sqlite3 /home/konstantin/.hermes/memory_store.db 'PRAGMA integrity_check;'
test -d /home/konstantin/.hermes/tool-output-artifacts
```

## Expected graceful mechanism

The safe production switch model is:

```text
atomic symlink switch -> SIGUSR1 -> gateway drain -> exit 75 -> systemd RestartForceExitStatus=75 -> auto-restart -> postcheck -> rollback only on failure
```

The normal switch path should use `kill -USR1 "$OLD_PID"` and should not use `systemctl stop/start/restart` or `kill -9`/`SIGKILL` as ordinary control flow.

Manual recovery documentation may mention `systemctl --user restart hermes-gateway`; classify that separately from executable normal-path code when grepping forbidden patterns.

## Runner report formatting pitfalls

When a Bash function writes Markdown using an unquoted heredoc such as `<<REPORT`, variable expansion is intentional, but Markdown backticks must be escaped carefully:

- correct inline code: `\`$value\`` inside the script source;
- over-escaped form such as `\\\`$value\\\`` can become command substitution or dangling backslashes in the generated report;
- triple backtick fences inside an expanding heredoc likewise need one escaping layer, not multiple accidental layers.

Post-switch report fields worth making explicit:

- `result`
- `active_target`
- `gateway_state`
- `MainPID`
- `symlink_switched`
- `rollback_performed`
- `graceful_restart_completed`
- `restart_usec` / `restart_sec` / `restart_wait_timeout_sec`
- `final_active_target`
- `service_active`

If a monitor/report generator has the formatting bug but historical output is already evidence, fix the generator and note the historical defect in the new audit report rather than rewriting the old report.

## Backup and verification pattern for runner-only edits

Before editing a production ops runner:

```bash
mkdir -p /home/konstantin/.hermes/ops/runner_backups
cp -a /home/konstantin/.hermes/ops/switch_to_<release>.sh \
  /home/konstantin/.hermes/ops/runner_backups/switch_to_<release>_<case>_before_edit_$(date +%Y%m%d_%H%M%S).sh
```

After edits, verify without launching the runner:

```bash
bash -n /home/konstantin/.hermes/ops/switch_to_<release>.sh
grep -n "SIGUSR1\|USR1" /home/konstantin/.hermes/ops/switch_to_<release>.sh
grep -n "RestartUSec\|restart_wait_timeout" /home/konstantin/.hermes/ops/switch_to_<release>.sh
grep -n "systemctl --user stop hermes-gateway" /home/konstantin/.hermes/ops/switch_to_<release>.sh || true
grep -n "systemctl --user restart hermes-gateway" /home/konstantin/.hermes/ops/switch_to_<release>.sh || true
grep -n "kill -9\|SIGKILL" /home/konstantin/.hermes/ops/switch_to_<release>.sh || true
sha256sum /home/konstantin/.hermes/ops/switch_to_<release>.sh <backup-path>
```

Recommended timeout baseline from the R14E observations:

- minimum restart wait timeout: `180s`;
- preferred future margin: `240s` if making a non-functional timeout-margin change;
- reason: observed `RestartUSec=60s`, new PID active after `113s`, implying ~49s startup/init after systemd restart delay.

## Operational baseline files

When asked to “закрепить baseline”, update or create:

- `/home/konstantin/.hermes/ops/RELEASE_STATUS.md`
- a task-specific final report under `/home/konstantin/.hermes/ops/`

Include:

- current production release and full path;
- rollback/previous known-good target;
- switch report path;
- runner path and backup path/hash when a runner changed;
- graceful restart mechanism;
- observed PID/timing facts;
- `RestartUSec` and timeout recommendation;
- postcheck/runtime skill/artifact/state integrity summary;
- rollback status;
- explicit statement that no switch/restart/symlink/rollback was performed during audit-only work.

Ops files under `~/.hermes/ops` are not repo files by themselves; do not commit them unless the user also changed a git repo file and explicitly asks for that commit scope.
